from __future__ import annotations

import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable

from .graph import DependencyGraph


@dataclass
class ImpactReport:
    git_root: Path | None = None
    changed_files: set[str] = field(default_factory=set)
    changed_in_graph: set[str] = field(default_factory=set)
    changed_outside_graph: set[str] = field(default_factory=set)
    affected_files: set[str] = field(default_factory=set)
    impact_sources: dict[str, set[str]] = field(default_factory=dict)

    @property
    def has_git_repo(self) -> bool:
        return self.git_root is not None

    def level_for(self, node_id: str) -> str | None:
        if node_id in self.changed_in_graph:
            return "changed"
        if node_id in self.affected_files:
            return "affected"
        return None


def build_impact_report(root: Path, graph: DependencyGraph) -> ImpactReport:
    git_root = _git_root(root)
    if git_root is None:
        return ImpactReport()

    changed_files = _changed_files(git_root)
    report = ImpactReport(git_root=git_root, changed_files=changed_files)
    graph_nodes = set(graph.nodes)

    for changed_file in changed_files:
        node_id = _node_id_for_changed_file(root, git_root, changed_file)
        if node_id in graph_nodes:
            report.changed_in_graph.add(node_id)
        else:
            report.changed_outside_graph.add(changed_file)

    report.impact_sources = _trace_impacts(graph, report.changed_in_graph)
    report.affected_files = set(report.impact_sources)
    return report


def _git_root(root: Path) -> Path | None:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None

    value = result.stdout.strip()
    return Path(value).resolve() if value else None


def _changed_files(git_root: Path) -> set[str]:
    files: set[str] = set()
    files.update(_git_lines(git_root, ["diff", "--name-only", "--relative"]))
    files.update(_git_lines(git_root, ["diff", "--cached", "--name-only", "--relative"]))
    files.update(_git_lines(git_root, ["ls-files", "--others", "--exclude-standard"]))
    return {path for path in files if path}


def _git_lines(git_root: Path, args: list[str]) -> set[str]:
    try:
        result = subprocess.run(
            ["git", "-C", str(git_root), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return set()
    return {line.strip() for line in result.stdout.splitlines() if line.strip()}


def _node_id_for_changed_file(root: Path, git_root: Path, changed_file: str) -> str:
    absolute_path = (git_root / changed_file).resolve()
    try:
        return absolute_path.relative_to(root.resolve()).as_posix()
    except ValueError:
        return changed_file


def _trace_impacts(
    graph: DependencyGraph, changed_nodes: Iterable[str]
) -> dict[str, set[str]]:
    changed_set = set(changed_nodes)
    impact_sources: dict[str, set[str]] = {}

    for changed_node in sorted(changed_set):
        queue = list(graph.incoming(changed_node))
        seen = {changed_node}

        while queue:
            current = queue.pop(0)
            if current in seen:
                continue
            seen.add(current)

            if current not in changed_set:
                impact_sources.setdefault(current, set()).add(changed_node)

            queue.extend(graph.incoming(current))

    return impact_sources

