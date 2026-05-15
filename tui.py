"""
sheaf-db terminal UI

Commands:
  <term>               lookup (default action)
  lookup <term>
  zoom [in|out|both] <term>
  synthesize <term>    (alias: s <term>)
  books                list all books in the db
  help                 show this message
  quit / exit / ^D

Omitting <term> reuses the last term looked up.
Long output is automatically paged through less.
"""

import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional

from prompt_toolkit import PromptSession
from prompt_toolkit.completion import Completer, Completion
from prompt_toolkit.formatted_text import ANSI
from prompt_toolkit.history import FileHistory

from config import SHEAF_DB_PATH
from sheaf_db import (
    lookup, zoom, synthesize,
    LookupResult, ZoomResult, SynthesisResult,
)

# ── ANSI colour helpers ───────────────────────────────────────────────────────

RESET   = "\033[0m"
BOLD    = "\033[1m"
DIM     = "\033[2m"
CYAN    = "\033[36m"
GREEN   = "\033[32m"
YELLOW  = "\033[33m"
MAGENTA = "\033[35m"
RED     = "\033[31m"

def b(s): return f"{BOLD}{s}{RESET}"
def c(s): return f"{CYAN}{s}{RESET}"
def g(s): return f"{GREEN}{s}{RESET}"
def y(s): return f"{YELLOW}{s}{RESET}"
def d(s): return f"{DIM}{s}{RESET}"
def m(s): return f"{MAGENTA}{s}{RESET}"


# ── Pager ─────────────────────────────────────────────────────────────────────

_PAGER_THRESHOLD = 30   # lines; below this, print directly


def _page(text: str) -> None:
    """Print text directly if short; pipe through less -RF for long output.

    less flags: -R pass ANSI colours through, -F exit immediately if output
    fits on one screen, -X don't clear the screen on exit.
    """
    if not sys.stdout.isatty() or text.count("\n") <= _PAGER_THRESHOLD:
        print(text)
        return
    less = shutil.which("less")
    if not less:
        print(text)
        return
    proc = subprocess.Popen([less, "-R", "-F", "-X"], stdin=subprocess.PIPE)
    try:
        proc.stdin.write(text.encode())
        proc.stdin.close()
        proc.wait()
    except BrokenPipeError:
        pass


# ── Output formatters ─────────────────────────────────────────────────────────

def fmt_lookup(r: LookupResult) -> str:
    if not r.concepts:
        return y(f"  No concepts found for '{r.query}'")
    lines = []
    for concept in r.concepts:
        lvl = f"  {d('['+concept.level+']')}" if concept.level else ""
        lines.append(
            f"\n{b(concept.canonical_label)}{lvl}"
            f"  {d('id='+str(concept.id)+' status='+concept.status)}"
        )
        if concept.occurrences:
            lines.append(f"  {d('Occurrences:')}")
            for occ in concept.occurrences:
                pages = ", ".join(str(p) for p in occ.pages[:8])
                tail  = d(" …") if len(occ.pages) > 8 else ""
                lines.append(f"    {g(occ.book_key)}: {pages}{tail}")
        if concept.relations:
            lines.append(f"  {d('Relations:')}")
            for rel in concept.relations:
                arrow = c("→") if rel.direction == "to" else m("←")
                score = d(f"  score={rel.score:.2f}") if rel.score is not None else ""
                mt    = d(f"  [{rel.match_type}]") if rel.match_type else ""
                lines.append(f"    {arrow} {rel.related_term}{mt}{score}")
    return "\n".join(lines)


def fmt_zoom(r: ZoomResult) -> str:
    if r.root is None:
        return y(f"  No concept found for '{r.query}'")
    lines = [f"\n{b(r.root.canonical_label)}  {d('seed, direction='+r.direction)}"]
    if not r.nodes:
        lines.append(d("  (no relations found for the given relation types)"))
    for node in r.nodes:
        indent = "  " * node.depth
        score  = d(f"  score={node.score:.2f}") if node.score is not None else ""
        mt     = d(f"  [{node.match_type}]") if node.match_type else ""
        rtype  = d(f"  {node.relation_type}") if node.relation_type else ""
        lines.append(f"{indent}  {c('→')} {node.canonical_label}{rtype}{mt}{score}")
    return "\n".join(lines)


