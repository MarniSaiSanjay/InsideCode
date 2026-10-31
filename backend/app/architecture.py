"""Architecture overview from the imports and calls the parser found (static analysis).

Modules are folders, or the files of a small repository. A module uses another when its code
imports or calls code there. Layers stack linked modules from entry points down to shared
foundations; flows follow resolved calls between definitions. Names are only linked when the
match is unambiguous, so the view may miss links but should not invent them.
"""

import re
from collections import Counter, defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from functools import cache
from itertools import takewhile
from pathlib import PurePosixPath

from .indexing import Facts
from .languages import BY_EXTENSION, language_for

MAX_MODULES = 14
MAX_KEY = 3
WORD = re.compile(r"\w+")
# Languages that call each other directly.
FAMILY = {"TypeScript": "JavaScript", "Kotlin": "Java"}
# Method names built-in types share (and dunders, e.g. super().__init__); such a call is only
# linked inside the caller's own class.
COMMON_METHODS = frozenset(
    "add append apply bind call clear close copy count decode delete dump dumps encode equals"
    " extend filter find forEach format get has hashCode index insert items join keys length"
    " load loads map open pop push put read reduce remove replace resolve run send set size"
    " slice sort split strip then toString update values write".split()
)
MAX_FLOWS = 3
MAX_FLOW_STEPS = 6
MAX_DOC = 110
DOCSTRING = re.compile(r"""^[rRuUbBfF]?(\"\"\"|\'\'\'|\"|\')""")
COMMENT = re.compile(r"^(/\*\*?|\*/?|///?|#(?!!)|--)")
ROLE = re.compile(r":[\w:]+:`[~.]*([^`]+)`")
DIRECTIVE = re.compile(r"^(eslint|prettier|noqa|type:|pragma|pylint|TODO|FIXME|-\*-)", re.I)
INDEX_STEMS = {"__init__", "index"}
ENTRY_STEMS = {"__main__", "main", "manage", "wsgi", "asgi", "server", "program", "cli"}
WEAK_ENTRY_STEMS = {"app", "index"}  # entry points only when nothing imports them
ENTRY_MARK = re.compile(r"""__name__\s*==\s*['"]__main__['"]|^@main\b""", re.M)
ROLES = ("UI", "API", "Network", "Data", "Jobs", "AI", "CLI")
# (role, label, import prefixes) for well-known frameworks and services.
STACK = (
    ("UI", "React", "react react-dom react-native"),
    ("UI", "Vue", "vue"),
    ("UI", "Angular", "@angular/core"),
    ("UI", "Svelte", "svelte"),
    ("UI", "Next.js", "next"),
    ("UI", "Jetpack Compose", "androidx/compose"),
    ("UI", "Android", "android"),
    ("UI", "SwiftUI", "SwiftUI"),
    ("UI", "UIKit", "UIKit"),
    ("UI", "Streamlit", "streamlit"),
    ("UI", "Tkinter", "tkinter"),
    ("UI", "Jinja", "jinja2"),
    ("API", "FastAPI", "fastapi"),
    ("API", "Flask", "flask"),
    ("API", "Django", "django"),
    ("API", "Starlette", "starlette"),
    ("API", "Werkzeug", "werkzeug"),
    ("API", "aiohttp", "aiohttp"),
    ("API", "Express", "express"),
    ("API", "Fastify", "fastify"),
    ("API", "Koa", "koa"),
    ("API", "NestJS", "@nestjs/core @nestjs/common"),
    ("API", "Spring", "org/springframework"),
    ("API", "Ktor", "io/ktor"),
    ("API", "Gin", "github.com/gin-gonic/gin"),
    ("API", "Echo", "github.com/labstack/echo"),
    ("API", "Fiber", "github.com/gofiber/fiber"),
    ("API", "net/http", "net/http"),
    ("API", "Laravel", "Illuminate"),
    ("API", "Symfony", "Symfony"),
    ("API", "Sinatra", "sinatra"),
    ("API", "Vapor", "Vapor"),
    ("Network", "HTTPX", "httpx"),
    ("Network", "Requests", "requests"),
    ("Network", "Axios", "axios"),
    ("Network", "OkHttp", "okhttp3"),
    ("Network", "Retrofit", "retrofit2"),
    ("Network", "Alamofire", "Alamofire"),
    ("Network", "gRPC", "grpc @grpc/grpc-js google.golang.org/grpc io/grpc"),
    ("Data", "SQLite", "sqlite3 better-sqlite3 GRDB"),
    ("Data", "SQLAlchemy", "sqlalchemy flask_sqlalchemy"),
    ("Data", "PostgreSQL", "psycopg psycopg2 asyncpg pg github.com/lib/pq github.com/jackc/pgx"),
    ("Data", "MySQL", "pymysql mysql mysql2 github.com/go-sql-driver/mysql"),
    ("Data", "MongoDB", "pymongo motor mongodb mongoose go.mongodb.org/mongo-driver"),
    ("Data", "Redis", "redis ioredis github.com/redis/go-redis github.com/go-redis/redis"),
    ("Data", "Prisma", "@prisma/client"),
    ("Data", "TypeORM", "typeorm"),
    ("Data", "Sequelize", "sequelize"),
    ("Data", "Django ORM", "django/db"),
    ("Data", "JDBC", "java/sql"),
    ("Data", "JPA", "javax/persistence jakarta/persistence"),
    ("Data", "Hibernate", "org/hibernate"),
    ("Data", "Room", "androidx/room"),
    ("Data", "database/sql", "database/sql"),
    ("Data", "GORM", "gorm.io/gorm"),
    ("Data", "Core Data", "CoreData"),
    ("Data", "pandas", "pandas"),
    ("Jobs", "Celery", "celery"),
    ("Jobs", "RQ", "rq"),
    ("Jobs", "Dramatiq", "dramatiq"),
    ("Jobs", "Kafka", "kafka confluent_kafka kafkajs"),
    ("Jobs", "RabbitMQ", "pika amqplib"),
    ("Jobs", "BullMQ", "bullmq"),
    ("AI", "OpenAI", "openai"),
    ("AI", "Anthropic", "anthropic @anthropic-ai/sdk"),
    ("AI", "LangChain", "langchain @langchain"),
    ("AI", "PyTorch", "torch"),
    ("AI", "TensorFlow", "tensorflow"),
    ("AI", "Transformers", "transformers"),
    ("AI", "scikit-learn", "sklearn"),
    ("CLI", "Click", "click"),
    ("CLI", "Typer", "typer"),
    ("CLI", "argparse", "argparse"),
    ("CLI", "Commander", "commander"),
    ("CLI", "Cobra", "github.com/spf13/cobra"),
)
STACK_PREFIXES = {
    tuple(prefix.split("/")): (role, label)
    for role, label, prefixes in STACK
    for prefix in prefixes.split()
}

