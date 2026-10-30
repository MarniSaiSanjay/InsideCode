"""Index the frozen demo ZIP and report Hit@5 for keyword-only and hybrid search.

Run from the repository root after `python evaluation/fetch_demo.py`:
    backend/.venv/bin/python evaluation/run_eval.py

With FEATHERLESS_API_KEY and FEATHERLESS_MODEL set, an "expanded" mode (hybrid plus
AI-suggested terms) is also measured; it sends only the questions to the provider.
"""

import json
import platform
import sys
import tempfile
import time
from contextlib import closing
from pathlib import Path

from fetch_demo import HERE, TARGET

sys.path.insert(0, str(HERE.parent / "backend"))
from app.config import Limits, load_settings  # noqa: E402
from app.explain import AIUnavailable, suggest_terms  # noqa: E402
from app.search import search  # noqa: E402
from app.storage import Store  # noqa: E402

TOP = 5


def first_hit(results: list[dict], expected: list[dict]) -> int | None:
    wanted = {(e["path"], e["symbol"]) for e in expected}
    for rank, r in enumerate(results, 1):
        if (r["path"], r["symbol"]) in wanted:
            return rank
    return None


def main() -> None:
    cases = json.loads((HERE / "cases.json").read_text())
    settings = load_settings()
    modes = ["keyword", "hybrid"] + (["expanded"] if settings.ai_configured else [])
    with tempfile.TemporaryDirectory() as state:
        store = Store(Path(state))
        started = time.perf_counter()
        summary = store.import_zip(TARGET.name, TARGET.read_bytes(), Limits())
        index_seconds = time.perf_counter() - started
        rows, timings = [], []
        with closing(store.connect(summary["snapshot_id"])) as db:
            for case in cases["cases"]:
                row = {"split": case["split"], "question": case["question"]}
                for mode in modes:
                    extra = []
                    if mode == "expanded":
                        try:
                            extra = row["suggested"] = suggest_terms(settings, case["question"])
                        except AIUnavailable as exc:
                            row["suggested"] = str(exc)
                    started = time.perf_counter()
                    results = search(db, case["question"], mode != "keyword", extra)
                    timings.append(time.perf_counter() - started)
                    row[mode] = first_hit(results, case["expected"])
                rows.append(row)
            negatives = {q: [r["path"] for r in search(db, q)[:3]] for q in cases["negatives"]}

    report = {
        "repository": {k: cases["repository"][k] for k in ("name", "commit")},
        "machine": f"{platform.system()} {platform.machine()}, Python {platform.python_version()}",
        "index": {k: summary[k] for k in ("files", "chunks")}
        | {"seconds": round(index_seconds, 2)},
        "max_search_ms": round(max(timings) * 1000, 1),
        "hit_at_5": {
            split: {
                mode: f"{sum(1 for r in subset if r[mode] and r[mode] <= TOP)}/{len(subset)}"
                for mode in modes
            }
            for split in ("dev", "heldout")
            if (subset := [r for r in rows if r["split"] == split])
        },
        "cases": rows,
        "negatives_top3": negatives,
    }
    (HERE / "results.json").write_text(json.dumps(report, indent=2) + "\n")
    for r in rows:
        ranks = " ".join(f"{m}={r[m]!s:5}" for m in modes)
        print(f"{r['split']:8} {ranks} {r['question']}")
    print(json.dumps({k: report[k] for k in ("index", "max_search_ms", "hit_at_5")}, indent=2))


if __name__ == "__main__":
    main()