def fmt_synthesis(r: SynthesisResult) -> str:
    if not r.seed_concepts:
        return y(f"  No concepts found for '{r.query}'")
    lines = [f"\n{b('=== Synthesis: '+r.query+' ===')}"]

    lines.append(f"\n{d('Seed concepts:')} ({len(r.seed_concepts)})")
    for c_ in r.seed_concepts:
        books = ", ".join(g(o.book_key) for o in c_.occurrences)
        lines.append(f"  {b(c_.canonical_label)}  {d('[')}{books}{d(']')}")

    if r.neighborhood:
        lines.append(f"\n{d('Neighbourhood:')} ({r.n_neighborhood} concepts)")
        for node in r.neighborhood:
            indent = "  " * node.depth
            score  = d(f"  {node.score:.2f}") if node.score is not None else ""
            lines.append(f"  {indent}{c('→')} {node.canonical_label}{score}")

    if r.by_book:
        lines.append(f"\n{d('By book:')} ({len(r.by_book)} books)")
        for book, labels in sorted(r.by_book.items()):
            lines.append(f"  {g(book)}  ({len(labels)} concepts)")
            for label in labels:
                lines.append(f"    {d('·')} {label}")

    if r.global_concepts:
        lines.append(f"\n{d('Global section candidates (≥2 books):')}")
        for label, n in r.global_concepts:
            lines.append(f"  {b(label)}  {d(str(n)+' books')}")

    if r.cross_field_overlaps:
        lines.append(f"\n{d('Cross-field overlaps:')} ({len(r.cross_field_overlaps)})")
        for o in r.cross_field_overlaps:
            src_only, tgt_only = o.bridged_books
            score = d(f"  {o.score:.2f}") if o.score is not None else ""
            src_b = g(",".join(src_only)) if src_only else d("(shared)")
            tgt_b = g(",".join(tgt_only)) if tgt_only else d("(shared)")
            lines.append(
                f"  {o.source_label} {d('[')}{src_b}{d(']')}"
                f"  {m('↔')}  {o.target_label} {d('[')}{tgt_b}{d(']')}{score}"
            )

    if not r.claims:
        lines.append(d("\n  (No claims yet — populate via curation or LLM extraction)"))

    return "\n".join(lines)


def fmt_books(db_path: Optional[Path]) -> str:
    import sqlite3
    con = sqlite3.connect(db_path or SHEAF_DB_PATH)
    rows = con.execute(
        """SELECT ie.book_key, count(distinct ie.concept_id) as n
           FROM index_entries ie GROUP BY ie.book_key ORDER BY n DESC"""
    ).fetchall()
    con.close()
    if not rows:
        return y("  No books found — run ingest.py first")
    lines = [f"\n{d('Books in db:')}"]
    for book_key, n in rows:
        lines.append(f"  {g(book_key)}  {d(str(n)+' concepts')}")
    return "\n".join(lines)


# ── Completer ─────────────────────────────────────────────────────────────────

COMMANDS   = ["lookup", "zoom", "synthesize", "s", "books", "help", "quit", "exit"]
DIRECTIONS = ["out", "in", "both"]


class SheafCompleter(Completer):
    def __init__(self):
        self._recent: list[str] = []

    def add_recent(self, term: str):
        if term and term not in self._recent:
            self._recent.insert(0, term)
            self._recent = self._recent[:30]

    def get_completions(self, document, complete_event):
        text  = document.text_before_cursor.lstrip()
        words = text.split()

        if not words or (len(words) == 1 and not text.endswith(" ")):
            prefix = words[0] if words else ""
            for cmd in COMMANDS:
                if cmd.startswith(prefix):
                    yield Completion(cmd, start_position=-len(prefix))
            return

        cmd = words[0]

        if cmd == "zoom":
            if len(words) == 1 or (len(words) == 2 and not text.endswith(" ")):
                prefix = words[1] if len(words) > 1 else ""
                for d_ in DIRECTIONS:
                    if d_.startswith(prefix):
                        yield Completion(d_, start_position=-len(prefix))
                return
            prefix = words[-1] if not text.endswith(" ") else ""
            for term in self._recent:
                if term.lower().startswith(prefix.lower()):
                    yield Completion(term, start_position=-len(prefix))
            return

        if cmd in ("lookup", "synthesize", "s"):
            prefix = " ".join(words[1:]) if not text.endswith(" ") else ""
            for term in self._recent:
                if term.lower().startswith(prefix.lower()):
                    yield Completion(term, start_position=-len(prefix))


# ── Help text ─────────────────────────────────────────────────────────────────

