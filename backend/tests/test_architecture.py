import pytest

from app.architecture import MAX_MODULES, Resolver, _layers, _partition, in_scope
from tests.helpers import upload

PATHS = [
    "src/pkg/__init__.py",
    "src/pkg/core.py",
    "src/pkg/util/helpers.py",
    "web/src/api.ts",
    "web/src/components/index.ts",
    "web/src/components/Button.tsx",
    "app/src/main/java/com/acme/billing/Invoice.java",
    "server/internal/store/db.go",
    "other/core.py",
    "a/lib/core.ts",
    "b/lib/core.ts",
]


@pytest.mark.parametrize(
    ("importer", "tried", "relative", "style", "expected"),
    [
        ("src/pkg/core.py", ("pkg/util/helpers",), False, "python", ["src/pkg/util/helpers.py"]),
        ("src/pkg/util/helpers.py", ("../core",), True, "python", ["src/pkg/core.py"]),
        ("src/pkg/core.py", ("pkg/missing", "pkg"), False, "python", ["src/pkg/__init__.py"]),
        ("web/src/api.ts", ("./components",), True, "path", ["web/src/components/index.ts"]),
        (
            "web/src/api.ts",
            ("@/components/Button",),
            False,
            "path",
            ["web/src/components/Button.tsx"],
        ),
        ("web/src/api.ts", ("react",), False, "path", []),
        (
            "server/main.go",
            ("github.com/acme/server/internal/store",),
            False,
            "go",
            ["server/internal/store/db.go"],
        ),
        (
            "app/src/main/java/com/acme/App.java",
            ("com.acme.billing.Invoice.TAX",),
            False,
            "qualified",
            ["app/src/main/java/com/acme/billing/Invoice.java"],
        ),
        ("x/y.py", ("core",), False, "python", ["other/core.py"]),  # src/pkg is a package
        ("web/src/api.ts", ("lib/core",), False, "path", []),  # two equally near matches
    ],
)
def test_resolver_links_imports_to_repository_files(importer, tried, relative, style, expected):
    assert Resolver(PATHS).resolve(importer, tried, relative, style) == expected


def test_partition_caps_modules_and_covers_every_file():
    paths = [f"pkg{i}/sub{j}/f{k}.py" for i in range(5) for j in range(4) for k in range(2)]
    module_of = _partition(paths)
    assert 5 < len(set(module_of.values())) <= MAX_MODULES
    assert all(in_scope(p, module_of[p]) for p in paths)
    paths = [f"pkg{i}/f.py" for i in range(20)]  # the root is split even past the cap
    module_of = _partition(paths)
    assert len(set(module_of.values())) == 20
    assert all(in_scope(p, module_of[p]) for p in paths)
    assert in_scope("a/b/c.py", "a/**") and not in_scope("a/b/c.py", "a/*")


def test_layers_put_callers_above_callees_and_merge_cycles():
    height = _layers(
        ["app", "a", "b", "base"], {("app", "a"), ("a", "b"), ("b", "a"), ("b", "base")}
    )
    assert height["app"] > height["a"] == height["b"] > height["base"] == 0


REPO = {
    "app/main.py": (
        "from fastapi import FastAPI\n"
        "from app.services.billing import charge\n\n"
        "def main():\n    charge(1)\n"
    ),
    "app/services/billing.py": (
        "import sqlalchemy\n"
        "from ..data.store import Store\n\n"
        "def charge(amount):\n    store = Store()\n    store.save(amount)\n    cache.get(amount)\n"
    ),
    "app/data/store.py": (
        "class Store:\n    def save(self, amount):\n        return self.get(amount)\n\n"
        "    def get(self, amount):\n        return amount\n"
    ),
    "app/data/other.py": "def charge(amount):\n    return amount\n",
    "web/src/main.tsx": (
        "import React from 'react'\nimport { charge } from './pay'\n\nexport function App() {\n"
        "  charge()\n}\n"
    ),
    "web/src/pay.ts": "export function charge() {\n  return fetch('/api')\n}\n",
    "tests/test_billing.py": "from app.services.billing import charge\n",
}


def test_architecture_endpoint_maps_modules_links_and_flows(client):
    snapshot = upload(client, REPO).json()
    data = client.get(f"/api/snapshots/{snapshot['snapshot_id']}/architecture").json()
    modules = {m["id"]: m for m in data["modules"]}
    assert all(not m.startswith("tests") for m in modules)  # tests are left out
    edges = {(e["source"], e["target"]) for e in data["edges"]}
    assert ("app/main.py", "app/services/billing.py") in edges  # small repos map files
    assert ("app/services/billing.py", "app/data/store.py") in edges
    assert not any("web" in a and "app" in b or "app" in a and "web" in b for a, b in edges)
    assert modules["app/main.py"]["entry"] == ["main.py"]
    assert {"role": "API", "labels": ["FastAPI"]} in data["stack"]
    flows = [[s["symbol"] for s in f] for f in data["flows"]]
    # `cache.get` is a built-in style call, so it is not linked to Store.get from outside.
    assert ["main", "charge", "Store.save", "Store.get"] in flows
    for flow in data["flows"]:  # TypeScript calls stay in TypeScript
        assert len({s["path"].startswith("web/") for s in flow}) == 1
    by_title = {g["title"]: g for g in data["groups"]}
    assert by_title["app"]["rows"][0] == ["app/main.py"]