Key = tuple[str, ...]  # path parts, without the extension for files


@dataclass
class FileInfo:
    path: str
    text: str
    definitions: list[tuple[str, str, int, int]]  # (symbol, kind, first line, last line)
    facts: Facts


def _parts(spec: str) -> Key:
    """Path parts of an import, without a source-file extension on the last part."""
    parts = [p for p in spec.split("/") if p]
    if parts and PurePosixPath(parts[-1]).suffix.lower() in BY_EXTENSION:
        parts[-1] = PurePosixPath(parts[-1]).stem
    return tuple(parts)


def _common(a: Key, b: Key) -> int:
    n = 0
    while n < min(len(a), len(b)) and a[n] == b[n]:
        n += 1
    return n


class Resolver:
    """Finds the repository files an import refers to.

    Styles: `path` (JS/TS/Ruby: relative paths, `@/` aliases, multi-part package paths),
    `qualified` (Java/Kotlin/PHP/Swift names that end a repository path), `go` (package paths
    ending in a repository folder) and `python` (dotted module names).
    """

    def __init__(self, paths: list[str]):
        files: dict[Key, list[str]] = defaultdict(list)
        index: dict[Key, list[str]] = defaultdict(list)
        folder: dict[Key, list[str]] = defaultdict(list)
        python: dict[Key, list[str]] = defaultdict(list)
        packages = {p.parent.parts for p in map(PurePosixPath, paths) if p.stem == "__init__"}
        for path in paths:
            pure = PurePosixPath(path)
            files[pure.parent.parts + (pure.stem,)].append(path)
            folder[pure.parent.parts].append(path)
            if pure.stem in INDEX_STEMS:
                index[pure.parent.parts].append(path)
            if pure.suffix == ".py":
                module = [] if pure.stem == "__init__" else [pure.stem]
                parent = pure.parent.parts
                while parent and parent in packages:
                    module.insert(0, parent[-1])
                    parent = parent[:-1]
                python[tuple(module)].append(path)
        # A path names a file, else a folder's index file, else every file in the folder.
        self.targets = {k: files.get(k) or index.get(k) or folder[k] for k in files | folder}
        self.folders = folder
        self.python = python
        self.by_last: dict[str, list[Key]] = defaultdict(list)
        for key in self.targets:
            if key:
                self.by_last[key[-1]].append(key)

    @staticmethod
    def _nearest(options: list[tuple[Key, list[str]]], importer: Key) -> list[str]:
        """Targets closest to the importing file; nothing if that is still ambiguous."""
        if not options:
            return []
        best = max(_common(k, importer) for k, _ in options)
        found = {tuple(t) for k, t in options if _common(k, importer) == best}
        return list(found.pop()) if len(found) == 1 else []

    def _suffix(self, parts: Key, importer: Key, minimum: int) -> list[str]:
        if len(parts) < minimum or not parts:
            return []
        keys = [k for k in self.by_last.get(parts[-1], []) if k[-len(parts) :] == parts]
        return self._nearest([(k, self.targets[k]) for k in keys], importer)

    def _relative(self, spec: str, folder: Key) -> list[str]:
        parts = list(folder)
        for part in spec.split("/"):
            if part == "..":
                if not parts:
                    return []
                parts.pop()
            elif part not in ("", "."):
                parts.append(part)
        return self.targets.get(_parts("/".join(parts)), [])

    def resolve(self, importer: str, tried: tuple[str, ...], relative: bool, style: str):
        folder = PurePosixPath(importer).parent.parts
        if style == "qualified" and not relative:
            spec = tried[0].replace(".", "/")
            tried = (spec, spec.rsplit("/", 1)[0]) if spec.count("/") > 1 else (spec,)
        for spec in tried:
            parts = _parts(spec)
            if relative or spec.startswith("."):
                found = self._relative(spec, folder)
                if not found and relative and not spec.startswith("."):
                    found = self._suffix(parts, folder, 2)  # e.g. PHP include paths
            elif style == "python":
                files = self.python.get(parts, [])
                found = self._nearest([(PurePosixPath(f).parent.parts, [f]) for f in files], folder)
                found = found or self._suffix(parts, folder, 2)  # folders without __init__.py
            elif style == "go":
                tails = [parts[i:] for i in range(len(parts) - 1) if parts[i:] in self.folders]
                found = self.folders[tails[0]] if tails else self._suffix(parts, folder, 2)
            elif style == "qualified":
                found = self._suffix(parts, folder, 1)
            elif spec.startswith(("@/", "~/")):
                found = self._suffix(parts[1:], folder, 1)
            else:
                found = self._suffix(parts, folder, 2)  # one-part names are packages
            if found:
                return [p for p in found if p != importer]
        return []


