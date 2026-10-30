# Brahmaniss

**Ask about unfamiliar code, find the right place, and verify the evidence.**

New contributors lose hours finding where a feature lives in an unfamiliar repository.
Brahmaniss indexes a code repository locally and answers questions such as
*"Where is the session cookie loaded?"* with ranked, exact source regions (path and
line range) that you can open in the full file. AI is optional: with consent, it can
suggest search terms or explain the top snippets, citing only the evidence it was shown.

Built by Team NextGen for CBIT Hacktoberfest Hackathon '26.

## How it works

```text
ZIP upload ──> safe extraction ──> symbol chunks ─────> SQLite + FTS5 snapshot
                                                              │
question ──> keyword + exact-symbol + symbol/path search (RRF) ┘──> evidence cards
                                                              │
               optional, with consent: Featherless AI ────────┘──> cited explanation
```

- **Import** (`backend/app/indexing.py`): rejects unsafe paths, symlinks, duplicates,
  encrypted or oversized archives; keeps source files of supported languages, skips
  dependency/build folders and generated files; never runs uploaded code. Python is
  chunked with `ast`; other languages with their official tree-sitter grammars (bundled
  wheels, fully offline), falling back to line windows (`backend/app/languages.py`).
- **Index** (`backend/app/storage.py`): one SQLite database per snapshot, published
  atomically; a failed upload keeps the previous index; it survives restarts.
- **Search** (`backend/app/search.py`): BM25 keyword search, exact-symbol lookup and
  symbol/path search merged with reciprocal-rank fusion; test files ranked lower and
  labelled. No AI is needed for indexing or search.
- **AI** (`backend/app/explain.py`, optional): only after you review the exact text to
  be sent. At most five snippets (< 20 KiB) labelled `E1`–`E5`; replies with unknown or
  missing citations are rejected, and paths/lines always come from the index. General
  programming answers are labelled as not based on the repository.
- **UI** (`frontend/src/App.tsx`): one page — upload, ask, evidence cards, full-file
  viewer, and a separate AI panel.

## Setup

Requires Python 3.12+ and Node 20.19+.

```bash
cd backend
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt

cd ../frontend
npm ci
npm run build
cd ..
```

Run from the repository root (serves the API and the built UI together):

```bash
cd backend
.venv/bin/uvicorn --factory app.main:create_app --host 127.0.0.1 --port 8723
```

Open <http://127.0.0.1:8723>, upload a repository ZIP (for example GitHub's
"Download ZIP"), and ask a question.

Optional AI (search works without it):

```bash
export FEATHERLESS_API_KEY=...        # kept on the backend only
export FEATHERLESS_MODEL=...          # any Featherless chat model
```

Any OpenAI-compatible endpoint works through `FEATHERLESS_BASE_URL`, e.g. Azure OpenAI
with `https://<resource>.openai.azure.com/openai/v1` and the deployment name as the model.

For frontend development, run `npx vite` in `frontend/` (it proxies `/api` to port 8723).

## Limits

- Python, JavaScript/TypeScript, Java, Kotlin, Go, PHP, Swift and Ruby. 20 MB ZIP,
  100 MB expanded, 1,000 files, 256 KiB per file.
- One repository at a time; uploads replace the current snapshot.
- Local use only: run on `127.0.0.1`; the API rejects other hosts and browser origins.
- Search finds words and symbols, not meaning; no match does not prove absence.
  AI citations prove where a claim came from, not that the claim is correct.

## Evaluation

Frozen public repository: [pallets/flask](https://github.com/pallets/flask) at
`49943b5`, 17 manually labelled questions (10 dev, 7 held out from tuning) plus 8
negative questions about things Flask does not contain. Hit@5 = a correct location is
among the first five results.

| Split | Keyword only | Hybrid (default) | Hybrid + AI terms |
|-------|--------------|------------------|-------------------|
| Dev (10) | 9/10 | **10/10** | 9/10 |
| Held out (7) | 6/7 | **6/7** | 5/7 |

Indexing: 83 files and 1,035 code regions in 0.09 s; slowest search 7.9 ms
(Apple Silicon, Python 3.12). Misses: the test client question ranks
`FlaskClient.open` 10th. AI terms (`gpt-4o-mini`) put 13 of 17 answers first but pushed
two below rank 5, so they stay optional.

AI explanations (`gpt-4o-mini`, top 5 results, checked by hand): all 17 positive
questions were answered with correct citations, and all 8 negatives reported
insufficient evidence. When a question names something (e.g. GraphQL) that no snippet
contains, the context says so, which stops the model guessing from look-alike code.
Full per-question ranks: `evaluation/results.json`.

Reproduce from the repository root:

```bash
backend/.venv/bin/python evaluation/fetch_demo.py
backend/.venv/bin/python evaluation/run_eval.py
```

With the AI variables set, `run_eval.py` also measures an "expanded" mode with
AI-suggested terms.

## Checks

From the repository root:

```bash
cd backend && .venv/bin/ruff format --check . ../evaluation && .venv/bin/ruff check . ../evaluation && .venv/bin/pytest -q
cd ../frontend && npm run build && npm run lint
```

## Demo (under three minutes)

1. Upload the Flask ZIP; the summary shows files indexed and skipped.
2. Ask *"Where is the session cookie signed and loaded?"*; `sessions.py` comes first.
3. Open it in the full file to verify the highlighted lines.
4. Ask *"How are payments processed with Stripe?"*; only weak matches appear.
5. With AI configured: *Explain the top 5 results…*, review the exact context, send,
   and follow the `E1`/`E2` citations back to the code.

More detail: [`spec.md`](spec.md), [`implementation.md`](implementation.md),
[`user-flow.md`](user-flow.md).
