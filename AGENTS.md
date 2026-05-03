# Repository Guidelines

## Project Structure & Module Organization

This is a Python 3.11+ desktop CLI project. The package lives in `code_viz/`:

- `cli.py` defines the `code-viz` command and subcommands.
- `scanner.py`, `graph.py`, and `impact.py` build and analyze dependency graphs.
- `viewer.py` contains the Tkinter desktop UI and SVG/README embedding behavior.
- `__main__.py` supports `python -m code_viz`.

Top-level project metadata is in `pyproject.toml`. `README.md` documents user-facing usage and embeds the generated `code-viz-dependency-graph.svg`. There is currently no committed test directory.

## Build, Test, and Development Commands

- `python -m pip install -e .` installs the local CLI entry point for development.
- `python -m code_viz init` runs the app from the source tree without installation.
- `code-viz init` scans the current directory and opens the desktop dependency graph after editable install.
- `python -m build` builds distribution artifacts if the `build` package is installed.

Run commands from the repository root unless testing the scanner against another target directory.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, type annotations where practical, and `from __future__ import annotations` in modules that use modern typing. Keep module names lowercase with underscores. Use `PascalCase` for classes, `snake_case` for functions, variables, and methods, and uppercase names for constants such as `SKIP_DIRS`.

Prefer `pathlib.Path` for filesystem paths. Keep UI-specific code in `viewer.py` and graph/scanning logic outside the UI layer. Do not commit generated caches such as `__pycache__/`, `.pytest_cache/`, or build outputs.

## Testing Guidelines

No test framework is configured yet. When adding tests, use `pytest` and place them under `tests/` with names like `test_scanner.py` or `test_impact.py`. Focus coverage on dependency parsing, graph relationships, impact reporting, and README/SVG update behavior. Run tests with:

```sh
python -m pytest
```

For UI changes, also run `python -m code_viz init` manually and verify refresh, SVG save, README embed, selection, and pan/zoom behavior.

## Commit & Pull Request Guidelines

Recent history uses short, imperative-style subjects, for example `Initial Commit - graph init`. Keep commit messages concise and describe the visible change. Prefer a clearer form such as `Add scanner tests` or `Fix README graph embedding`.

Pull requests should include a short summary, testing performed, and screenshots or notes for UI changes. Link related issues when available and call out changes that modify generated README graph output.