def _external(tried: tuple[str, ...]) -> tuple[str, str] | None:
    """(role, label) of a well-known framework an unresolved import names."""
    # Python/Java names are dotted; Go domains and JS package names keep their dots.
    for spec in (tried[0].replace(".", "/"), tried[0]):
        parts = tuple(p for p in spec.split("/") if p)
        for n in range(len(parts), 0, -1):
            if found := STACK_PREFIXES.get(parts[:n]):
                return found
    return None


def _partition(paths: list[str]) -> dict[str, str]:
    """Module scope for each path: `dir/**` (all below), `dir/*` (its own files) or a file.

    Folders are split while there are at most MAX_MODULES modules (the repository root is
    always split, even into more); small repositories then
    split folders into their files, largest first, stopping once one no longer fits.
    """
    own: dict[Key, list[str]] = defaultdict(list)
    children: dict[Key, set[Key]] = defaultdict(set)
    size: Counter[Key] = Counter()
    for path in paths:
        folder = PurePosixPath(path).parent.parts
        own[folder].append(path)
        for i in range(len(folder) + 1):
            size[folder[:i]] += 1
            if i:
                children[folder[: i - 1]].add(folder[:i])

    def split(node: tuple[str, Key]) -> list[tuple[str, Key]] | None:
        mode, folder = node
        if mode == "all" and children[folder]:
            kids = [("all", c) for c in sorted(children[folder])]
            return kids + ([("own", folder)] if own[folder] else [])
        if mode in ("all", "own") and own[folder]:
            return [("file", tuple(p.split("/"))) for p in sorted(own[folder])]
        return None

    def count(node: tuple[str, Key]) -> int:
        mode, key = node
        return 1 if mode == "file" else size[key] if mode == "all" else len(own[key])

    modules = [("all", ())]
    for files_too in (False, True):
        while True:
            options = sorted(
                (n for n in modules if (s := split(n)) and (files_too or s[0][0] != "file")),
                key=lambda n: (-count(n), n),
            )
            changed = False
            for node in options:
                parts = split(node) or []
                fits = len(modules) - 1 + len(parts) <= MAX_MODULES
                if len(parts) == 1 or fits or (len(modules) == 1 and not files_too):
                    modules.remove(node)
                    modules += parts
                    changed = True
                    break
                if files_too:
                    break  # keep files of similar folders at one granularity
            if not changed:
                break

    found = {}
    for mode, key in modules:
        joined = "/".join(key)
        if mode == "file":
            found[joined] = joined
            continue
        scope = f"{joined}/**" if mode == "all" else f"{joined}/*"
        for path in paths:
            if in_scope(path, scope.lstrip("/")):
                found.setdefault(path, scope.lstrip("/"))
    return found


