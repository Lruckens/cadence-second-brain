"""
Cadence second brain — minimal proof of concept.

Mirrors the real folder structure Cadence creates in SharePoint for each deal
(source/apps/api/src/cadence_api/services/engagement_docs.py):

    Customers/{Client}/{Deal}/{contracts|proposals|deliverables}/

"Client" = a Cadence `bench.client` (a customer org). "Deal" = a Cadence
`bench.engagement` — Cadence treats "deal" and "project" as the same entity,
so this tool does too. The three subfolders are a closed, lowercase set;
Cadence owns no other categories for deal documents today.

Commands:
  ingest <client> <deal> <category> <file>   compile a document into a structured note
  ask    <client> <deal> <question>           answer a question from that deal's notes
  list   <client> <deal>                      show what's been ingested for a deal

Notes are compiled once at ingest time (facts, decisions, open questions) and
reused across every future question — that's the "second brain" idea, as
opposed to re-reading raw documents on every query.

Model access: shells out to the local `claude` CLI (node_modules/.bin/claude,
installed via `npm install`) in headless print mode, the same pattern Cadence's
own Steward automation uses (.github/workflows/steward.yml) — reuses whatever
Claude Code auth is already on this machine (OAuth session or
CLAUDE_CODE_OAUTH_TOKEN), so no separate metered API key is needed.
"""

import argparse
import json
import os
import re
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
SOURCES = ROOT / "sources"
BRAIN = ROOT / "brain"
CLAUDE_BIN = ROOT / "node_modules" / ".bin" / "claude"
MODEL = "sonnet"

# The closed category set Cadence owns by convention for deal documents.
CATEGORIES = ("contract", "proposal", "deliverable")
CATEGORY_FOLDER = {
    "contract": "contracts",
    "proposal": "proposals",
    "deliverable": "deliverables",
}

# No file/code tools are needed for text-in, text-out compilation — keep the
# subprocess restricted to pure generation.
NO_TOOLS_FLAGS = [
    "--restricted",
    "--disallowedTools", "Read,Write,Edit,Glob,Grep,Task,WebFetch,WebSearch",
]

INGEST_SYSTEM_PROMPT = """You compile a raw project document into a compact, structured note for a \
knowledge base. Extract only what is actually stated in the document — never invent \
information. Return strict JSON with this shape, and nothing else — no markdown fences, no \
commentary outside the JSON:

{
  "summary": "one paragraph, what this document is and why it matters",
  "key_facts": ["short factual statement", ...],
  "decisions": ["a decision recorded in this document, with its rationale if stated", ...],
  "open_questions": ["a question raised but not resolved in this document", ...]
}

Use empty lists where a category doesn't apply."""

ASK_SYSTEM_PROMPT = """You answer questions about a client deal using ONLY the compiled notes \
provided below. Each note is labeled with its source category (contract/proposal/deliverable) \
and source file. Cite both for every claim you make, like this: \
(source: proposals/proposal-summary.md). If the notes don't contain the answer, say so plainly \
instead of guessing."""


def run_claude(system_prompt: str, user_prompt: str) -> str:
    if not CLAUDE_BIN.exists():
        sys.exit(f"claude CLI not found at {CLAUDE_BIN} — run `npm install` first.")

    result = subprocess.run(
        [
            str(CLAUDE_BIN), "-p",
            "--append-system-prompt", system_prompt,
            "--output-format", "json",
            "--model", MODEL,
            *NO_TOOLS_FLAGS,
        ],
        input=user_prompt,
        capture_output=True, text=True, timeout=180, cwd=ROOT,
    )
    if result.returncode != 0:
        sys.exit(f"claude CLI failed (exit {result.returncode}):\n{result.stderr}")

    try:
        envelope = json.loads(result.stdout)
    except json.JSONDecodeError:
        sys.exit(f"Could not parse claude CLI output:\n{result.stdout}")

    if envelope.get("is_error"):
        sys.exit(f"claude CLI reported an error:\n{envelope.get('result')}")

    return envelope["result"]


def strip_code_fence(text: str) -> str:
    text = text.strip()
    match = re.match(r"^```(?:json)?\s*\n(.*)\n```$", text, re.DOTALL)
    return match.group(1) if match else text


def slugify(name: str) -> str:
    s = name.strip().lower()
    s = re.sub(r"[^a-z0-9]+", "-", s)
    return s.strip("-")


def read_text(path: Path) -> str:
    if path.suffix.lower() == ".pdf":
        from pypdf import PdfReader

        reader = PdfReader(str(path))
        return "\n\n".join(page.extract_text() or "" for page in reader.pages)
    return path.read_text(encoding="utf-8", errors="ignore")


