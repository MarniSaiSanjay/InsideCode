"""Supported languages. Adding one means adding one `Language` entry to LANGUAGES.

Python is parsed with `ast`. Other languages use per-line definition regexes (each with a
`name` group and an optional `owner` group, e.g. a Go receiver or C++ `Class::`) applied to
the source with comments and strings blanked, plus a block style that finds where a
definition ends: "braces" (matching `{}`) or "end" (Ruby: the `end` at the same indent).
"""

import re
from dataclasses import dataclass
from fnmatch import fnmatchcase
from pathlib import PurePosixPath


def _rx(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(r"\s*" + p) for p in patterns)


@dataclass(frozen=True)
class Language:
    name: str
    extensions: tuple[str, ...]
    blocks: str = "braces"  # "ast" (Python), "braces", or "end"
    classes: tuple[re.Pattern[str], ...] = ()  # class/struct/interface/enum/trait/impl
    functions: tuple[re.Pattern[str], ...] = ()  # functions and methods
    tests: tuple[str, ...] = ()  # file-name globs for test files
    quotes: str = "\"'"  # string delimiters blanked before matching
    comments: tuple[str, ...] = ("//",)  # line comments; /* */ is always blanked


JS_NAME = r"[A-Za-z_$#][\w$]*"
# Type with optional generics, e.g. `Map<String, List<User>>` (Java, C#).
TYPE = r"[\w.$?\[\]]+(?:<.*?>)?[?\[\]]*\s+"
JAVA_MODS = r"(?:(?:public|protected|private|internal|static|final|abstract|synchronized|native|"
JAVA_MODS += r"default|virtual|override|sealed|async|extern|unsafe|new|partial|readonly)\s+)*"
SWIFT_MODS = r"(?:@\w+\s+)*(?:(?:public|private|fileprivate|internal|open|final|static|class|"
SWIFT_MODS += r"override|mutating|nonmutating|convenience|required)\s+)*"