def in_scope(path: str, scope: str) -> bool:
    """Whether a file belongs to a module scope (see _partition)."""
    if scope.endswith("**"):
        return path.startswith(scope[:-2])
    if scope.endswith("*"):
        return path.startswith(scope[:-1]) and "/" not in path[len(scope) - 1 :]
    return path == scope


def _label(scope: str) -> str:
    parts = scope.rstrip("*").rstrip("/").split("/")
    return parts[-1] or "(root)"


def _layers(nodes: list[str], edges: set[tuple[str, str]]) -> dict[str, int]:
    """Height above the modules nothing depends on; modules in a cycle share a height."""
    out = defaultdict(set)
    for a, b in edges:
        out[a].add(b)
    # Tarjan's strongly connected components (modules are few, recursion is fine).
    index, low, stack, on, comp = {}, {}, [], set(), {}

    def visit(v):
        index[v] = low[v] = len(index)
        stack.append(v)
        on.add(v)
        for w in out[v]:
            if w not in index:
                visit(w)
                low[v] = min(low[v], low[w])
            elif w in on:
                low[v] = min(low[v], index[w])
        if low[v] == index[v]:
            while True:
                w = stack.pop()
                on.discard(w)
                comp[w] = v
                if w == v:
                    break

    for v in nodes:
        if v not in index:
            visit(v)
    below = defaultdict(set)
    for a, b in edges:
        if comp[a] != comp[b]:
            below[comp[a]].add(comp[b])

    @cache
    def height(c):
        return 1 + max((height(d) for d in below[c]), default=-1)

    return {v: height(comp[v]) for v in nodes}


def _owner_words(path: str, symbol: str) -> set[str]:
    """Names a caller uses to reach a definition: its class, else its file or package."""
    if "." in symbol:
        return {symbol.split(".", 1)[0]}
    parts = PurePosixPath(path)
    return {parts.stem, parts.parent.name}


