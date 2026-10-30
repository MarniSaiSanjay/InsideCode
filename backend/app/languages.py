"""Supported languages. Adding one means adding one `Language` entry to LANGUAGES.

Python is parsed with `ast`; the others with their official tree-sitter grammar (bundled
wheels, nothing is downloaded). `classes` and `functions` name the grammar's node types for
definitions, which become the searchable code regions.
"""

from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


def _types(names: str) -> frozenset[str]:
    return frozenset(names.split())


def _same(grammar: str, *extensions: str) -> dict[str, str]:
    return dict.fromkeys(extensions, grammar)


@dataclass(frozen=True, eq=False)
class Language:
    name: str
    grammars: dict[str, str]  # extension -> "module[:function]" giving the tree-sitter language
    classes: frozenset[str] = frozenset()  # class/struct/interface/enum/trait/impl node types
    functions: frozenset[str] = frozenset()  # function/method/constructor node types
    tests: tuple[str, ...] = ()  # file-name globs for test files


JS_FUNCTIONS = _types("function_declaration generator_function_declaration method_definition")

LANGUAGES = (
    Language("Python", {".py": ""}, tests=("test_*.py", "*_test.py", "conftest.py")),
    Language(
        "JavaScript",
        _same("tree_sitter_javascript", ".js", ".jsx", ".mjs", ".cjs"),
        _types("class_declaration"),
        JS_FUNCTIONS,
        tests=("*.test.*", "*.spec.*"),
    ),
    Language(
        "TypeScript",
        _same("tree_sitter_typescript:language_typescript", ".ts", ".mts", ".cts")
        | {".tsx": "tree_sitter_typescript:language_tsx"},
        _types(
            "class_declaration abstract_class_declaration interface_declaration enum_declaration"
        ),
        JS_FUNCTIONS,
        tests=("*.test.*", "*.spec.*"),
    ),
    Language(
        "Java",
        {".java": "tree_sitter_java"},
        _types(
            "class_declaration interface_declaration enum_declaration record_declaration "
            "annotation_type_declaration"
        ),
        _types("method_declaration constructor_declaration compact_constructor_declaration"),
        tests=("*Test.java", "*Tests.java"),
    ),
    Language(
        "Kotlin",
        _same("tree_sitter_kotlin", ".kt", ".kts"),
        _types("class_declaration object_declaration companion_object"),
        _types("function_declaration secondary_constructor"),
        tests=("*Test.kt", "*Tests.kt"),
    ),
    Language(
        "Go",
        {".go": "tree_sitter_go"},
        _types("type_spec"),
        _types("function_declaration method_declaration"),
        tests=("*_test.go",),
    ),
    Language(
        "PHP",
        {".php": "tree_sitter_php:language_php"},
        _types("class_declaration interface_declaration trait_declaration enum_declaration"),
        _types("function_definition method_declaration"),
        tests=("*Test.php",),
    ),
    Language(
        "Swift",
        {".swift": "tree_sitter_swift"},
        _types("class_declaration protocol_declaration"),
        _types("function_declaration init_declaration deinit_declaration"),
        tests=("*Tests.swift", "*Test.swift"),
    ),
    Language(
        "Ruby",
        {".rb": "tree_sitter_ruby"},
        _types("class module"),
        _types("method singleton_method"),
        tests=("*_spec.rb", "*_test.rb", "test_*.rb"),
    ),
)

BY_EXTENSION = {ext: lang for lang in LANGUAGES for ext in lang.grammars}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}


def language_for(path: str) -> Language | None:
    return BY_EXTENSION.get(PurePosixPath(path).suffix.lower())


def is_test_path(path: str) -> bool:
    *dirs, name = PurePosixPath(path).parts
    lang = language_for(path)
    return bool(TEST_DIRS & {d.lower() for d in dirs}) or any(
        fnmatchcase(name, pattern) for pattern in (lang.tests if lang else ())
    )
