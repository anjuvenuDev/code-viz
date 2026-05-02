from __future__ import annotations

import math
import random
import tkinter as tk
from pathlib import Path
from tkinter import ttk

from .graph import DependencyGraph
from .scanner import build_graph


class GraphViewer:
    def __init__(self, root_path: Path, graph: DependencyGraph) -> None:
        self.root_path = root_path
        self.graph = graph
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
        self.detail_var = tk.StringVar(value="Select a file node")

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
        ttk.Label(details, text="Selected", font=("", 13, "bold")).grid(
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
            f"{len(self.graph.nodes)} files    {len(self.graph.edges)} links"
        )

    def _refresh(self) -> None:
        self.graph = build_graph(self.root_path)
        self.selected = None
        self.auto_fit_pending = True
        self.header_var.set(self._header_text())
        self._layout_graph()
        self._set_details("Select a file node")
        self._fit_and_draw()

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

            fill = "#ffffff" if is_linked else "#eeeeeb"
            outline = "#2f6fed" if is_selected else "#4b5560"
            text_fill = "#1f2933" if is_linked else "#9da4aa"
            if degree == 0:
                fill = "#fff8df" if is_linked else "#efede7"

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

        lines = [node_id, "", "References"]
        lines.extend(f"- {item}" for item in outgoing) if outgoing else lines.append("- none")
        lines.extend(["", "Referenced by"])
        lines.extend(f"- {item}" for item in incoming) if incoming else lines.append("- none")
        self._set_details("\n".join(lines))

    def _set_details(self, text: str) -> None:
        self.detail.configure(state="normal")
        self.detail.delete("1.0", tk.END)
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")