def build(infos: list[FileInfo], check: Callable[[], None] = lambda: None) -> dict:
    """The architecture overview of the non-test files; `check` can stop a slow build."""
    paths = [i.path for i in infos]
    if not paths:
        return {"modules": [], "edges": [], "groups": [], "stack": [], "flows": []}
    module_of = _partition(paths)
    resolver = Resolver(paths)

    # Imports: file links, and frameworks named by imports outside the repository.
    imported: dict[str, set[str]] = defaultdict(set)
    importers: Counter[str] = Counter()
    stack: dict[str, set[tuple[str, str]]] = defaultdict(set)
    for info in infos:
        lang = language_for(info.path)
        for tried, relative in info.facts.imports:
            found = resolver.resolve(info.path, tried, relative, lang.import_style)
            imported[info.path].update(found)
            if not found and not relative and not tried[0].startswith("."):
                if hit := _external(tried):
                    stack[module_of[info.path]].add(hit)
        for target in imported[info.path]:
            importers[target] += 1

    # Calls: link a name to one definition in the same file, else in files this one can see
    # (imported, or re-exported by an imported index file such as a package `__init__.py`),
    # else (plain calls outside Python, which always imports) the only such definition.
    # A method call into another file also needs its class (or module) named in the caller.
    family = {i.path: FAMILY.get(n := language_for(i.path).name, n) for i in infos}
    names = {i.path: set(WORD.findall(i.text)) for i in infos}
    defs_by_name: dict[tuple[str, str], list[tuple[str, str]]] = defaultdict(list)
    spans = {}
    in_folder: dict[PurePosixPath, set[str]] = defaultdict(set)
    for info in infos:
        in_folder[PurePosixPath(info.path).parent].add(info.path)
        for symbol, kind, first, last in info.definitions:
            defs_by_name[(symbol.rsplit(".", 1)[-1], family[info.path])].append((info.path, symbol))
            spans[(info.path, symbol)] = (kind, first, last)
    # caller -> {callee: first line of the call}
    calls: dict[tuple[str, str], dict[tuple[str, str], int]] = defaultdict(dict)
    top: dict[str, dict[tuple[str, str], int]] = defaultdict(dict)  # calls from top-level code
    file_calls: set[tuple[str, tuple[str, str]]] = set()
    for info in infos:
        check()
        lang = language_for(info.path)
        visible = imported[info.path] | (
            in_folder[PurePosixPath(info.path).parent] if lang.package_scope else set()
        )
        for target in list(imported[info.path]):
            if PurePosixPath(target).stem in INDEX_STEMS:
                visible |= imported[target]
        for (caller, name, method), line in info.facts.calls.items():
            top_level = caller is None
            caller = caller if (info.path, caller) in spans else None
            own = caller.rsplit(".", 1)[0] + "." if caller and "." in caller else None
            inner = (own, caller + ".") if own else (caller + ".",) if caller else ()
            options = [
                d
                for d in defs_by_name.get((name, family[info.path]), [])
                if d != (info.path, caller)
                # a plain call reaches top-level code, or its own class or nested functions
                and (method or "." not in d[1] or (d[0] == info.path and d[1].startswith(inner)))
            ]
            local = [d for d in options if d[0] == info.path]
            if method and (name in COMMON_METHODS or name.startswith("__")):
                options = local = [d for d in local if own and d[1].startswith(own)]
            elif len(local) > 1 and own:  # prefer the caller's own class
                local = [d for d in local if d[1].startswith(own)]
            seen = [d for d in options if d[0] in visible]
            if method:
                seen = [d for d in seen if _owner_words(*d) & names[info.path]]
            target = (
                local[0] if len(local) == 1
                else None if local
                else seen[0] if len(seen) == 1
                else options[0]
                if not seen and not method and len(options) == 1 and lang.import_style != "python"
                else None
            )  # fmt: skip
            if target:
                file_calls.add((info.path, target))
                if caller or top_level:
                    found = calls[(info.path, caller)] if caller else top[info.path]
                    found[target] = min(found.get(target, line), line)

    # Module links.
    links: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for source, targets in imported.items():
        for target in targets:
            if module_of[source] != module_of[target]:
                links[(module_of[source], module_of[target])]["imports"] += 1
    for source, (target, _) in file_calls:
        if module_of[source] != module_of[target]:
            links[(module_of[source], module_of[target])]["calls"] += 1

    # Key definitions: most used from other modules, then other files, then the busiest.
    used_by: dict[tuple[str, str], Counter[str]] = defaultdict(Counter)
    for (path, _), targets in calls.items():
        for target in targets:
            where = "module" if module_of[path] != module_of[target[0]] else "file"
            if where == "module" or path != target[0]:
                used_by[target][where] += 1

    def rank(d: tuple[str, str]):
        kind, first, last = spans[d]
        name = d[1].rsplit(".", 1)[-1]
        return (
            -used_by[d]["module"], -used_by[d]["file"], -len(calls.get(d, ())),
            name.startswith("_"), kind != "class", -(last - first), d,
        )  # fmt: skip

    def entry(info: FileInfo) -> bool:
        stem = PurePosixPath(info.path).stem
        main = any(s == "main" or s.endswith(".main") for s, *_ in info.definitions)
        strong = stem in ENTRY_STEMS or main or ENTRY_MARK.search(info.text)
        return bool(strong or (stem in WEAK_ENTRY_STEMS and not importers[info.path]))

    members: dict[str, list[FileInfo]] = defaultdict(list)
    for info in infos:
        members[module_of[info.path]].append(info)
    edges = set(links)
    sources = Counter(b for _, b in edges)
    top_used = sorted((n for n in sources.values() if n >= 2), reverse=True)[:2]
    labels = Counter(_label(m) for m in members)
    modules = {}
    for scope, files in members.items():
        defs = sorted(((f.path, s) for f in files for s, *_ in f.definitions), key=rank)
        langs = Counter(language_for(f.path).name for f in files)
        label = _label(scope)
        if labels[label] > 1:
            label = "/".join(scope.rstrip("*").rstrip("/").split("/")[-2:])
        modules[scope] = {
            "id": scope,
            "label": label,
            "files": len(files),
            "definitions": len(defs),
            "language": langs.most_common(1)[0][0],
            "entry": sorted(PurePosixPath(f.path).name for f in files if entry(f)),
            "hub": sources[scope] in top_used,
            "stack": sorted({label for _, label in stack[scope]}),
            "key": [_step(d, spans, module_of) for d in defs[:MAX_KEY]],
        }

    # Groups: modules linked to each other, each stacked in layers.
    parent = {m: m for m in modules}

    def root(m):
        while parent[m] != m:
            parent[m] = parent[parent[m]]
            m = parent[m]
        return m

    for a, b in edges:
        parent[root(a)] = root(b)
    grouped: dict[str, list[str]] = defaultdict(list)
    for m in sorted(modules, key=lambda m: -modules[m]["files"]):
        grouped[root(m) if any(m in e for e in edges) else ""].append(m)
    height = _layers(list(modules), edges)
    groups = []
    for key, names in sorted(grouped.items(), key=lambda g: (g[0] == "", -len(g[1]))):
        rows: list[list[str]] = []
        for level in sorted({height[m] for m in names}, reverse=True):
            row = [m for m in names if height[m] == level]
            if rows:  # place under the modules that use them, to reduce crossings
                above = {m: (i + 0.5) / len(r) for r in rows for i, m in enumerate(r)}

                def place(m, above=above):
                    users = [above[a] for a, b in edges if b == m and a in above]
                    return sum(users) / len(users) if users else 2

                row.sort(key=place)
            else:
                row.sort(key=lambda m: (not modules[m]["entry"], -modules[m]["files"]))
            rows.append(row)
        roles = defaultdict(set)
        for m in names:
            for role, label in stack[m]:
                roles[role].add(label)
        groups.append({
            "title": _title(names) if key else "Standalone",
            "stack": [{"role": r, "labels": sorted(roles[r])} for r in ROLES if r in roles],
            "rows": rows if key else [names],
        })  # fmt: skip

    everything = defaultdict(set)
    for hits in stack.values():
        for role, label in hits:
            everything[role].add(label)
    return {
        "modules": list(modules.values()),
        "edges": [
            {"source": a, "target": b, "imports": c["imports"], "calls": c["calls"]}
            for (a, b), c in sorted(links.items())
        ],
        "groups": groups,
        "stack": [{"role": r, "labels": sorted(everything[r])} for r in ROLES if r in everything],
        "flows": _flows(calls, top, spans, module_of, {i.path for i in infos if entry(i)}, infos),
    }