HELP_TEXT = f"""
{b('Commands')}
  {c('<term>')}                     lookup (default)
  {c('lookup <term>')}
  {c('zoom [in|out|both] <term>')}  traverse concept graph
  {c('synthesize <term>')}          cross-field view  (alias: {c('s')})
  {c('books')}                      list books in the db
  {c('help')}                       show this message
  {c('quit')} / {c('exit')} / Ctrl+D

  Omit {c('<term>')} to reuse the last term.  Long output is paged through less.

{b('Match tags')}  (shown in brackets after a related term)

  {d('[case]')}          Same term, different capitalisation.
                   "Memory" and "memory" are the same string modulo case.
                   Score is always 1.0.

  {d('[containment]')}   One term is a substring of the other.
                   "neuroinflammation" contains "inflammation".
                   Score ≈ shorter/longer length ratio (0–1).

  {d('[abbreviation]')}  One term is an acronym or abbreviation of the other.
                   "EEG" / "Electroencephalography (EEG)".
                   Score is always 1.0.

  {d('[token_set]')}     Terms share a significant overlap of word tokens,
                   ignoring order and stop words.
                   "EEG and behavior" / "EEG" share the token "EEG".
                   Score = Jaccard-like token overlap (0–1).

  {d('[fuzzy]')}         General edit-distance similarity (Levenshtein).
                   Used for near-identical spellings / typos.
                   Score = similarity ratio (0–1).

{b('Score')}

  All scores are in [0, 1].  Higher = stronger evidence that the two terms
  refer to the same concept across books.  Scores come from candidates.json
  produced by the textbook-db fuzzy-match pipeline.

  1.0  exact match within the chosen match type (case, abbreviation)
  0.7+ strong candidate — likely the same concept, different phrasing
  0.4–0.7  moderate — worth inspecting; may be related but distinct
  <0.4  weak — often noise from token overlap or substring accidents

{b('Relation types')}

  {d('candidate_restriction')}
       The only relation type currently in the db.  Populated automatically
       from candidates.json during ingest.  These are {b('candidate')} restriction
       morphisms in the sheaf sense: fuzzy-matched pairs that {b('may')} denote
       the same concept in different books/fields.  They are not asserted —
       they need curation before being promoted to typed semantic relations.

  Typed semantic relations (to be populated via curation / LLM extraction):
  {d('is_a  part_of  causes  modulates  realizes  correlates_with')}
  {d('measures  models  explains  predicts  inhibits  enables')}
  {d('analogous_to  operationalized_as')}

{b('Directions in zoom')}

  {c('out')}   Seed is the source of the relation — follows towards broader /
        related terms.  e.g. "inflammation" → "Gut inflammation".
  {c('in')}    Seed is the target — follows towards terms that point to it.
        e.g. "inflammation" ← "Gut inflammation" (containment).
  {c('both')}  Union of out and in, deduplicating shared nodes.
"""


# ── Command dispatch ──────────────────────────────────────────────────────────

CAND = ("candidate_restriction",)


def dispatch(
    raw: str,
    last_term: Optional[str],
    completer: SheafCompleter,
    db_path: Optional[Path],
) -> tuple[str, Optional[str]]:
    """Parse and run a command. Returns (output, new_last_term)."""
    parts = raw.strip().split(None, 1)
    if not parts:
        return "", last_term

    cmd  = parts[0].lower()
    rest = parts[1].strip() if len(parts) > 1 else ""

    if cmd in ("quit", "exit"):
        raise EOFError

    if cmd == "help":
        return HELP_TEXT, last_term

    if cmd == "books":
        return fmt_books(db_path), last_term

    if cmd == "zoom":
        zoom_parts = rest.split(None, 1)
        if zoom_parts and zoom_parts[0] in ("in", "out", "both"):
            direction = zoom_parts[0]
            term = zoom_parts[1].strip() if len(zoom_parts) > 1 else last_term
        else:
            direction = "out"
            term = rest or last_term
        if not term:
            return y("  No term specified and no previous term in session."), last_term
        completer.add_recent(term)
        r = zoom(term, direction=direction, relation_types=CAND, db_path=db_path)
        return fmt_zoom(r), term

    if cmd in ("synthesize", "s"):
        term = rest or last_term
        if not term:
            return y("  No term specified and no previous term in session."), last_term
        completer.add_recent(term)
        r = synthesize(term, relation_types=CAND, db_path=db_path)
        return fmt_synthesis(r), term

    if cmd == "lookup":
        term = rest or last_term
    else:
        term = raw.strip()

    if not term:
        return y("  No term specified."), last_term

    completer.add_recent(term)
    r = lookup(term, db_path=db_path)
    return fmt_lookup(r), term


# ── Main loop ─────────────────────────────────────────────────────────────────

def main(db_path: Optional[Path] = None) -> None:
    history_path = Path.home() / ".sheaf_db_history"
    completer    = SheafCompleter()

    session: PromptSession = PromptSession(
        history=FileHistory(str(history_path)),
        completer=completer,
        complete_while_typing=False,
        mouse_support=False,
    )

    db = db_path or SHEAF_DB_PATH
    print(f"{b('sheaf-db')}  {d(str(db))}  — type {c('help')} for commands, Ctrl+D to quit\n")

    last_term: Optional[str] = None

    while True:
        try:
            prompt_str = f"{d('['+last_term+']') +' ' if last_term else ''}{c('❯')} "
            raw = session.prompt(ANSI(prompt_str))
        except KeyboardInterrupt:
            continue
        except EOFError:
            print(d("\nbye"))
            break

        raw = raw.strip()
        if not raw:
            continue

        try:
            output, last_term = dispatch(raw, last_term, completer, db)
            _page(output)
        except EOFError:
            print(d("\nbye"))
            break
        except Exception as exc:
            print(f"{RED}Error: {exc}{RESET}")

        print()


if __name__ == "__main__":
    db_arg = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(db_path=db_arg)