def deal_brain_dir(client: str, deal: str) -> Path:
    d = BRAIN / slugify(client) / slugify(deal)
    d.mkdir(parents=True, exist_ok=True)
    return d


def cmd_ingest(client: str, deal: str, category: str, file: str):
    if category not in CATEGORIES:
        sys.exit(f"category must be one of {CATEGORIES}, got '{category}'")

    src_path = Path(file).expanduser().resolve()
    if not src_path.exists():
        sys.exit(f"File not found: {src_path}")

    text = read_text(src_path)
    if not text.strip():
        sys.exit(f"No extractable text in: {src_path}")

    print(f"Compiling note from {CATEGORY_FOLDER[category]}/{src_path.name}...")
    raw = run_claude(INGEST_SYSTEM_PROMPT, text[:100_000])
    try:
        note = json.loads(strip_code_fence(raw))
    except json.JSONDecodeError:
        sys.exit(f"Model did not return valid JSON:\n{raw}")

    note_id = f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:6]}"
    note["client"] = client
    note["deal"] = deal
    note["category"] = category
    note["source_file"] = src_path.name
    note["ingested_at"] = datetime.now(timezone.utc).isoformat()

    brain_dir = deal_brain_dir(client, deal)
    out_path = brain_dir / f"{note_id}.json"
    out_path.write_text(json.dumps(note, indent=2))
    print(f"Saved note: {out_path.relative_to(ROOT)}")
    print(f"  facts: {len(note.get('key_facts', []))}  "
          f"decisions: {len(note.get('decisions', []))}  "
          f"open questions: {len(note.get('open_questions', []))}")


def load_notes(client: str, deal: str) -> list[dict]:
    brain_dir = BRAIN / slugify(client) / slugify(deal)
    if not brain_dir.exists():
        return []
    notes = []
    for p in sorted(brain_dir.glob("*.json")):
        notes.append(json.loads(p.read_text()))
    return notes


def cmd_ask(client: str, deal: str, question: str, category: str | None = None):
    notes = load_notes(client, deal)
    if category:
        notes = [n for n in notes if n.get("category") == category]
    if not notes:
        sys.exit(f"No notes found for {client}/{deal}"
                  f"{f' (category={category})' if category else ''}. Ingest something first.")

    context = "\n\n".join(
        f"--- {CATEGORY_FOLDER[n['category']]}/{n['source_file']} (ingested {n['ingested_at']}) ---\n"
        f"Summary: {n['summary']}\n"
        f"Key facts: {n['key_facts']}\n"
        f"Decisions: {n['decisions']}\n"
        f"Open questions: {n['open_questions']}"
        for n in notes
    )

    answer = run_claude(ASK_SYSTEM_PROMPT, f"{context}\n\n---\n\nQuestion: {question}")
    print(answer)


def cmd_list(client: str, deal: str):
    notes = load_notes(client, deal)
    if not notes:
        print(f"No notes for {client}/{deal} yet.")
        return
    for n in notes:
        print(f"- {CATEGORY_FOLDER[n['category']]}/{n['source_file']}  (ingested {n['ingested_at']})")
        print(f"    {n['summary'][:100]}")


def main():
    parser = argparse.ArgumentParser(description="Cadence second brain (PoC)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_ingest = sub.add_parser("ingest", help="Compile a document into a note")
    p_ingest.add_argument("client", help="Customer org name, e.g. 'Acme Corp'")
    p_ingest.add_argument("deal", help="Deal/project name, e.g. 'Project Meridian'")
    p_ingest.add_argument("category", choices=CATEGORIES)
    p_ingest.add_argument("file")

    p_ask = sub.add_parser("ask", help="Ask a question against a deal's notes")
    p_ask.add_argument("client")
    p_ask.add_argument("deal")
    p_ask.add_argument("question")
    p_ask.add_argument("--category", choices=CATEGORIES, default=None,
                        help="Restrict to one category (default: all)")

    p_list = sub.add_parser("list", help="List notes ingested for a deal")
    p_list.add_argument("client")
    p_list.add_argument("deal")

    args = parser.parse_args()

    if args.command == "ingest":
        cmd_ingest(args.client, args.deal, args.category, args.file)
    elif args.command == "ask":
        cmd_ask(args.client, args.deal, args.question, args.category)
    elif args.command == "list":
        cmd_list(args.client, args.deal)


if __name__ == "__main__":
    main()