def _title(scopes: list[str]) -> str:
    folders = [tuple(s.rstrip("*").rstrip("/").split("/")) for s in scopes]
    folders = [f[:-1] if "." in f[-1] else f for f in folders]  # files stand for their folder
    common = folders[0]
    for f in folders[1:]:
        common = common[: _common(common, f)]
    return "/".join(p for p in common if p) or "Linked modules"


def _step(d: tuple[str, str], spans: dict, module_of: dict[str, str]) -> dict:
    kind, first, _ = spans[d]
    return {"symbol": d[1], "kind": kind, "path": d[0], "line": first, "module": module_of[d[0]]}


def _flows(
    calls: dict[tuple[str, str], dict[tuple[str, str], int]],
    top: dict[str, dict[tuple[str, str], int]],
    spans: dict,
    module_of: dict[str, str],
    entries: set[str],
    infos: list[FileInfo],
) -> list[list[dict]]:
    """Up to MAX_FLOWS call chains, preferring ones that cross files and start at entry points.

    An entry file's top-level code (e.g. `createApp()` in server/index.js) can start a chain.
    """
    texts = {i.path: i.text for i in infos}
    calls, spans = dict(calls), dict(spans)
    for path in sorted(entries & top.keys()):
        node = (path, PurePosixPath(path).name)
        if node not in spans:
            calls[node] = top[path]
            spans[node] = ("module", 1, len(texts[path].splitlines()))
    called = {t for targets in calls.values() for t in targets}

    @cache
    def best(node: tuple[str, str], steps: int) -> tuple[tuple[str, str], ...]:
        if steps == 1:
            return (node,)
        options = [(node,) + best(t, steps - 1) for t in sorted(calls.get(node, ())) if t != node]
        return max(options, key=_score, default=(node,))

    found = []
    for start in sorted(calls):
        if start in called and start[0] not in entries:
            continue
        path = best(start, MAX_FLOW_STEPS)
        path = path[: next((i for i, d in enumerate(path) if d in path[:i]), len(path))]
        if len(path) >= 3:
            found.append((start[0] in entries, _score(path), path))
    chosen: list[tuple[tuple[str, str], ...]] = []
    # cross-file chains first; chains within one file only fill the remaining places
    order = sorted(found, key=lambda f: (f[1][0] < 2, not f[0], [-x for x in f[1]], f[2]))
    for _, _, path in order:
        if all(path[1] != c[1] and path[0] not in c for c in chosen):
            chosen.append(path)
        if len(chosen) == MAX_FLOWS:
            break
    return [
        [
            _step(d, spans, module_of)
            | {
                "end": spans[d][2],
                "doc": None  # a file's opening comment is often a licence header
                if spans[d][0] == "module"
                else _doc(d[0], texts[d[0]].splitlines(), *spans[d][1:]),
                "calls_at": calls[d][after] if after else None,  # where it calls the next step
            }
            for d, after in zip(path, path[1:] + (None,), strict=True)
        ]
        for path in chosen
    ]


