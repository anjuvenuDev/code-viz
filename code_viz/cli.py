from __future__ import annotations

import argparse
from pathlib import Path

from .scanner import build_graph
from .viewer import GraphViewer


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="code-viz",
        description="Visualize a project directory as a file dependency graph.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser(
        "init",
        help="Scan the current working directory and open the dependency graph.",
    )
    init_parser.add_argument(
        "path",
        nargs="?",
        default=".",
        help="Project directory to scan. Defaults to the current working directory.",
    )

    args = parser.parse_args(argv)

    if args.command == "init":
        root = Path(args.path).resolve()
        if not root.exists() or not root.is_dir():
            parser.error(f"{root} is not a directory")

        graph = build_graph(root)
        GraphViewer(root, graph).run()
        return 0

    parser.error(f"unknown command: {args.command}")
    return 2

