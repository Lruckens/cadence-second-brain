# Cadence second brain — proof of concept

A minimal knowledge layer for Cadence deals: **compile documents into structured
notes once, then answer questions from those notes** — instead of re-reading raw
documents on every question. This is the core idea behind Xebia's
`kickstartai-living-wiki-multi` project, stripped down to just two operations for a
first proof of concept. No templates, no permission tiers, no generator module yet —
just: does the compile-once-then-query loop actually produce good answers on real
Cadence project material?

Sibling project: [Cadence](../cadence) — Xebia Data's delivery-forecasting and
staffing platform (FastAPI + Postgres/Redis, React/TS/Vite). This repo is a separate,
standalone experiment; nothing here talks to Cadence's database or API yet.

## Folder structure — mirrors Cadence's real SharePoint tree

Cadence creates one SharePoint folder per deal, on the `XebiaDataDelivery` site,
under `Shared Documents/Customers/{Client}/{Deal}/`, with three subfolders it owns
by convention: `contracts/`, `proposals/`, `deliverables/`
(`engagement_docs.py` in the Cadence repo). "Client" is a Cadence `bench.client`
(a customer org); "Deal" is a Cadence `bench.engagement` — Cadence treats "deal" and
"project" as the same entity throughout, so this tool does too.

This repo's `sources/` and `brain/` follow exactly that shape:

```
sources/<client-slug>/<deal-slug>/contracts/...
sources/<client-slug>/<deal-slug>/proposals/...
sources/<client-slug>/<deal-slug>/deliverables/...

brain/<client-slug>/<deal-slug>/<note-id>.json   # compiled notes, one per source doc
```

Each compiled note records which category it came from, so `ask` can cite
`proposals/proposal-summary.md` etc., or be restricted to just one category with
`--category`.

## How it works

- **`ingest`** — reads a document, asks Claude to extract a structured note (a
  summary, key facts, decisions with rationale, open questions), and saves it under
  `brain/<client-slug>/<deal-slug>/`. Nothing is invented — the model is instructed
  to only extract what the document actually states.
- **`ask`** — loads every compiled note for a deal (not the raw documents) and
  answers a question from them, citing the category + source file for every claim.
- **`list`** — shows what's been ingested for a deal so far.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
npm install   # installs the claude CLI locally (node_modules/.bin/claude)
```

No `ANTHROPIC_API_KEY` needed. `cli.py` shells out to the local `claude` CLI in
headless mode (`claude -p ...`) — the same pattern Cadence's own Steward automation
uses (`.github/workflows/steward.yml`) — so it reuses whatever Claude Code auth is
already on this machine. If you're already logged into Claude Code here, it just
works. For unattended/CI use later, mint a token once with `claude setup-token`
(ties to your personal subscription, no separate billing) and export it as
`CLAUDE_CODE_OAUTH_TOKEN` — exactly what Cadence's Steward workflow does.

## Try it with the bundled example

The example simulates one deal (Acme Corp / Project Meridian) with one document in
each category.

```bash
python cli.py ingest "Acme Corp" "Project Meridian" proposal example/sources/acme-corp/project-meridian/proposals/proposal-summary.md
python cli.py ingest "Acme Corp" "Project Meridian" contract  example/sources/acme-corp/project-meridian/contracts/sow-excerpt.md
python cli.py ingest "Acme Corp" "Project Meridian" deliverable example/sources/acme-corp/project-meridian/deliverables/status-update.md

python cli.py ask "Acme Corp" "Project Meridian" "why did the forecasting integration slip, and what did the SOW promise for acceptance?"
python cli.py ask "Acme Corp" "Project Meridian" "what's still undecided across this deal?"
python cli.py list "Acme Corp" "Project Meridian"
```

## Using it on a real deal

Point `ingest` at real files wherever they live on disk — they don't need to be
copied into this repo first (`sources/` is gitignored specifically so real client
documents never accidentally get committed):

```bash
python cli.py ingest "<Client name>" "<Deal name>" contract     /path/to/sow.pdf
python cli.py ingest "<Client name>" "<Deal name>" proposal     /path/to/proposal.pdf
python cli.py ingest "<Client name>" "<Deal name>" deliverable  /path/to/status-report.md
python cli.py ask    "<Client name>" "<Deal name>" "what's blocking delivery right now?"
```

Each client/deal's compiled notes live under `brain/<client-slug>/<deal-slug>/` —
also gitignored. Only `example/` ships in git.

## What this deliberately doesn't do yet

- No web UI — CLI only, to keep the core loop honest before building around it.
- No permission tiers — don't ingest anything client-confidential until that exists.
  Everything under `Customers/` in real SharePoint is exactly the kind of content
  (contracts, rates, client names) the Living Wiki's permission layer was designed to
  protect — that almost certainly needs to come back before this touches real data
  at scale.
- No live pull from SharePoint/Graph — documents are ingested from local files for
  now; wiring this to `graph_drive.py`'s Graph client is a later step, not this PoC.
- No cross-referencing, templates, or generated reports (digests, progress reports).
- No integration with Cadence's own data (EVM/RAG status, forecasts).

## Next steps

1. Ingest 1–2 real Cadence deals' worth of documents (a few from each of
   contracts/proposals/deliverables) and sanity-check the answers against what you
   actually know about those deals.
2. Decide whether the compiled-note shape (facts / decisions / open questions) is the
   right one for all three categories, or whether contracts (acceptance criteria,
   payment terms) and proposals (scope, trade-offs) need a different extraction focus
   than deliverables (progress, blockers).
3. If it holds up, revisit which Living Wiki pieces are worth adding back —
   permission tiers first, then a real SharePoint/Graph connector instead of local
   files.