def _doc(path: str, lines: list[str], first: int, last: int) -> str | None:
    """First sentence of a definition's docstring, or of the doc comment next to it."""
    body = lines[first - 1 : min(last, first + 12)]
    if path.endswith((".py", ".pyi")):
        header = next(
            (i for i, b in enumerate(body) if b.split("#")[0].rstrip().endswith(":")), None
        )
        rest = [b for b in body[header + 1 :] if b.strip()] if header is not None else []
        if rest and (opening := DOCSTRING.match(rest[0].strip())):
            quote, doc = opening.group(1), []
            for i, line in enumerate(rest):
                text = line.strip()[opening.end() if i == 0 else 0 :]
                doc.append(text.split(quote)[0])
                if quote in text:
                    break
            return _sentence(doc, DOCSTRING)
    leading = list(takewhile(lambda b: COMMENT.match(b.strip()), body))  # comment inside the span
    above: list[str] = []
    for line in reversed(lines[: first - 1]):
        text = line.strip()
        if text.startswith("@") and not above:  # decorators and annotations
            continue
        if not text or not COMMENT.match(text):
            break
        above.insert(0, line)
    return _sentence(above or leading, COMMENT)


def _sentence(lines: list[str], marker: re.Pattern) -> str | None:
    words = []
    for line in lines:
        text = marker.sub("", line.strip(), count=1).strip()
        text = text.removesuffix("*/").strip()
        if text.startswith("@") or DIRECTIVE.match(text):  # JSDoc tags, lint pragmas
            if words:
                break
            continue
        if not re.search(r"[A-Za-z]", text):
            if words:
                break
            continue
        words.append(text)
        if re.search(r"[.!?]$", text) or len(" ".join(words)) > MAX_DOC:
            break
    text = ROLE.sub(r"\1", " ".join(words)).replace("`", "")  # :class:`.App` -> App
    sentence = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
    return sentence[:MAX_DOC].rstrip() + "…" if len(sentence) > MAX_DOC else sentence or None


def _score(path: tuple[tuple[str, str], ...]) -> tuple[int, int]:
    return len({d[0] for d in path}), len(path)