LANGUAGES = (
    Language(
        "Python",
        (".py",),
        blocks="ast",
        tests=("test_*.py", "*_test.py", "conftest.py"),
    ),
    Language(
        "JavaScript/TypeScript",
        (".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx"),
        classes=_rx(
            r"(?:(?:export|default|declare|abstract)\s+)*(?:class|interface|enum)\s+"
            rf"(?P<name>{JS_NAME})"
        ),
        functions=_rx(
            rf"(?:(?:export|default|async)\s+)*function\s*\*?\s*(?P<name>{JS_NAME})",
            # const f = (...) => {, app.handle = async function () {
            r"(?:(?:export|const|let|var|public|private|protected|static|readonly)\s+)*"
            rf"(?:(?P<owner>{JS_NAME}(?:\.{JS_NAME})*)\.)?"
            rf"(?P<name>{JS_NAME})\s*(?::[^=]+)?=\s*(?:async\s+)?"
            r"(?:function\b|(?=\()|[A-Za-z_$][\w$]*\s*=>)",
            # class and object-literal methods
            r"(?:(?:public|private|protected|static|async|readonly|override|abstract|get|set)"
            rf"\s+)*\*?(?P<name>{JS_NAME})\s*(?=[(<])",
        ),
        tests=("*.test.*", "*.spec.*"),
        quotes="\"'`",
    ),
    Language(
        "Java",
        (".java",),
        classes=_rx(
            r"(?:@\w+\s+)*(?:(?:public|protected|private|static|final|abstract|sealed|"
            r"non-sealed|strictfp)\s+)*(?:class|interface|enum|record|@interface)\s+(?P<name>\w+)"
        ),
        functions=_rx(rf"(?:@\w+\s+)*{JAVA_MODS}(?:<[^>]*>\s+)?(?:{TYPE})?(?P<name>\w+)(?=\s*\()"),
        tests=("*Test.java", "*Tests.java"),
    ),
    Language(
        "Kotlin",
        (".kt", ".kts"),
        classes=_rx(
            r"(?:(?:public|private|protected|internal|abstract|open|final|sealed|data|enum|"
            r"annotation|inner|value|inline|fun)\s+)*(?:class|interface|object)\s+(?P<name>\w+)"
        ),
        functions=_rx(
            r"(?:(?:public|private|protected|internal|open|override|abstract|final|suspend|"
            r"inline|operator|infix|tailrec|external)\s+)*fun\s+(?:<[^>]*>\s*)?"
            r"(?:[\w.<>?]+\.)?(?P<name>\w+)(?=\s*\()"
        ),
        tests=("*Test.kt", "*Tests.kt"),
        quotes="\"'`",
    ),
    Language(
        "Go",
        (".go",),
        classes=_rx(r"type\s+(?P<name>\w+)(?:\[[^\]]*\])?\s+(?:struct|interface)\b"),
        functions=_rx(r"func\s+(?:\(\s*(?:\w+\s+)?\*?(?P<owner>\w+)[^)]*\)\s*)?(?P<name>\w+)"),
        tests=("*_test.go",),
        quotes="\"'`",
    ),
    Language(
        "C#",
        (".cs",),
        classes=_rx(
            r"(?:\[.*\]\s*)?(?:(?:public|private|protected|internal|static|abstract|sealed|"
            r"partial|readonly|ref|unsafe|new|file)\s+)*"
            r"(?:class|struct|interface|enum|record(?:\s+(?:class|struct))?)\s+(?P<name>\w+)"
        ),
        functions=_rx(rf"{JAVA_MODS}(?:{TYPE})?(?P<name>\w+)\s*(?:<[^>]*>)?(?=\s*\()"),
        tests=("*Test.cs", "*Tests.cs"),
    ),
    Language(
        "C/C++",
        (".c", ".h", ".cc", ".cpp", ".cxx", ".hpp", ".hh"),
        classes=_rx(
            r"(?:template\s*<.*>\s*)?(?:typedef\s+)?(?:class|struct|union|enum(?:\s+class)?)\s+"
            r"(?:\w+\s+)?(?P<name>\w+)\s*(?:final\s*)?(?=[:{]|$)"
        ),
        functions=_rx(
            # return type, optional `Owner::`, name: `static int Foo::bar(`
            r"(?:[\w~][\w:<>,~]*[\s*&]+)+(?:(?P<owner>[\w:]+)::)?(?P<name>~?\w+)(?=\s*\()",
            # constructors and destructors defined outside the class: `Foo::Foo(`
            r"(?P<owner>[\w:]+)::(?P<name>~?\w+)(?=\s*\()",
        ),
        tests=("*_test.*", "*_unittest.*", "test_*"),
    ),
    Language(
        "Rust",
        (".rs",),
        classes=_rx(
            r"(?:pub(?:\([^)]*\))?\s+)?(?:unsafe\s+)?(?:struct|enum|trait|union)\s+(?P<name>\w+)",
            r"(?:unsafe\s+)?impl(?:\s*<.*?>)?\s+(?:[\w:<>,\s']+?\s+for\s+)?(?:\w+::)*(?P<name>\w+)",
        ),
        functions=_rx(
            r"(?:pub(?:\([^)]*\))?\s+)?(?:(?:const|async|unsafe|extern)\s+)*fn\s+(?P<name>\w+)"
        ),
        quotes='"',  # a single quote is usually a lifetime ('a), not a string
    ),
    Language(
        "PHP",
        (".php",),
        classes=_rx(
            r"(?:(?:abstract|final|readonly)\s+)*(?:class|interface|trait|enum)\s+(?P<name>\w+)"
        ),
        functions=_rx(
            r"(?:(?:public|private|protected|static|abstract|final)\s+)*function\s+&?(?P<name>\w+)"
        ),
        tests=("*Test.php",),
        comments=("//", "#"),
    ),
    Language(
        "Swift",
        (".swift",),
        classes=_rx(
            r"(?:(?:public|private|fileprivate|internal|open|final|indirect)\s+)*"
            r"(?:class|struct|enum|protocol|extension|actor)\s+(?P<name>\w+)"
        ),
        functions=_rx(
            SWIFT_MODS + r"func\s+(?P<name>\w+)",
            SWIFT_MODS + r"(?P<name>init|deinit)\b",
        ),
        tests=("*Tests.swift", "*Test.swift"),
        quotes='"',
    ),
    Language(
        "Ruby",
        (".rb",),
        blocks="end",
        classes=_rx(r"(?:class|module)\s+(?P<name>[A-Z][\w:]*)"),
        functions=_rx(r"def\s+(?:self\.)?(?P<name>\w+[?!]?)"),
        tests=("*_spec.rb", "*_test.rb", "test_*.rb"),
        comments=("#",),
    ),
)

BY_EXTENSION = {ext: lang for lang in LANGUAGES for ext in lang.extensions}
TEST_DIRS = {"test", "tests", "__tests__", "spec", "specs"}


def language_for(path: str) -> Language | None:
    return BY_EXTENSION.get(PurePosixPath(path).suffix.lower())


def is_test_path(path: str) -> bool:
    *dirs, name = PurePosixPath(path).parts
    lang = language_for(path)
    return bool(TEST_DIRS & {d.lower() for d in dirs}) or any(
        fnmatchcase(name, pattern) for pattern in (lang.tests if lang else ())
    )
