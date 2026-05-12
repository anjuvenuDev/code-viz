from __future__ import annotations

import ast
import os
import re
from pathlib import Path

from .graph import DependencyGraph


SKIP_DIRS = {
    ".agents",
    ".codex",
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".svn",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "venv",
}

CODE_EXTENSIONS = {
    ".c",
    ".cc",
    ".cfg",
    ".cpp",
    ".cs",
    ".css",
    ".go",
    ".h",
    ".hpp",
    ".html",
    ".java",
    ".js",
    ".json",
    ".jsx",
    ".kt",
    ".lua",
    ".md",
    ".mjs",
    ".php",
    ".py",
    ".rb",
    ".rs",
    ".scss",
    ".sh",
    ".svelte",
    ".toml",
    ".ts",
    ".tsx",
    ".vue",
    ".yaml",
    ".yml",
}

CODE_FILENAMES = {
    "Dockerfile",
    "Makefile",
    "Rakefile",
}

IMPORT_PATH_RE = re.compile(
    r"""
    (?:
        import\s+(?:type\s+)?(?:[\w*{}\s,$]+\s+from\s+)?|
        export\s+(?:type\s+)?(?:[\w*{}\s,$]+\s+from\s+)|
        require\s*\(|
        import\s*\(|
        @import\s+
    )
    ["']([^"']+)["']
    """,
    re.VERBOSE,
)
GENERIC_RELATIVE_PATH_RE = re.compile(r"""["']((?:\./|\.\./|/)[^"'#?]+)["']""")


def build_graph(root: Path) -> DependencyGraph:
    files = _discover_files(root)
    graph = DependencyGraph()
    id_by_path = {_relative_id(root, path): path for path in files}

    for node_id in sorted(id_by_path):
        graph.add_node(node_id)

    known_ids = set(id_by_path)
    known_paths = set(files)

    for source_id, source_path in sorted(id_by_path.items()):
        for target_path, kind in _find_references(root, source_path, known_paths):
            target_id = _relative_id(root, target_path)
            if target_id in known_ids:
                graph.add_edge(source_id, target_id, kind)

    return graph


def _discover_files(root: Path) -> list[Path]:
    files: list[Path] = []
    for current_root, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(
            dirname
            for dirname in dirnames
            if dirname not in SKIP_DIRS and not dirname.startswith(".cache")
        )
        current = Path(current_root)
        for filename in sorted(filenames):
            path = current / filename
            if _is_code_file(path) and _looks_textual(path):
                files.append(path.resolve())
    return files


def _is_code_file(path: Path) -> bool:
    return path.name in CODE_FILENAMES or path.suffix.lower() in CODE_EXTENSIONS


def _looks_textual(path: Path) -> bool:
    try:
        sample = path.read_bytes()[:2048]
    except OSError:
        return False
    return b"\0" not in sample


def _find_references(
    root: Path, source_path: Path, known_paths: set[Path]
) -> list[tuple[Path, str]]:
    try:
        text = source_path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        try:
            text = source_path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            return []
    except OSError:
        return []

    references: list[tuple[Path, str]] = []

    if source_path.suffix == ".py":
        references.extend(_python_import_references(root, source_path, text, known_paths))

    for import_path in IMPORT_PATH_RE.findall(text):
        resolved = _resolve_import_path(root, source_path, import_path, known_paths)
        if resolved is not None:
            references.append((resolved, "import"))

    for raw_path in GENERIC_RELATIVE_PATH_RE.findall(text):
        resolved = _resolve_relative_file(root, source_path, raw_path, known_paths)
        if resolved is not None:
            references.append((resolved, "path"))

    return sorted(set(references), key=lambda item: str(item[0]))


def _python_import_references(
    root: Path, source_path: Path, text: str, known_paths: set[Path]
) -> list[tuple[Path, str]]:
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return []

    references: list[tuple[Path, str]] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                resolved = _resolve_python_module(root, alias.name, known_paths)
                if resolved is not None:
                    references.append((resolved, "import"))
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level:
                module = _resolve_relative_python_module(root, source_path, node.level, module)
            resolved = _resolve_python_module(root, module, known_paths)
            if resolved is not None:
                references.append((resolved, "import"))

            for alias in node.names:
                if alias.name == "*":
                    continue
                child_module = f"{module}.{alias.name}" if module else alias.name
                resolved = _resolve_python_module(root, child_module, known_paths)
                if resolved is not None:
                    references.append((resolved, "import"))

    return references


def _resolve_relative_python_module(
    root: Path, source_path: Path, level: int, module: str
) -> str:
    package_parts = list(source_path.parent.relative_to(root).parts)
    hops = max(level - 1, 0)
    if hops:
        package_parts = package_parts[:-hops]
    rel_parts = list(package_parts)
    if module:
        rel_parts.extend(module.split("."))
    return ".".join(rel_parts)


def _resolve_python_module(
    root: Path, module: str, known_paths: set[Path]
) -> Path | None:
    if not module:
        return None

    parts = module.split(".")
    candidates = [
        root.joinpath(*parts).with_suffix(".py"),
        root.joinpath(*parts, "__init__.py"),
    ]
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in known_paths:
            return resolved
    return None


def _resolve_import_path(
    root: Path, source_path: Path, import_path: str, known_paths: set[Path]
) -> Path | None:
    if import_path.startswith(".") or import_path.startswith("/"):
        return _resolve_relative_file(root, source_path, import_path, known_paths)

    # Package-style imports can still point to files inside this repo.
    package_path = root / import_path
    return _resolve_candidate(package_path, known_paths)


def _resolve_relative_file(
    root: Path, source_path: Path, raw_path: str, known_paths: set[Path]
) -> Path | None:
    if raw_path.startswith("/"):
        candidate = root / raw_path.lstrip("/")
    else:
        candidate = source_path.parent / raw_path
    return _resolve_candidate(candidate, known_paths)


def _resolve_candidate(candidate: Path, known_paths: set[Path]) -> Path | None:
    candidate = candidate.resolve()
    if not candidate.name:
        return None

    candidates = [candidate]

    if candidate.suffix:
        candidates.append(candidate.with_suffix(""))
    else:
        for suffix in CODE_EXTENSIONS:
            candidates.append(candidate.with_suffix(suffix))
        for suffix in CODE_EXTENSIONS:
            candidates.append(candidate / f"index{suffix}")
            candidates.append(candidate / f"__init__{suffix}")

    for item in candidates:
        resolved = item.resolve()
        if resolved in known_paths:
            return resolved
    return None


def _relative_id(root: Path, path: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()