def test_search_can_be_scoped_to_a_module(client):
    snapshot = upload(client, REPO).json()
    params = {"snapshot_id": snapshot["snapshot_id"], "q": "charge"}
    everywhere = {r["path"] for r in client.get("/api/search", params=params).json()["results"]}
    scoped = client.get("/api/search", params={**params, "scope": "web/src/**"}).json()
    assert {"app/services/billing.py", "web/src/pay.ts"} <= everywhere
    assert scoped["scope"] == "web/src/**"
    assert {r["path"] for r in scoped["results"]} <= {"web/src/main.tsx", "web/src/pay.ts"}
    assert scoped["results"]


def test_decorators_and_plain_calls_do_not_invent_flow_steps(client):
    repo = {
        "a/cli.py": (
            "from b.jobs import Job\n\nclass Group:\n"
            "    def command(self):\n        return Job().process()\n\n"
            "group = Group()\n\n@group.command()\ndef serve():\n    return process()\n"
        ),
        "b/jobs.py": (
            "class Job:\n    def process(self):\n        return finish()\n\n"
            "def finish():\n    return 1\n"
        ),
    }
    snapshot = upload(client, repo).json()
    data = client.get(f"/api/snapshots/{snapshot['snapshot_id']}/architecture").json()
    flows = [[s["symbol"] for s in f] for f in data["flows"]]
    assert ["Group.command", "Job.process", "finish"] in flows
    # neither the decorator nor the plain `process()` call is a step out of serve
    assert all("serve" not in f for f in flows)


def test_zipped_package_folder_with_init_at_the_root_imports():
    resolver = Resolver(["__init__.py", "core.py", "util/__init__.py", "util/io.py"])
    assert resolver.resolve("core.py", ("util/io",), False, "python") == ["util/io.py"]


def test_python_calls_need_an_import_but_follow_package_reexports(client):
    repo = {
        "lib/__init__.py": "from .core import make\n",
        "lib/core.py": "def make():\n    return 1\n\ndef get_version():\n    return 2\n",
        "app/run.py": "from lib import make\n\ndef main():\n    return make()\n",
        "docs/conf.py": "from theme import get_version\n\ndef setup():\n    return get_version()\n",
    }
    snapshot = upload(client, repo).json()
    data = client.get(f"/api/snapshots/{snapshot['snapshot_id']}/architecture").json()
    calls = {(e["source"], e["target"]) for e in data["edges"] if e["calls"]}
    assert ("app/run.py", "lib/core.py") in calls  # `make` is re-exported by lib/__init__.py
    assert all(source != "docs/conf.py" for source, _ in calls)  # get_version is external


def test_flow_steps_carry_doc_summaries_and_call_lines(client):
    repo = {
        "web/main.ts": (
            "import { charge } from './billing'\n\n// eslint-disable-next-line\n"
            "/** Starts the app. Extra text. */\nexport function main() {\n  return charge()\n}\n"
        ),
        "web/billing.ts": (
            "import { save } from './store'\n\n/**\n * Charges the :class:`.Card`\n"
            " * and records it.\n * @param x ignored\n */\nexport function charge() {\n"
            "  const a = 1\n  return save()\n}\n"
        ),
        "web/store.ts": "export function save() {\n  return 1\n}\n",
        "a/main.py": (
            'from b.svc import run_job\n\ndef main():\n    """Entry point."""\n'
            "    return run_job()\n"
        ),
        "b/svc.py": (
            "from c.db import put\n\ndef run_job(\n    x=1,\n) -> int:  # noqa\n"
            '    """\n    Run the job\n    now.\n\n    More.\n    """\n    return put()\n'
        ),
        "c/db.py": "def put():\n    # not a docstring\n    return 'x'\n",
    }
    snapshot = upload(client, repo).json()
    data = client.get(f"/api/snapshots/{snapshot['snapshot_id']}/architecture").json()
    steps = {
        s["path"]: (s["doc"], s["line"], s["end"], s["calls_at"]) for f in data["flows"] for s in f
    }
    assert steps["web/main.ts"] == ("Starts the app.", 3, 7, 6)
    assert steps["web/billing.ts"] == ("Charges the Card and records it.", 3, 11, 10)
    assert steps["web/store.ts"] == (None, 1, 3, None)
    assert steps["a/main.py"][::3] == ("Entry point.", 5)
    assert steps["b/svc.py"][0] == "Run the job now."
    assert steps["c/db.py"][0] is None
