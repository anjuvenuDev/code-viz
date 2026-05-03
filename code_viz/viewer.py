from __future__ import annotations

import math
import random
import tkinter as tk
from html import escape
from pathlib import Path
from tkinter import messagebox, ttk
from typing import Callable

from .graph import DependencyGraph
from .impact import build_impact_report
from .scanner import build_graph


README_GRAPH_START = "<!-- code-viz:graph:start -->"
README_GRAPH_END = "<!-- code-viz:graph:end -->"


class GraphViewer:
    def __init__(self, root_path: Path, graph: DependencyGraph) -> None:
        self.root_path = root_path
        self.graph = graph
        self.impact = build_impact_report(root_path, graph)
        self.window = tk.Tk()
        self.window.title(f"code-viz - {root_path.name}")
        self.window.geometry("1200x780")
        self.window.minsize(900, 560)

        self.scale = 1.0
        self.offset_x = 0.0
        self.offset_y = 0.0
        self.positions: dict[str, tuple[float, float]] = {}
        self.selected: str | None = None
        self.drag_node: str | None = None
        self.drag_last: tuple[int, int] | None = None
        self.pan_last: tuple[int, int] | None = None
        self.auto_fit_pending = True

        self.header_var = tk.StringVar()
        self.detail_var = tk.StringVar(value=self._impact_summary_text())
        self.status_var = tk.StringVar()

        self._build_ui()
        self._layout_graph()
        self.window.after_idle(self._fit_and_draw)

    def run(self) -> None:
        self.window.mainloop()

    def _build_ui(self) -> None:
        self.window.columnconfigure(0, weight=1)
        self.window.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.window, padding=(10, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        toolbar.columnconfigure(0, weight=1)

        self.header_var.set(self._header_text())
        ttk.Label(toolbar, textvariable=self.header_var).grid(row=0, column=0, sticky="w")
        ttk.Button(toolbar, text="Refresh", command=self._refresh).grid(row=0, column=1)
        ttk.Button(toolbar, text="Save SVG", command=self._save_graph_svg).grid(
            row=0, column=2, padx=(8, 0)
        )
        ttk.Button(
            toolbar,
            text="Embed README",
            command=self._save_graph_svg_and_embed_readme,
        ).grid(row=0, column=3, padx=(8, 0))

        body = ttk.PanedWindow(self.window, orient=tk.HORIZONTAL)
        body.grid(row=1, column=0, sticky="nsew")

        graph_frame = ttk.Frame(body)
        graph_frame.rowconfigure(0, weight=1)
        graph_frame.columnconfigure(0, weight=1)

        self.canvas = tk.Canvas(graph_frame, background="#f7f7f5", highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")

        details = ttk.Frame(body, width=280, padding=(12, 10))
        details.grid_propagate(False)
        details.rowconfigure(1, weight=1)
        ttk.Label(details, text="Impact", font=("", 13, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        self.detail = tk.Text(
            details,
            wrap="word",
            borderwidth=0,
            highlightthickness=0,
            background=self.window.cget("background"),
            padx=0,
            pady=8,
            height=20,
        )
        self.detail.grid(row=1, column=0, sticky="nsew")
        self.detail.insert("1.0", self.detail_var.get())
        self.detail.configure(state="disabled")
        ttk.Label(details, textvariable=self.status_var, wraplength=250).grid(
            row=2, column=0, sticky="ew", pady=(10, 0)
        )

        body.add(graph_frame, weight=1)
        body.add(details, weight=0)

        self.canvas.bind("<ButtonPress-1>", self._on_left_press)
        self.canvas.bind("<B1-Motion>", self._on_left_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_left_release)
        self.canvas.bind("<ButtonPress-2>", self._on_pan_press)
        self.canvas.bind("<B2-Motion>", self._on_pan_drag)
        self.canvas.bind("<ButtonPress-3>", self._on_pan_press)
        self.canvas.bind("<B3-Motion>", self._on_pan_drag)
        self.canvas.bind("<MouseWheel>", self._on_mousewheel)
        self.canvas.bind("<Button-4>", self._on_mousewheel)
        self.canvas.bind("<Button-5>", self._on_mousewheel)
        self.canvas.bind("<Configure>", self._on_canvas_configure)

    def _header_text(self) -> str:
        return (
            f"code-viz  {self.root_path}    "
            f"{len(self.graph.nodes)} files    {len(self.graph.edges)} links    "
            f"{len(self.impact.changed_in_graph)} changed    "
            f"{len(self.impact.affected_files)} affected"
        )

    def _refresh(self) -> None:
        self.graph = build_graph(self.root_path)
        self.impact = build_impact_report(self.root_path, self.graph)
        self.selected = None
        self.auto_fit_pending = True
        self.header_var.set(self._header_text())
        self._layout_graph()
        self._set_details(self._impact_summary_text())
        self._fit_and_draw()

    def _save_graph_svg(self) -> None:
        path = self._export_svg()
        if path is not None:
            self._set_status(f"Saved graph to {path.name}")

    def _save_graph_svg_and_embed_readme(self) -> None:
        svg_path = self._export_svg()
        if svg_path is None:
            return

        try:
            readme_path = self._embed_graph_in_readme(svg_path)
        except OSError as error:
            messagebox.showerror("README export failed", str(error))
            self._set_status("README export failed")
            return

        self._set_status(f"Saved {svg_path.name} and updated {readme_path.name}")

    def _export_svg(self) -> Path | None:
        path = self._graph_svg_path()
        try:
            path.write_text(self._svg_text(), encoding="utf-8")
        except OSError as error:
            messagebox.showerror("Graph export failed", str(error))
            self._set_status("Graph export failed")
            return None
        return path

    def _graph_svg_path(self) -> Path:
        name = "".join(
            char.lower() if char.isalnum() else "-"
            for char in (self.root_path.name or "project")
        )
        safe_name = "-".join(part for part in name.split("-") if part) or "project"
        return self.root_path / f"{safe_name}-dependency-graph.svg"

    def _embed_graph_in_readme(self, svg_path: Path) -> Path:
        readme_path = self.root_path / "README.md"
        relative_svg = svg_path.relative_to(self.root_path).as_posix()
        graph_section = self._readme_graph_section(relative_svg)

        if readme_path.exists():
            readme = readme_path.read_text(encoding="utf-8")
        else:
            readme = f"# {self.root_path.name}\n"

        if README_GRAPH_START in readme and README_GRAPH_END in readme:
            start = readme.index(README_GRAPH_START)
            end = readme.index(README_GRAPH_END) + len(README_GRAPH_END)
            readme = f"{readme[:start]}{graph_section}{readme[end:]}"
        else:
            separator = "\n\n" if readme.strip() else ""
            readme = f"{readme.rstrip()}{separator}{graph_section}\n"

        readme_path.write_text(readme, encoding="utf-8")
        return readme_path

    def _readme_graph_section(self, relative_svg: str) -> str:
        return "\n".join(
            [
                README_GRAPH_START,
                "## Code Dependency Graph",
                "",
                f"![Code dependency graph]({relative_svg})",
                "",
                "Generated by `code-viz` from the local dependency scan.",
                "",
                "Legend:",
                "",
                "- Circles are code files.",
                "- Arrows point from a file to another file it references or imports.",
                "- Red nodes are changed files in the current Git working tree.",
                "- Yellow nodes are files that depend on changed files.",
                "- Larger nodes have more incoming or outgoing dependency links.",
                "",
                f"Files: {len(self.graph.nodes)}. Links: {len(self.graph.edges)}. "
                f"Changed: {len(self.impact.changed_in_graph)}. "
                f"Affected: {len(self.impact.affected_files)}.",
                README_GRAPH_END,
            ]
        )

    def _svg_text(self) -> str:
        width = 1400
        graph_height = 820
        legend_height = 190
        height = graph_height + legend_height
        padding = 80

        transform = self._svg_transform(width, graph_height, padding)
        lines = [
            '<?xml version="1.0" encoding="UTF-8"?>',
            (
                f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" '
                f'height="{height}" viewBox="0 0 {width} {height}" '
                'role="img" aria-labelledby="title desc">'
            ),
            f"<title id=\"title\">code-viz dependency graph for {escape(self.root_path.name)}</title>",
            (
                '<desc id="desc">A dependency graph where circles are files, arrows '
                "show references, red files are changed, and yellow files are affected "
                "by changed files.</desc>"
            ),
            "<defs>",
            (
                '<marker id="arrow" markerWidth="10" markerHeight="10" refX="9" '
                'refY="3" orient="auto" markerUnits="strokeWidth">'
            ),
            '<path d="M0,0 L0,6 L9,3 z" fill="#5d6f80" />',
            "</marker>",
            "</defs>",
            '<rect width="100%" height="100%" fill="#f7f7f5" />',
            f'<text x="32" y="42" fill="#1f2933" font-size="24" font-family="Arial, sans-serif">code-viz: {escape(str(self.root_path))}</text>',
            f'<text x="32" y="70" fill="#4b5560" font-size="15" font-family="Arial, sans-serif">{len(self.graph.nodes)} files, {len(self.graph.edges)} links, {len(self.impact.changed_in_graph)} changed, {len(self.impact.affected_files)} affected</text>',
        ]

        if not self.graph.nodes:
            lines.append(
                f'<text x="{width / 2}" y="{graph_height / 2}" text-anchor="middle" '
                'fill="#555555" font-size="22" font-family="Arial, sans-serif">'
                "No code files found in this directory.</text>"
            )
        else:
            for edge in sorted(self.graph.edges, key=lambda item: (item.source, item.target)):
                sx, sy = transform(*self.positions[edge.source])
                tx, ty = transform(*self.positions[edge.target])
                lines.append(
                    f'<line x1="{sx:.2f}" y1="{sy:.2f}" x2="{tx:.2f}" y2="{ty:.2f}" '
                    'stroke="#5d6f80" stroke-width="2" opacity="0.82" '
                    'marker-end="url(#arrow)" />'
                )

            for node_id in sorted(self.graph.nodes):
                x, y = transform(*self.positions[node_id])
                radius, fill, outline, text_fill = self._node_svg_style(node_id)
                label = escape(self.graph.nodes[node_id].label)
                title = escape(node_id)
                lines.extend(
                    [
                        f"<g><title>{title}</title>",
                        (
                            f'<circle cx="{x:.2f}" cy="{y:.2f}" r="{radius:.2f}" '
                            f'fill="{fill}" stroke="{outline}" stroke-width="1.5" />'
                        ),
                        (
                            f'<text x="{x:.2f}" y="{y + radius + 16:.2f}" '
                            'text-anchor="middle" fill="'
                            f'{text_fill}" font-size="12" font-family="Arial, sans-serif">{label}</text>'
                        ),
                        "</g>",
                    ]
                )

        lines.extend(self._svg_legend(width, graph_height))
        lines.append("</svg>")
        return "\n".join(lines)

    def _svg_transform(
        self, width: int, graph_height: int, padding: int
    ) -> Callable[[float, float], tuple[float, float]]:
        if not self.positions:
            return lambda x, y: (width / 2, graph_height / 2)

        xs = [point[0] for point in self.positions.values()]
        ys = [point[1] for point in self.positions.values()]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        graph_width = max(max_x - min_x, 1.0)
        graph_depth = max(max_y - min_y, 1.0)
        scale = min(
            (width - padding * 2) / graph_width,
            (graph_height - padding * 2 - 30) / graph_depth,
            2.0,
        )
        center_x = (min_x + max_x) / 2
        center_y = (min_y + max_y) / 2

        def transform(x: float, y: float) -> tuple[float, float]:
            return (
                width / 2 + (x - center_x) * scale,
                graph_height / 2 + 20 + (y - center_y) * scale,
            )

        return transform

    def _node_svg_style(self, node_id: str) -> tuple[float, str, str, str]:
        incoming = len(self.graph.incoming(node_id))
        outgoing = len(self.graph.outgoing(node_id))
        degree = incoming + outgoing
        radius = min(20, 8 + degree * 1.5)
        impact_level = self.impact.level_for(node_id)

        fill = "#ffffff"
        outline = "#4b5560"
        text_fill = "#1f2933"
        if degree == 0:
            fill = "#fff8df"
        if impact_level == "changed":
            fill = "#e5484d"
            outline = "#8f1d22"
            text_fill = "#111111"
        elif impact_level == "affected":
            fill = "#f2c94c"
            outline = "#8a6d00"
            text_fill = "#111111"
        return radius, fill, outline, text_fill

    def _svg_legend(self, width: int, graph_height: int) -> list[str]:
        y = graph_height + 30
        return [
            f'<rect x="0" y="{graph_height}" width="{width}" height="190" fill="#ffffff" />',
            f'<line x1="0" y1="{graph_height}" x2="{width}" y2="{graph_height}" stroke="#d0d4d6" />',
            f'<text x="32" y="{y}" fill="#1f2933" font-size="18" font-weight="700" font-family="Arial, sans-serif">Legend</text>',
            f'<circle cx="48" cy="{y + 34}" r="10" fill="#ffffff" stroke="#4b5560" />',
            f'<text x="70" y="{y + 39}" fill="#1f2933" font-size="14" font-family="Arial, sans-serif">File node</text>',
            f'<line x1="190" y1="{y + 34}" x2="250" y2="{y + 34}" stroke="#5d6f80" stroke-width="2" marker-end="url(#arrow)" />',
            f'<text x="270" y="{y + 39}" fill="#1f2933" font-size="14" font-family="Arial, sans-serif">Reference/import direction</text>',
            f'<circle cx="48" cy="{y + 74}" r="10" fill="#e5484d" stroke="#8f1d22" />',
            f'<text x="70" y="{y + 79}" fill="#1f2933" font-size="14" font-family="Arial, sans-serif">Changed file</text>',
            f'<circle cx="190" cy="{y + 74}" r="10" fill="#f2c94c" stroke="#8a6d00" />',
            f'<text x="212" y="{y + 79}" fill="#1f2933" font-size="14" font-family="Arial, sans-serif">Affected by changed files</text>',
            f'<circle cx="48" cy="{y + 114}" r="7" fill="#ffffff" stroke="#4b5560" />',
            f'<circle cx="78" cy="{y + 114}" r="15" fill="#ffffff" stroke="#4b5560" />',
            f'<text x="110" y="{y + 119}" fill="#1f2933" font-size="14" font-family="Arial, sans-serif">Larger nodes have more incoming or outgoing links</text>',
        ]

    def _set_status(self, text: str) -> None:
        self.status_var.set(text)

    def _layout_graph(self) -> None:
        node_ids = sorted(self.graph.nodes)
        count = len(node_ids)
        self.positions = {}
        if not count:
            return

        radius = max(180.0, 34.0 * math.sqrt(count))
        random.seed(37)
        for index, node_id in enumerate(node_ids):
            angle = (2 * math.pi * index) / count
            jitter = random.uniform(-18, 18)
            self.positions[node_id] = (
                math.cos(angle) * (radius + jitter),
                math.sin(angle) * (radius + jitter),
            )

        edge_pairs = [(edge.source, edge.target) for edge in self.graph.edges]
        if not edge_pairs:
            self._center_layout()
            return

        iterations = min(220, max(60, count * 3))
        area = max(500.0, 95.0 * math.sqrt(count))
        ideal = area / math.sqrt(count)

        for _ in range(iterations):
            forces = {node_id: [0.0, 0.0] for node_id in node_ids}

            for i, source in enumerate(node_ids):
                sx, sy = self.positions[source]
                for target in node_ids[i + 1 :]:
                    tx, ty = self.positions[target]
                    dx = sx - tx
                    dy = sy - ty
                    distance = math.hypot(dx, dy) or 0.01
                    force = (ideal * ideal) / distance
                    fx = (dx / distance) * force
                    fy = (dy / distance) * force
                    forces[source][0] += fx
                    forces[source][1] += fy
                    forces[target][0] -= fx
                    forces[target][1] -= fy

            for source, target in edge_pairs:
                sx, sy = self.positions[source]
                tx, ty = self.positions[target]
                dx = sx - tx
                dy = sy - ty
                distance = math.hypot(dx, dy) or 0.01
                force = (distance * distance) / ideal
                fx = (dx / distance) * force
                fy = (dy / distance) * force
                forces[source][0] -= fx
                forces[source][1] -= fy
                forces[target][0] += fx
                forces[target][1] += fy

            temperature = max(1.5, 24.0 * (1.0 - (_ / iterations)))
            for node_id in node_ids:
                fx, fy = forces[node_id]
                magnitude = math.hypot(fx, fy) or 0.01
                x, y = self.positions[node_id]
                self.positions[node_id] = (
                    x + (fx / magnitude) * min(magnitude, temperature),
                    y + (fy / magnitude) * min(magnitude, temperature),
                )

        self._center_layout()

    def _center_layout(self) -> None:
        if not self.positions:
            return
        xs = [point[0] for point in self.positions.values()]
        ys = [point[1] for point in self.positions.values()]
        center_x = (min(xs) + max(xs)) / 2
        center_y = (min(ys) + max(ys)) / 2
        self.positions = {
            node_id: (x - center_x, y - center_y)
            for node_id, (x, y) in self.positions.items()
        }

    def _fit_and_draw(self) -> None:
        if self.auto_fit_pending:
            if not self._fit_to_view():
                self.window.after(50, self._fit_and_draw)
                return
            self.auto_fit_pending = False
        self._draw()

    def _fit_to_view(self) -> bool:
        width = self.canvas.winfo_width()
        height = self.canvas.winfo_height()
        if width <= 1 or height <= 1:
            return False

        if not self.positions:
            self.scale = 1.0
            self.offset_x = 0.0
            self.offset_y = 0.0
            return True

        xs = [point[0] for point in self.positions.values()]
        ys = [point[1] for point in self.positions.values()]
        graph_width = max(max(xs) - min(xs), 1.0)
        graph_height = max(max(ys) - min(ys), 1.0)
        horizontal_scale = (width - 120) / graph_width
        vertical_scale = (height - 120) / graph_height

        self.scale = min(2.0, max(0.05, min(horizontal_scale, vertical_scale)))
        self.offset_x = 0.0
        self.offset_y = 0.0
        return True

    def _draw(self) -> None:
        self.canvas.delete("all")
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        if not self.graph.nodes:
            self.canvas.create_text(
                width / 2,
                height / 2,
                text="No code files found in this directory.",
                fill="#555555",
                font=("", 14),
            )
            return

        linked = set()
        if self.selected:
            linked.add(self.selected)
            linked.update(self.graph.outgoing(self.selected))
            linked.update(self.graph.incoming(self.selected))

        for edge in sorted(self.graph.edges, key=lambda item: (item.source, item.target)):
            sx, sy = self._world_to_screen(*self.positions[edge.source])
            tx, ty = self._world_to_screen(*self.positions[edge.target])
            active = not self.selected or (
                edge.source == self.selected or edge.target == self.selected
            )
            color = "#5d6f80" if active else "#d0d4d6"
            width_px = 2 if active else 1
            self.canvas.create_line(
                sx,
                sy,
                tx,
                ty,
                fill=color,
                width=width_px,
                arrow=tk.LAST,
                arrowshape=(9, 11, 4),
            )

        for node_id in sorted(self.graph.nodes):
            x, y = self._world_to_screen(*self.positions[node_id])
            is_selected = node_id == self.selected
            is_linked = not self.selected or node_id in linked
            incoming = len(self.graph.incoming(node_id))
            outgoing = len(self.graph.outgoing(node_id))
            degree = incoming + outgoing
            radius = min(20, 8 + degree * 1.5)
            impact_level = self.impact.level_for(node_id)

            fill = "#ffffff" if is_linked else "#eeeeeb"
            outline = "#2f6fed" if is_selected else "#4b5560"
            text_fill = "#1f2933" if is_linked else "#9da4aa"
            if degree == 0:
                fill = "#fff8df" if is_linked else "#efede7"
            if impact_level == "changed":
                fill = "#e5484d" if is_linked else "#f2a2a5"
                outline = "#8f1d22" if not is_selected else outline
                text_fill = "#111111" if is_linked else "#7b5557"
            elif impact_level == "affected":
                fill = "#f2c94c" if is_linked else "#f7e6a7"
                outline = "#8a6d00" if not is_selected else outline
                text_fill = "#111111" if is_linked else "#7a6d40"

            self.canvas.create_oval(
                x - radius,
                y - radius,
                x + radius,
                y + radius,
                fill=fill,
                outline=outline,
                width=3 if is_selected else 1,
                tags=("node", f"node:{node_id}"),
            )
            self.canvas.create_text(
                x,
                y + radius + 12,
                text=self.graph.nodes[node_id].label,
                fill=text_fill,
                font=("", 9),
                tags=("node-label", f"node:{node_id}"),
            )

    def _on_canvas_configure(self, _event: tk.Event) -> None:
        self._fit_and_draw() if self.auto_fit_pending else self._draw()

    def _world_to_screen(self, x: float, y: float) -> tuple[float, float]:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        return (
            width / 2 + self.offset_x + x * self.scale,
            height / 2 + self.offset_y + y * self.scale,
        )

    def _screen_to_world(self, x: float, y: float) -> tuple[float, float]:
        width = max(1, self.canvas.winfo_width())
        height = max(1, self.canvas.winfo_height())
        return (
            (x - width / 2 - self.offset_x) / self.scale,
            (y - height / 2 - self.offset_y) / self.scale,
        )

    def _node_at(self, x: int, y: int) -> str | None:
        closest = None
        closest_distance = 28.0
        for node_id, (world_x, world_y) in self.positions.items():
            sx, sy = self._world_to_screen(world_x, world_y)
            distance = math.hypot(sx - x, sy - y)
            if distance < closest_distance:
                closest = node_id
                closest_distance = distance
        return closest

    def _on_left_press(self, event: tk.Event) -> None:
        node_id = self._node_at(event.x, event.y)
        if node_id:
            self.selected = node_id
            self.drag_node = node_id
            self.drag_last = (event.x, event.y)
            self._set_details_for_node(node_id)
            self._draw()
        else:
            self.pan_last = (event.x, event.y)

    def _on_left_drag(self, event: tk.Event) -> None:
        if self.drag_node and self.drag_last:
            world_x, world_y = self._screen_to_world(event.x, event.y)
            self.positions[self.drag_node] = (world_x, world_y)
            self.drag_last = (event.x, event.y)
            self._draw()
        elif self.pan_last:
            last_x, last_y = self.pan_last
            self.offset_x += event.x - last_x
            self.offset_y += event.y - last_y
            self.pan_last = (event.x, event.y)
            self._draw()

    def _on_left_release(self, _event: tk.Event) -> None:
        self.drag_node = None
        self.drag_last = None
        self.pan_last = None

    def _on_pan_press(self, event: tk.Event) -> None:
        self.pan_last = (event.x, event.y)

    def _on_pan_drag(self, event: tk.Event) -> None:
        if not self.pan_last:
            return
        last_x, last_y = self.pan_last
        self.offset_x += event.x - last_x
        self.offset_y += event.y - last_y
        self.pan_last = (event.x, event.y)
        self._draw()

    def _on_mousewheel(self, event: tk.Event) -> None:
        if getattr(event, "num", None) == 4 or getattr(event, "delta", 0) > 0:
            factor = 1.1
        else:
            factor = 0.9

        before_x, before_y = self._screen_to_world(event.x, event.y)
        self.scale = min(4.0, max(0.2, self.scale * factor))
        after_x, after_y = self._screen_to_world(event.x, event.y)
        self.offset_x += (after_x - before_x) * self.scale
        self.offset_y += (after_y - before_y) * self.scale
        self._draw()

    def _set_details_for_node(self, node_id: str) -> None:
        outgoing = self.graph.outgoing(node_id)
        incoming = self.graph.incoming(node_id)
        impact_level = self.impact.level_for(node_id)

        lines = [node_id, "", "Impact"]
        if impact_level == "changed":
            lines.append("Red: changed in the pending commit set")
            impacted = sorted(
                node
                for node, sources in self.impact.impact_sources.items()
                if node != node_id and node_id in sources
            )
            lines.append("")
            lines.append("May affect")
            lines.extend(f"- {item}" for item in impacted) if impacted else lines.append(
                "- none detected"
            )
        elif impact_level == "affected":
            lines.append("Yellow: depends on changed file(s)")
            lines.append("")
            lines.append("Affected by")
            sources = sorted(self.impact.impact_sources.get(node_id, set()))
            lines.extend(f"- {item}" for item in sources) if sources else lines.append(
                "- none detected"
            )
        else:
            lines.append("No pending-change impact detected")

        lines.extend(["", "References"])
        lines.extend(f"- {item}" for item in outgoing) if outgoing else lines.append("- none")
        lines.extend(["", "Referenced by"])
        lines.extend(f"- {item}" for item in incoming) if incoming else lines.append("- none")
        self._set_details("\n".join(lines))

    def _impact_summary_text(self) -> str:
        if not self.impact.has_git_repo:
            return "No Git repository detected.\n\nImpact coloring needs Git changes."

        lines = [
            "Pending commit impact",
            "",
            f"Red changed files: {len(self.impact.changed_in_graph)}",
            f"Yellow affected files: {len(self.impact.affected_files)}",
        ]

        if not self.impact.changed_files:
            lines.extend(["", "No staged, unstaged, or untracked file changes detected."])
            return "\n".join(lines)

        if self.impact.changed_in_graph:
            lines.extend(["", "Changed in graph"])
            lines.extend(f"- {item}" for item in sorted(self.impact.changed_in_graph))

        if self.impact.affected_files:
            lines.extend(["", "Affected by dependency links"])
            lines.extend(f"- {item}" for item in sorted(self.impact.affected_files))

        if self.impact.changed_outside_graph:
            lines.extend(["", "Changed outside graph"])
            lines.extend(f"- {item}" for item in sorted(self.impact.changed_outside_graph))

        return "\n".join(lines)

    def _set_details(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")
