from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Node:
    id: str
    label: str
    path: str


@dataclass(frozen=True)
class Edge:
    source: str
    target: str
    kind: str = "reference"


@dataclass
class DependencyGraph:
    nodes: dict[str, Node] = field(default_factory=dict)
    edges: set[Edge] = field(default_factory=set)

    def add_node(self, node_id: str) -> None:
        label = node_id.rsplit("/", 1)[-1]
        self.nodes[node_id] = Node(id=node_id, label=label, path=node_id)

    def add_edge(self, source: str, target: str, kind: str = "reference") -> None:
        if source == target:
            return
        if source not in self.nodes or target not in self.nodes:
            return
        self.edges.add(Edge(source=source, target=target, kind=kind))

    def outgoing(self, node_id: str) -> list[str]:
        return sorted(edge.target for edge in self.edges if edge.source == node_id)

    def incoming(self, node_id: str) -> list[str]:
        return sorted(edge.source for edge in self.edges if edge.target == node_id)

