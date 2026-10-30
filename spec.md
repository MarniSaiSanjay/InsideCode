# Brahmaniss - Simple MVP Specification

**Status:** Plan, not implemented.
**Updated:** October 30, 2026.
**Problem:** Helping New Contributors Find the Right Code.

## 1. What we are building

A local dashboard where a developer uploads a source-code ZIP, asks a question,
and gets relevant functions/files with exact code, line numbers, and a short
AI explanation backed by that code.

**One dashboard. One backend. One database. One uploaded repository at a time.**

Started with Python repositories; common languages (JavaScript/TypeScript, Java,
Kotlin, Go, C#, C/C++, Rust, PHP, Swift, Ruby) are now indexed with a lightweight
regex-based chunker. A limited language set is allowed by the problem statement.

## 2. Required workflow

1. **Upload:** Accept a ZIP and clearly show the supported language and limits.
2. **Index:** Filter files, extract functions/classes, and save searchable code.
3. **Search:** Accept natural-language questions and exact keywords.
4. **Inspect:** Show ranked snippets with real paths, line ranges, and match reasons.
5. **Explain:** With consent, send selected snippets to Featherless and display a
   short cited explanation separately from the evidence.

Examples, adapted to the actual uploaded code:

- "Where are expired tokens rejected?"
- "Where is `validate_token` defined?"
- "How does the route reference the validation module?"
- "Where should I start reading to change the expiry rule?"

These are source-discovery questions, not requests to edit or execute code.
Do not claim a module relationship or safe change unless the evidence supports
the statement. No full call graph or impact analysis is promised.

## 3. Coverage of the photographed requirements

| Requirement | Our MVP |
|---|---|
| 1. Local repository or source archive | ZIP upload; local-folder import is unnecessary for the first version |
| 2. Exclude generated/build/dependency files and enforce configurable file size | Filtering and explicit limits with skipped-file counts |
| 3. Index paths, functions/classes, and snippets | Python `ast` (regex definitions for other languages) plus stored source ranges |
| 4. Natural-language and keyword queries | One search box supporting both |
| 5. Rank files and code regions | Keyword search combined with symbol matching |
| 6. Show code, path, and line range | Evidence cards and an expandable source view |
| 7. Separate evidence from explanation; no unsupported responsibility claims | Independent evidence and AI panels, validated references, honest limitations |
| 8. At least ten manually verified repository-specific questions | Evaluation questions and expected files/symbols saved with the demo repository identity |

The expected output also calls for an interactive dashboard, hybrid retrieval,
and grounded AI explanations. Our hybrid is **lexical + symbol search**, not
embedding-based search. Featherless is suggested in the photos and is our planned
explanation provider; an accessible model must be checked before integration.

## 4. Minimal stack

| Component | Choice |
|---|---|
| Frontend | React + TypeScript + Vite |
| Backend | Python + FastAPI |
| Source parsing | Python standard-library `ast`; stdlib regexes for other languages |
| Storage and keyword search | SQLite + FTS5 |
| AI explanation | Featherless through an OpenAI-compatible client |
| Checks | pytest, frontend typecheck/lint/build, focused browser tests |

Use Python's existing parser for the first supported language, rather than
introducing a multi-language parsing framework immediately. Parse source as data;
never import or execute the uploaded modules. The parser needs reliable end
positions; select a compatible supported Python runtime during scaffolding.

There is no OpenCode runtime, vector database, agent framework, or separate
worker service.

## 5. Index once, search many times

- Accept UTF-8 source files of supported languages, including tests; label tests separately.
- Exclude `.git`, dependency environments, caches, build outputs, generated files,
  binary files, archives, and known secret-oriented filenames.
- Keep a private copy of admitted source, repository-relative paths, and content
  hashes. Display evidence from that copy, not a changing original directory.
- Extract function, async-function, class, and method names with exact ranges.
- Split large regions into bounded contiguous snippets; include module-level code.
- If parsing fails, use labelled line-based fallback rather than silently losing
  the file or inventing symbols.
- Persist source and index locally so search survives a restart.
- Publish a replacement only after its complete index succeeds. Existing evidence
  keeps its snapshot identity; reject stale requests rather than mixing uploads.
- No live watching, incremental indexing, or repository management interface.

Initial configurable limits: **20 MiB ZIP, 100 MiB expanded content, 10,000 archive
entries, 1,000 indexed files, 256 KiB per indexed file, and 120 seconds per import**.
Show limits and skip reasons. These are our engineering choices, not organizer
rules. Input-level limit breaches fail clearly; oversized individual files skip
with a warning. A ZIP with no eligible files does not become a useful ready index.

## 6. Retrieval and exact evidence

1. Normalize the question, split identifiers, and discard unhelpful filler words.
2. Retrieve code with SQLite FTS5.
3. Independently match function/class names and path tokens.
4. Combine candidate ranks using reciprocal rank fusion; deduplicate overlaps.
5. Return up to ten regions, keeping the first few results reasonably diverse.

Each result contains a repository-relative path, symbol when known, exact snippet,
one-based inclusive line range, and actual match reasons such as "exact symbol"
or "keyword match". Do not display made-up accuracy percentages.

Use parameterized SQL and safe FTS expressions. Bound query length and candidate
counts. Empty input, malformed search syntax, and missing matches must not crash
the service. "Not found in our index" does not mean "absent from the repository".

## 7. Small, grounded AI layer

- Search results appear before the explanation finishes.
- Before external inference, explain that the question and selected code leave
  the machine; require explicit consent and make context inspectable.
- Send at most five approved snippets and a bounded question/context payload,
  not the entire repository. Keep context below 20 KiB and within model capacity.
- Give each snippet a backend-owned ID such as `E1`. Require structured claims
  with those IDs; resolve displayed paths and lines from the index.
- Reject malformed responses, unknown IDs, and uncited positive claims.
- Treat source comments and model output as untrusted text, not instructions.
- Use a 20-second overall deadline; on failure, retain search results and show
  that explanation is unavailable. Do not invent a successful fallback.
- Say when evidence is insufficient, including when only a test supports a match.

Valid citations establish source identity, not automatic semantic correctness.
Manually audit claims during evaluation. No API key or no consent means
search-only mode; the complete demo must also prove a real AI explanation works.

After the local-search baseline works, optional consented AI query expansion can
suggest a few search terms. Keep the original-query results, bound and validate
the suggestions, and fall back on failure. Indexing remains entirely AI-free.
Evaluate expansion separately; it cannot guarantee that nothing is missed.

General programming questions, such as "What is password hashing?", may receive
a separately labelled general answer without repository search. Questions about
this project's behaviour still require retrieved source evidence.

## 8. Simple UI

One page with an upload/status area, question box, ranked evidence cards, an
expandable source viewer, and a separate AI explanation panel.

Show processing, ready, no-match, partial-coverage, and failure states plainly.
Ignore stale responses after a new upload or question. Keep controls keyboard
accessible, source text readable, and the layout usable on a laptop.

No chat history, graphs, project switcher, accounts, or evaluation dashboard.

## 9. Reliability and safety we do not cut

- Reject unsafe ZIP paths, symlinks, duplicate/colliding paths, encrypted/corrupt
  archives, and oversized input. Enforce actual expanded-byte and time limits.
- Stage imports in owned temporary locations; clean failed imports without
  touching unrelated files. Allow only one import at a time.
- Never execute uploaded code, install its dependencies, or follow its scripts.
- Keep keys backend-only and source/private state out of version control.
- Do not log source, questions, answers, or secrets. Filename exclusions do not
  guarantee that all secrets have been found; use public code for the demo.
- Bind locally, restrict browser origins/hosts, and protect local API access
  against requests from unrelated websites.
- Serve source by snapshot/file IDs, not arbitrary filesystem paths.
- Use bounded in-process work, not an external queue. Interrupted imports fail
  cleanly on restart; already published indexes remain usable.
- Any public demo is pre-indexed public data only, with uploads disabled and
  provider requests limited. Public hosting is not required.

## 10. Verification and efficiency

Use one frozen public repository with **at least ten answerable questions** and
manually checked relevant files/symbols. Keeping all ten on one snapshot is our
conservative acceptance choice, not an additional rule shown in the photos.
Include feature-location, relationship, small-change, and exact-symbol questions.
Add negative/unsupported questions separately; do not count them toward the ten.
Choose the repository and begin labels during foundation work. Measure local
search as soon as it exists; keep some labelled questions held out from tuning
for final evaluation.

Record each question, expected locations, actual ranks, and snapshot identity in
a small JSON fixture. Compare keyword-only and hybrid results. Report Hit@5
(whether a relevant location appears among the first five results) and failures.
Never hard-code repository-specific answers.

**Targets, not achieved measurements:** warm local search under one second for
the demo repository; at least 8 of 10 questions with a relevant location in the
first five results. Record the machine and input size. Indexing happens once per
upload; searches reuse the index and never need a model call.

Required checks:

- Import exclusions and unsafe/oversized ZIP rejection.
- Parser/chunk/source-line correctness, including Unicode and newline edge cases.
- Keyword, natural-language, no-match, and stale-snapshot behaviour.
- Valid/invalid citations and provider timeout handling.
- Restart persistence and a failed replacement preserving the previous index.
- Real browser upload -> question -> snippet -> cited source.
- A real Featherless call on consented public code, not just mocked responses.
- Typecheck, configured lint/format checks, tests, and production build.

All evaluated snippets/ranges must match source exactly; manually checked positive
claims must be supported. Failures are reported and fixed, not hidden.

## 11. Build order

1. Set up the backend, frontend, SQLite capability check, and API connection.
2. Make ZIP -> filtered source -> Python symbols -> persisted index work.
3. Make one question return the correct source region through the API.
4. Connect the one-page dashboard and source viewer.
5. Add consent, AI explanation, citation checks, and failure handling.
6. Run the ten-question evaluation, finish tests, document setup, record the demo.

The task-by-task breakdown and per-task checks are in `implementation.md`,
section 5. This document's six stages group those tasks into the core flow.

Freeze features once this works. Do not add languages or embeddings to compensate
for an unreliable basic workflow.

## 12. Submission

The photos require an open-source GitHub repository with clean contributions from
all team members, a README covering problem/architecture/setup, and either a live
demo or a working prototype video **under three minutes**. Original submission
code is to be written in the 24-hour hackathon; open-source libraries are allowed.

The photographed assignment is locked for Team "NextGen" and cannot be changed.
Verify any additional organizer rules and exact deadline separately. Do not
commit or push merely because the submission eventually requires a repository.

Deliver the local prototype video by default. Keep the final pitch simple:
**ask about unfamiliar code, find the right place, and verify the evidence.**
