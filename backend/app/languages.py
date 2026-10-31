"""Supported languages. Adding one means adding one `Language` entry to LANGUAGES.

Python is parsed with `ast`; the others with their official tree-sitter grammar (bundled
wheels, nothing is downloaded). `classes` and `functions` name the grammar's node types for
definitions, which become the searchable code regions. `imports` and `calls` are query
patterns for the architecture view (patterns a grammar lacks are skipped):
@import is a module or path, @relative a path from the importing file, @call a plain call or
construction, @method a call on a receiver.
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
    imports: tuple[str, ...] = ()
    calls: tuple[str, ...] = ()
    import_style: str = "path"  # how @import resolves; see architecture.Resolver
    package_scope: bool = False  # files in one folder use each other without imports


JS_FUNCTIONS = _types("function_declaration generator_function_declaration method_definition")
JS_IMPORTS = (
    "(import_statement source: (string (string_fragment) @import))",
    "(export_statement source: (string (string_fragment) @import))",
    "(import_require_clause source: (string (string_fragment) @import))",
    "(call_expression function: [(identifier) (import)] @_f arguments: (arguments"
    ' . (string (string_fragment) @import)) (#match? @_f "^(require|import)$"))',
)
JS_CALLS = (
    "(call_expression function: (identifier) @call)",
    "(call_expression function: (member_expression property: (property_identifier) @method))",
    "(new_expression constructor: (identifier) @call)",
    "(new_expression constructor: (member_expression property: (property_identifier) @method))",
    "(jsx_opening_element name: (identifier) @call)",
    "(jsx_self_closing_element name: (identifier) @call)",
)
PHP_INCLUDES = tuple(
    f"({node} [(string (string_content) @relative) (encapsed_string (string_content) @relative)"
    " (binary_expression right: [(string (string_content) @relative)"
    " (encapsed_string (string_content) @relative)])])"
    for node in (
        "require_expression", "require_once_expression", "include_expression",
        "include_once_expression",
    )
)  # fmt: skip

LANGUAGES = (
    Language(
        "Python",
        {".py": ""},
        tests=("test_*.py", "*_test.py", "conftest.py"),
        import_style="python",
    ),
    Language(
        "JavaScript",
        _same("tree_sitter_javascript", ".js", ".jsx", ".mjs", ".cjs"),
        _types("class_declaration"),
        JS_FUNCTIONS,
        tests=("*.test.*", "*.spec.*"),
        imports=JS_IMPORTS,
        calls=JS_CALLS,
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
        imports=JS_IMPORTS,
        calls=JS_CALLS,
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
        imports=(
            "(import_declaration (scoped_identifier) @import)",
            "(import_declaration (identifier) @import)",
        ),
        calls=(
            "(method_invocation !object name: (identifier) @call)",
            "(method_invocation object: (_) name: (identifier) @method)",
            "(object_creation_expression type: (type_identifier) @call)",
            "(object_creation_expression type: (generic_type (type_identifier) @call))",
        ),
        import_style="qualified",
        package_scope=True,
    ),
    Language(
        "Kotlin",
        _same("tree_sitter_kotlin", ".kt", ".kts"),
        _types("class_declaration object_declaration companion_object"),
        _types("function_declaration secondary_constructor"),
        tests=("*Test.kt", "*Tests.kt"),
        imports=("(import (qualified_identifier) @import)",),
        calls=(
            "(call_expression . (identifier) @call)",
            "(call_expression . (navigation_expression (identifier) @method .))",
        ),
        import_style="qualified",
        package_scope=True,
    ),
    Language(
        "Go",
        {".go": "tree_sitter_go"},
        _types("type_spec"),
        _types("function_declaration method_declaration"),
        tests=("*_test.go",),
        imports=(
            "(import_spec path: (interpreted_string_literal"
            " (interpreted_string_literal_content) @import))",
        ),
        calls=(
            "(call_expression function: (identifier) @call)",
            "(call_expression function: (selector_expression field: (field_identifier) @method))",
            "(composite_literal type: (type_identifier) @call)",
            "(composite_literal type: (qualified_type name: (type_identifier) @method))",
        ),
        import_style="go",
        package_scope=True,
    ),
    Language(
        "PHP",
        {".php": "tree_sitter_php:language_php"},
        _types("class_declaration interface_declaration trait_declaration enum_declaration"),
        _types("function_definition method_declaration"),
        tests=("*Test.php",),
        imports=(
            "(namespace_use_declaration (namespace_use_clause [(qualified_name) (name)] @import))",
            "(namespace_use_declaration (namespace_name) @import)",
            *PHP_INCLUDES,
        ),
        calls=(
            "(function_call_expression function: (name) @call)",
            "(function_call_expression function: (qualified_name (name) @call .))",
            "(object_creation_expression (name) @call)",
            "(object_creation_expression (qualified_name (name) @call .))",
            "(member_call_expression name: (name) @method)",
            "(nullsafe_member_call_expression name: (name) @method)",
            "(scoped_call_expression name: (name) @method)",
        ),
        import_style="qualified",
        package_scope=True,
    ),
    Language(
        "Swift",
        {".swift": "tree_sitter_swift"},
        _types("class_declaration protocol_declaration"),
        _types("function_declaration init_declaration deinit_declaration"),
        tests=("*Tests.swift", "*Test.swift"),
        imports=("(import_declaration (identifier) @import)",),
        calls=(
            "(call_expression . (simple_identifier) @call)",
            "(call_expression . (navigation_expression suffix: (navigation_suffix"
            " suffix: (simple_identifier) @method)))",
        ),
        import_style="qualified",
        package_scope=True,
    ),
    Language(
        "Ruby",
        {".rb": "tree_sitter_ruby"},
        _types("class module"),
        _types("method singleton_method"),
        tests=("*_spec.rb", "*_test.rb", "test_*.rb"),
        imports=(
            "(call !receiver method: (identifier) @_m"
            ' arguments: (argument_list . (string (string_content) @import)) (#eq? @_m "require"))',
            "(call !receiver method: (identifier) @_m arguments: (argument_list"
            ' . (string (string_content) @relative)) (#eq? @_m "require_relative"))',
        ),
        calls=(
            "(call !receiver method: (identifier) @call)",
            "(call receiver: (_) method: (identifier) @method)",
            "(call receiver: [(constant) @call (scope_resolution name: (constant) @call)]"
            ' method: (identifier) @_n (#eq? @_n "new"))',
        ),
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
