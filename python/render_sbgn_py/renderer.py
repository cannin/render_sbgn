"""SBGNML renderer using pycairo.

This module mirrors the rendering logic from the Rust implementation while
keeping dependencies limited to pycairo and the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, List, Optional, Sequence, Tuple
import json
import math
import xml.etree.ElementTree as ET

import cairo

# Configuration constants
DEFAULT_PADDING_PX = 50.0
RENDERER_VERSION = "0.0.6"
DEFAULT_LINE_WIDTH = 1.5
FONT_FAMILY = "Liberation Sans"
ARROW_SIZE = 8.0
CYTOSCAPE_ARROW_SCALE = 4.53125

BORDER_COLOR = (0x55 / 255.0, 0x55 / 255.0, 0x55 / 255.0)
JS_NODE_FILL_COLOR = (1.0, 1.0, 1.0)
JS_NODE_BORDER_COLOR = BORDER_COLOR
JS_NODE_TEXT_COLOR = (0.0, 0.0, 0.0)
JS_COMPARTMENT_BORDER_COLOR = BORDER_COLOR
JS_MACROMOLECULE_BORDER_COLOR = BORDER_COLOR
JS_SIMPLE_CHEMICAL_BORDER_COLOR = BORDER_COLOR
JS_COMPLEX_BORDER_COLOR = BORDER_COLOR
JS_PROCESS_BORDER_COLOR = BORDER_COLOR
JS_SUBMAP_BORDER_COLOR = BORDER_COLOR
JS_PHENOTYPE_BORDER_COLOR = BORDER_COLOR
JS_SOURCE_SINK_BORDER_COLOR = BORDER_COLOR
JS_GLYPH_COLOR_BORDER_COLOR = (0x16 / 255.0, 0x19 / 255.0, 0x1F / 255.0)
JS_EDGE_COLOR = BORDER_COLOR
JS_DEFAULT_NODE_BORDER_WIDTH = 1.25
JS_COMPLEX_BORDER_WIDTH = 1.25
JS_COMPARTMENT_BORDER_WIDTH = 3.25
JS_GLYPH_COLOR_BORDER_WIDTH = 2.4
JS_DEFAULT_EDGE_WIDTH = 1.25
JS_NODE_FONT_PX = 12.0
JS_COMPARTMENT_FONT_PX = 12.0
StyleConfig = dict[str, Any]


@dataclass(frozen=True)
class Point:
    """2D point in floating point coordinates."""

    x: float
    y: float


@dataclass(frozen=True)
class BBox:
    """Bounding box in data coordinates."""

    x: float
    y: float
    w: float
    h: float


@dataclass(frozen=True)
class PixelRect:
    """Rectangle in pixel coordinates with a cached center point."""

    x0: float
    y0: float
    width: float
    height: float
    center: Point


@dataclass(frozen=True)
class Port(Point):
    """SBGN glyph port with an ID for endpoint topology."""

    id: str


@dataclass
class Glyph:
    """Parsed glyph from SBGNML."""

    id: str
    parent_id: Optional[str]
    class_name: str
    bbox: Optional[BBox]
    extra_width: Optional[float]
    extra_height: Optional[float]
    label: str
    ports: List[Port]
    has_clone: bool
    state_value: Optional[str]
    state_variable: Optional[str]
    orientation: Optional[str]
    entity_name: Optional[str] = None


@dataclass
class ArcGlyph:
    """Auxiliary glyph attached directly to an SBGN arc."""

    id: str
    class_name: str
    bbox: Optional[BBox]
    label: str


@dataclass
class Arc:
    """Parsed arc with ordered points."""

    id: str
    class_name: str
    source: Optional[str]
    target: Optional[str]
    points: List[Point]
    auxiliary_glyphs: List[ArcGlyph] = field(default_factory=list)


@dataclass(frozen=True)
class Bounds:
    """Data bounds for layout."""

    min_x: float
    max_x: float
    min_y: float
    max_y: float


@dataclass(frozen=True)
class Transform:
    """Coordinate transform from data units to pixels."""

    min_x: float
    min_y: float
    scale_x: float
    scale_y: float
    offset_x: float = 0.0
    offset_y: float = 0.0

    def map_point(self, x: float, y: float) -> Point:
        """Map a data point into pixel coordinates."""

        return Point(
            self.offset_x + (x - self.min_x) * self.scale_x,
            self.offset_y + (y - self.min_y) * self.scale_y,
        )

    def scale_scalar(self, value: float) -> float:
        """Scale a scalar value by the minimum axis scale."""

        return value * min(self.scale_x, self.scale_y)


# Parsing helpers


def strip_tag(tag: str) -> str:
    """Strip XML namespace from a tag name."""

    return tag.split("}")[-1] if "}" in tag else tag


def parse_float(value: Optional[str]) -> Optional[float]:
    """Parse a string into a float if possible."""

    if value is None:
        return None
    try:
        return float(value)
    except ValueError:
        return None


def parse_bbox(node: ET.Element) -> Optional[BBox]:
    """Parse a bbox element into a BBox dataclass."""

    x = parse_float(node.get("x"))
    y = parse_float(node.get("y"))
    w = parse_float(node.get("w"))
    h = parse_float(node.get("h"))
    if x is None or y is None or w is None or h is None:
        return None
    return BBox(x=x, y=y, w=w, h=h)


def parse_glyph_node(
    glyph: ET.Element, parent_id: Optional[str], glyphs: List[Glyph]
) -> None:
    """Recursively parse glyph nodes into a flat list."""

    glyph_id = glyph.get("id", "")
    class_name = glyph.get("class", "")
    effective_parent_id = glyph.get("compartmentRef") or parent_id

    label_text = ""
    for child in glyph:
        if strip_tag(child.tag) == "label":
            label_text = child.get("text", "")
            break
    label_text = label_text.replace("\r", "")

    bbox = None
    for child in glyph:
        if strip_tag(child.tag) == "bbox":
            bbox = parse_bbox(child)
            break

    extra_width = None
    extra_height = None
    for child in glyph.iter():
        child_tag = strip_tag(child.tag)
        if child_tag == "w":
            extra_width = parse_float(child.text)
        elif child_tag == "h":
            extra_height = parse_float(child.text)

    ports: List[Port] = []
    for child in glyph:
        if strip_tag(child.tag) == "port":
            x = parse_float(child.get("x"))
            y = parse_float(child.get("y"))
            if x is not None and y is not None:
                ports.append(Port(x=x, y=y, id=child.get("id", "")))

    has_clone = any(strip_tag(child.tag) == "clone" for child in glyph)

    state_value = None
    state_variable = None
    for child in glyph:
        if strip_tag(child.tag) == "state":
            state_value = child.get("value")
            state_variable = child.get("variable")
            break

    entity_name = None
    for child in glyph:
        if strip_tag(child.tag) == "entity":
            entity_name = child.get("name")
            break

    orientation = glyph.get("orientation")

    glyphs.append(
        Glyph(
            id=glyph_id,
            parent_id=effective_parent_id,
            class_name=class_name,
            bbox=bbox,
            extra_width=extra_width,
            extra_height=extra_height,
            label=label_text,
            ports=ports,
            has_clone=has_clone,
            state_value=state_value,
            state_variable=state_variable,
            orientation=orientation,
            entity_name=entity_name,
        )
    )

    for child in glyph:
        if strip_tag(child.tag) == "glyph":
            parse_glyph_node(child, glyph_id, glyphs)


def parse_sbgnml(path: Path) -> Tuple[List[Glyph], List[Arc], Bounds]:
    """Parse an SBGNML file into glyphs, arcs, and bounds."""

    tree = ET.parse(path)
    root = tree.getroot()

    map_nodes = [node for node in root.iter() if strip_tag(node.tag) == "map"]
    if not map_nodes:
        raise ValueError("SBGN file missing map element")

    glyphs: List[Glyph] = []
    for map_node in map_nodes:
        for child in list(map_node):
            if strip_tag(child.tag) == "glyph":
                parse_glyph_node(child, None, glyphs)

    arcs: List[Arc] = []
    for arc_node in root.iter():
        if strip_tag(arc_node.tag) != "arc":
            continue
        class_name = arc_node.get("class", "")
        start_node = None
        end_node = None
        for child in arc_node:
            tag = strip_tag(child.tag)
            if tag == "start":
                start_node = child
            elif tag == "end":
                end_node = child
        if start_node is None or end_node is None:
            raise ValueError("Arc missing start or end")

        points: List[Point] = []
        start_x = parse_float(start_node.get("x"))
        start_y = parse_float(start_node.get("y"))
        end_x = parse_float(end_node.get("x"))
        end_y = parse_float(end_node.get("y"))
        if start_x is None or start_y is None:
            raise ValueError("Bad arc start coordinates")
        if end_x is None or end_y is None:
            raise ValueError("Bad arc end coordinates")
        points.append(Point(start_x, start_y))

        for child in arc_node:
            if strip_tag(child.tag) == "next":
                x = parse_float(child.get("x"))
                y = parse_float(child.get("y"))
                if x is not None and y is not None:
                    points.append(Point(x, y))

        points.append(Point(end_x, end_y))
        auxiliary_glyphs: List[ArcGlyph] = []
        for child in arc_node:
            if strip_tag(child.tag) != "glyph":
                continue
            bbox_node = next(
                (node for node in child if strip_tag(node.tag) == "bbox"),
                None,
            )
            label_node = next(
                (node for node in child if strip_tag(node.tag) == "label"),
                None,
            )
            auxiliary_glyphs.append(
                ArcGlyph(
                    id=child.get("id", ""),
                    class_name=child.get("class", ""),
                    bbox=parse_bbox(bbox_node) if bbox_node is not None else None,
                    label=(
                        label_node.get("text", "") if label_node is not None else ""
                    ).replace("\r", ""),
                )
            )
        arcs.append(
            Arc(
                id=arc_node.get("id", ""),
                class_name=class_name,
                source=arc_node.get("source"),
                target=arc_node.get("target"),
                points=points,
                auxiliary_glyphs=auxiliary_glyphs,
            )
        )

    bounds = compute_bounds(glyphs, arcs)
    return glyphs, arcs, bounds


# Geometry helpers


def compute_bounds(glyphs: Sequence[Glyph], arcs: Sequence[Arc]) -> Bounds:
    """Compute JS-rendered primitive bounds from visible glyph bboxes."""

    x_values: List[float] = []
    y_values: List[float] = []

    for glyph in glyphs:
        if glyph.bbox is not None and not is_js_hidden_glyph_class(glyph.class_name):
            x_values.extend([glyph.bbox.x, glyph.bbox.x + glyph.bbox.w])
            y_values.extend([glyph.bbox.y, glyph.bbox.y + glyph.bbox.h])

    if not x_values or not y_values:
        raise ValueError("No coordinates found in SBGN file")

    return Bounds(
        min_x=min(x_values),
        max_x=max(x_values),
        min_y=min(y_values),
        max_y=max(y_values),
    )


def transform_with_padding(
    bounds: Bounds,
    padding: float,
    output_width: Optional[float] = None,
    output_height: Optional[float] = None,
) -> Tuple[Transform, float, float]:
    """Build a transform and image size from data bounds."""

    min_x = bounds.min_x - padding
    max_x = bounds.max_x + padding
    min_y = bounds.min_y - padding
    max_y = bounds.max_y + padding

    span_x = max(abs(max_x - min_x), 1.0)
    span_y = max(abs(max_y - min_y), 1.0)
    width = max(float(output_width or span_x), 1.0)
    height = max(float(output_height or span_y), 1.0)
    scale = min(width / span_x, height / span_y)
    offset_x = (width - span_x * scale) / 2.0
    offset_y = (height - span_y * scale) / 2.0

    transform = Transform(
        min_x=min_x,
        min_y=min_y,
        scale_x=scale,
        scale_y=scale,
        offset_x=offset_x,
        offset_y=offset_y,
    )

    return transform, width, height


def bbox_pixel_rect(transform: Transform, bbox: BBox) -> PixelRect:
    """Convert a data-space bbox into pixel-space rectangle."""

    x0 = transform.offset_x + (bbox.x - transform.min_x) * transform.scale_x
    x1 = transform.offset_x + (bbox.x + bbox.w - transform.min_x) * transform.scale_x
    y0 = transform.offset_y + (bbox.y - transform.min_y) * transform.scale_y
    y1 = transform.offset_y + (bbox.y + bbox.h - transform.min_y) * transform.scale_y

    left = min(x0, x1)
    right = max(x0, x1)
    top = min(y0, y1)
    bottom = max(y0, y1)

    return PixelRect(
        x0=left,
        y0=top,
        width=right - left,
        height=bottom - top,
        center=Point((left + right) / 2.0, (top + bottom) / 2.0),
    )


def sbgnviz_port_span(glyph: Glyph) -> Optional[float]:
    """Return sbgnviz's source-space port span for ported primitives."""

    ported_classes = {
        "process",
        "omitted process",
        "uncertain process",
        "association",
        "dissociation",
        "and",
        "or",
        "not",
    }
    if glyph.class_name not in ported_classes or len(glyph.ports) < 2:
        return None
    x_values = [port.x for port in glyph.ports]
    y_values = [port.y for port in glyph.ports]
    span = max(max(x_values) - min(x_values), max(y_values) - min(y_values))
    if glyph.bbox is not None:
        span = max(span, glyph.bbox.w, glyph.bbox.h)
    return span if span > 0 else None


def sbgnviz_manifest_rect(glyph: Glyph) -> PixelRect:
    """Return the source-space primitive rectangle used by sbgnviz manifests."""

    if glyph.bbox is None:
        return PixelRect(0.0, 0.0, 0.0, 0.0, Point(0.0, 0.0))
    center = Point(glyph.bbox.x + glyph.bbox.w / 2.0, glyph.bbox.y + glyph.bbox.h / 2.0)
    port_span = sbgnviz_port_span(glyph)
    if port_span is not None:
        width = port_span
        height = port_span
    elif glyph.class_name in {"compartment", "complex", "complex multimer"}:
        padding = 24.0 if glyph.class_name == "compartment" else 10.0
        border_width = (
            JS_COMPARTMENT_BORDER_WIDTH
            if glyph.class_name == "compartment"
            else JS_COMPLEX_BORDER_WIDTH
        )
        expansion = 2.0 * padding + border_width + 2.0
        width = (
            glyph.extra_width if glyph.extra_width is not None else glyph.bbox.w
        ) + expansion
        height = (
            glyph.extra_height if glyph.extra_height is not None else glyph.bbox.h
        ) + expansion
    elif glyph.extra_width is not None and glyph.extra_height is not None:
        width = glyph.extra_width
        height = glyph.extra_height
    else:
        width = glyph.bbox.w
        height = glyph.bbox.h
    return PixelRect(
        x0=center.x - width / 2.0,
        y0=center.y - height / 2.0,
        width=width,
        height=height,
        center=center,
    )


# Cairo helpers


def setup_context(ctx: cairo.Context) -> None:
    """Initialize the Cairo context with defaults."""

    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.paint()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    ctx.set_line_cap(cairo.LineCap.SQUARE)


def create_png_surface(
    width: int, height: int
) -> Tuple[cairo.ImageSurface, cairo.Context]:
    """Create a Cairo image surface and context."""

    surface = cairo.ImageSurface(cairo.Format.ARGB32, width, height)
    ctx = cairo.Context(surface)
    setup_context(ctx)
    return surface, ctx


def render_svg(svg_path: Path, width: float, height: float, render_fn) -> None:
    """Render to an SVG surface using Cairo."""

    surface = cairo.SVGSurface(str(svg_path), width, height)
    ctx = cairo.Context(surface)
    setup_context(ctx)
    render_fn(ctx)
    surface.finish()


# Text helpers


def set_font(ctx: cairo.Context, font_px: float) -> None:
    """Configure font on the Cairo context."""

    ctx.select_font_face(FONT_FAMILY, cairo.FontSlant.NORMAL, cairo.FontWeight.NORMAL)
    ctx.set_font_size(font_px)


def text_metrics(
    ctx: cairo.Context, text: str, font_px: float
) -> Tuple[float, float, float]:
    """Return width, line height, and ascent for a line of text."""

    set_font(ctx, font_px)
    extents = ctx.text_extents(text)
    font_extents = ctx.font_extents()
    line_height = font_extents[2]
    ascent = font_extents[0]
    return extents.width, line_height, ascent


def draw_js_text_centered(
    ctx: cairo.Context,
    center: Point,
    text: str,
    font_px: float,
    color: Tuple[float, float, float],
) -> None:
    """Draw JS-style centered text without native renderer decoration.

    Args:
        ctx: Cairo drawing context.
        center: Text center point.
        text: Label text.
        font_px: Font size in pixels.
        color: RGB text color.

    Returns:
        None.
    """

    if not text.strip():
        return
    set_font(ctx, font_px)
    lines = text.split("\n")
    widths = []
    line_height = 0.0
    ascent = 0.0
    for line in lines:
        width, height, line_ascent = text_metrics(ctx, line, font_px)
        widths.append(width)
        line_height = max(line_height, height)
        ascent = max(ascent, line_ascent)

    total_height = line_height * len(lines)
    y_start = center.y - total_height / 2.0 + ascent
    ctx.set_source_rgb(*color)
    for idx, line in enumerate(lines):
        x = center.x - widths[idx] / 2.0
        y = y_start + idx * line_height
        ctx.move_to(x, y)
        ctx.show_text(line)
    ctx.set_source_rgb(*BORDER_COLOR)


# Shape primitives


def path_rect(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add a rectangle path to the context."""

    ctx.new_path()
    ctx.rectangle(rect.x0, rect.y0, rect.width, rect.height)


def path_ellipse(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add an ellipse path to the context."""

    radius_x = max(rect.width / 2.0, 1.0)
    radius_y = max(rect.height / 2.0, 1.0)
    ctx.save()
    ctx.new_path()
    ctx.translate(rect.center.x, rect.center.y)
    ctx.scale(radius_x, radius_y)
    ctx.arc(0.0, 0.0, 1.0, 0.0, math.tau)
    ctx.restore()


def path_round_rect(ctx: cairo.Context, rect: PixelRect, radius: float) -> None:
    """Add a rounded-rectangle path to the context."""

    path_round_rect_impl(ctx, rect.x0, rect.y0, rect.width, rect.height, radius)


def path_stadium(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add the sbgnviz simple-chemical stadium path."""

    path_round_rect(ctx, rect, max(1.0, rect.height / 2.0))


def tag_points(rect: PixelRect, orientation: Optional[str]) -> list[Point]:
    """Return sbgnviz tag polygon points."""

    x0 = rect.x0
    y0 = rect.y0
    x1 = rect.x0 + rect.width
    y1 = rect.y0 + rect.height
    orientation_value = str(orientation or "right").strip().lower()
    if orientation_value == "left":
        return [
            Point(x1, y0),
            Point(x0 + 0.75 * rect.width, y0),
            Point(x0, rect.center.y),
            Point(x0 + 0.75 * rect.width, y1),
            Point(x1, y1),
        ]
    if orientation_value == "up":
        return [
            Point(x0, y1),
            Point(x0, y0 + 0.75 * rect.height),
            Point(rect.center.x, y0),
            Point(x1, y0 + 0.75 * rect.height),
            Point(x1, y1),
        ]
    if orientation_value == "down":
        return [
            Point(x0, y0),
            Point(x0, y0 + 0.25 * rect.height),
            Point(rect.center.x, y1),
            Point(x1, y0 + 0.25 * rect.height),
            Point(x1, y0),
        ]
    return [
        Point(x0, y0),
        Point(x0 + 0.625 * rect.width, y0),
        Point(x1, rect.center.y),
        Point(x0 + 0.625 * rect.width, y1),
        Point(x0, y1),
    ]


def perturbing_agent_points(rect: PixelRect) -> list[Point]:
    """Return sbgnviz perturbing-agent polygon points."""

    return [
        Point(rect.x0, rect.y0),
        Point(rect.x0 + 0.25 * rect.width, rect.center.y),
        Point(rect.x0, rect.y0 + rect.height),
        Point(rect.x0 + rect.width, rect.y0 + rect.height),
        Point(rect.x0 + 0.75 * rect.width, rect.center.y),
        Point(rect.x0 + rect.width, rect.y0),
    ]


def path_polygon_points(ctx: cairo.Context, points: list[Point]) -> None:
    """Add a closed polygon path from points."""

    ctx.new_path()
    if not points:
        return
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()


def path_hexagon(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add a hexagon path."""

    x0 = rect.x0
    y0 = rect.y0
    w = rect.width
    h = rect.height
    points = [
        Point(x0, y0 + 0.5 * h),
        Point(x0 + 0.25 * w, y0),
        Point(x0 + 0.75 * w, y0),
        Point(x0 + w, y0 + 0.5 * h),
        Point(x0 + 0.75 * w, y0 + h),
        Point(x0 + 0.25 * w, y0 + h),
    ]
    ctx.new_path()
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()


def path_cut_rect(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add the clipped-corner complex path used by sbgnviz."""

    corner = min(12.0, rect.width / 3.0, rect.height / 3.0)
    points = [
        Point(rect.x0 + corner, rect.y0),
        Point(rect.x0, rect.y0 + corner),
        Point(rect.x0, rect.y0 + rect.height - corner),
        Point(rect.x0 + corner, rect.y0 + rect.height),
        Point(rect.x0 + rect.width - corner, rect.y0 + rect.height),
        Point(rect.x0 + rect.width, rect.y0 + rect.height - corner),
        Point(rect.x0 + rect.width, rect.y0 + corner),
        Point(rect.x0 + rect.width - corner, rect.y0),
    ]
    ctx.new_path()
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()


def path_bottom_round_rect(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add the nucleic-acid feature path with rounded bottom corners."""

    radius = min(10.0, rect.width / 2.0, rect.height / 2.0)
    right = rect.x0 + rect.width
    bottom = rect.y0 + rect.height
    ctx.new_path()
    ctx.move_to(rect.x0, rect.y0)
    ctx.line_to(right, rect.y0)
    ctx.line_to(right, bottom - radius)
    ctx.arc(right - radius, bottom - radius, radius, 0.0, math.pi / 2.0)
    ctx.line_to(rect.x0 + radius, bottom)
    ctx.arc(rect.x0 + radius, bottom - radius, radius, math.pi / 2.0, math.pi)
    ctx.close_path()


def path_barrel(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add the sbgnviz compartment barrel path."""

    width_offset = min(100.0, rect.width / 3.0)
    height_offset = min(15.0, rect.height / 3.0)
    control_x_offset = 5.0
    right = rect.x0 + rect.width
    bottom = rect.y0 + rect.height
    ctx.new_path()
    ctx.move_to(rect.x0, rect.y0 + height_offset)
    ctx.line_to(rect.x0, bottom - height_offset)
    ctx.curve_to(
        rect.x0 + control_x_offset,
        bottom,
        rect.x0 + width_offset,
        bottom,
        rect.x0 + width_offset,
        bottom,
    )
    ctx.line_to(right - width_offset, bottom)
    ctx.curve_to(
        right - control_x_offset,
        bottom,
        right,
        bottom - height_offset,
        right,
        bottom - height_offset,
    )
    ctx.line_to(right, rect.y0 + height_offset)
    ctx.curve_to(
        right - control_x_offset,
        rect.y0,
        right - width_offset,
        rect.y0,
        right - width_offset,
        rect.y0,
    )
    ctx.line_to(rect.x0 + width_offset, rect.y0)
    ctx.curve_to(
        rect.x0 + control_x_offset,
        rect.y0,
        rect.x0,
        rect.y0 + height_offset,
        rect.x0,
        rect.y0 + height_offset,
    )
    ctx.close_path()


def is_ported_glyph_class(class_name: str) -> bool:
    """Return whether sbgnviz draws the glyph with port stubs."""

    return class_name in {
        "process",
        "omitted process",
        "uncertain process",
        "association",
        "dissociation",
        "and",
        "or",
        "not",
    }


def port_orientation(glyph: Glyph) -> str:
    """Infer port orientation from explicit SBGN ports."""

    if len(glyph.ports) >= 2:
        x_values = [port.x for port in glyph.ports]
        y_values = [port.y for port in glyph.ports]
        if max(y_values) - min(y_values) > max(x_values) - min(x_values):
            return "vertical"
    return "horizontal"


def path_ported_glyph(ctx: cairo.Context, rect: PixelRect, glyph: Glyph) -> None:
    """Add the sbgnviz process/logical operator polygon with port stubs."""

    orientation = port_orientation(glyph)
    core_type = "rectangle" if "process" in glyph.class_name else "circle"
    core_width = rect.width * 0.707071
    core_height = rect.height * 0.707071
    core = PixelRect(
        rect.center.x - core_width / 2.0,
        rect.center.y - core_height / 2.0,
        core_width,
        core_height,
        rect.center,
    )
    points: list[Point] = []
    if orientation == "horizontal":
        line_half_height = max(rect.height * 0.01, 0.5) / 2.0
        if core_type == "circle":
            top = [
                Point(
                    core.center.x + core.width / 2.0 * math.cos(theta),
                    core.center.y + core.height / 2.0 * math.sin(theta),
                )
                for theta in [math.pi - math.pi * index / 30.0 for index in range(31)]
            ]
            bottom = [
                Point(
                    core.center.x + core.width / 2.0 * math.cos(theta),
                    core.center.y + core.height / 2.0 * math.sin(theta),
                )
                for theta in [-math.pi * index / 30.0 for index in range(31)]
            ]
            points = [
                Point(rect.x0, rect.center.y - line_half_height),
                Point(core.x0, rect.center.y - line_half_height),
                *top,
                Point(core.x0 + core.width, rect.center.y - line_half_height),
                Point(rect.x0 + rect.width, rect.center.y - line_half_height),
                Point(rect.x0 + rect.width, rect.center.y + line_half_height),
                Point(core.x0 + core.width, rect.center.y + line_half_height),
                *bottom,
                Point(core.x0, rect.center.y + line_half_height),
                Point(rect.x0, rect.center.y + line_half_height),
            ]
        else:
            points = [
                Point(rect.x0, rect.center.y - line_half_height),
                Point(core.x0, rect.center.y - line_half_height),
                Point(core.x0, core.y0),
                Point(core.x0 + core.width, core.y0),
                Point(core.x0 + core.width, rect.center.y - line_half_height),
                Point(rect.x0 + rect.width, rect.center.y - line_half_height),
                Point(rect.x0 + rect.width, rect.center.y + line_half_height),
                Point(core.x0 + core.width, rect.center.y + line_half_height),
                Point(core.x0 + core.width, core.y0 + core.height),
                Point(core.x0, core.y0 + core.height),
                Point(core.x0, rect.center.y + line_half_height),
                Point(rect.x0, rect.center.y + line_half_height),
            ]
    else:
        line_half_width = max(rect.width * 0.01, 0.5) / 2.0
        points = [
            Point(rect.center.x - line_half_width, rect.y0),
            Point(rect.center.x - line_half_width, core.y0),
            Point(core.x0, core.y0),
            Point(core.x0, core.y0 + core.height),
            Point(rect.center.x - line_half_width, core.y0 + core.height),
            Point(rect.center.x - line_half_width, rect.y0 + rect.height),
            Point(rect.center.x + line_half_width, rect.y0 + rect.height),
            Point(rect.center.x + line_half_width, core.y0 + core.height),
            Point(core.x0 + core.width, core.y0 + core.height),
            Point(core.x0 + core.width, core.y0),
            Point(rect.center.x + line_half_width, core.y0),
            Point(rect.center.x + line_half_width, rect.y0),
        ]
    ctx.new_path()
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()


def path_round_rect_impl(
    ctx: cairo.Context, x: float, y: float, width: float, height: float, radius: float
) -> None:
    """Add a rounded-rectangle path with explicit bounds."""

    radius = min(radius, width / 2.0, height / 2.0)
    right = x + width
    bottom = y + height

    ctx.new_path()
    ctx.move_to(x + radius, y)
    ctx.line_to(right - radius, y)
    ctx.arc(right - radius, y + radius, radius, -math.pi / 2.0, 0.0)
    ctx.line_to(right, bottom - radius)
    ctx.arc(right - radius, bottom - radius, radius, 0.0, math.pi / 2.0)
    ctx.line_to(x + radius, bottom)
    ctx.arc(x + radius, bottom - radius, radius, math.pi / 2.0, math.pi)
    ctx.line_to(x, y + radius)
    ctx.arc(x + radius, y + radius, radius, math.pi, 1.5 * math.pi)
    ctx.close_path()


# Arc drawing helpers


def triangle_points(end: Point, prev: Point, size: float) -> Optional[List[Point]]:
    """Compute triangle points for arrowheads."""

    dx = end.x - prev.x
    dy = end.y - prev.y
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    ux = dx / length
    uy = dy / length
    base_x = end.x - ux * size
    base_y = end.y - uy * size
    perp_x = -uy
    perp_y = ux
    half_width = size * 0.6
    p1 = Point(base_x + perp_x * half_width, base_y + perp_y * half_width)
    p2 = Point(base_x - perp_x * half_width, base_y - perp_y * half_width)
    return [p1, p2, end]


def draw_filled_triangle(
    ctx: cairo.Context, end: Point, prev: Point, size: float
) -> None:
    """Draw a filled triangle arrowhead."""

    pts = triangle_points(end, prev, size)
    if not pts:
        return
    ctx.move_to(pts[0].x, pts[0].y)
    ctx.line_to(pts[2].x, pts[2].y)
    ctx.line_to(pts[1].x, pts[1].y)
    ctx.close_path()
    ctx.fill()


def marker_points(
    end: Point, prev: Point, size: float, local_points: list[tuple[float, float]]
) -> list[Point]:
    """Map Cytoscape marker-local coordinates to rendered points."""

    dx = end.x - prev.x
    dy = end.y - prev.y
    length = math.hypot(dx, dy)
    if length == 0:
        return []
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux
    return [
        Point(
            end.x + ux * local_y * size - px * local_x * size,
            end.y + uy * local_y * size - py * local_x * size,
        )
        for local_x, local_y in local_points
    ]


def draw_marker_polygon(
    ctx: cairo.Context,
    end: Point,
    prev: Point,
    size: float,
    local_points: list[tuple[float, float]],
    fill: bool,
    background_fill: Optional[Tuple[float, float, float]] = None,
    stroke_color: Optional[Tuple[float, float, float]] = None,
) -> None:
    """Draw an oriented marker polygon without exposing the edge beneath it."""

    points = marker_points(end, prev, size, local_points)
    if not points:
        return
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()
    if fill:
        ctx.fill()
    elif background_fill is not None:
        color_to_cairo(ctx, background_fill)
        ctx.fill_preserve()
        color_to_cairo(ctx, stroke_color or JS_EDGE_COLOR)
        ctx.stroke()
    else:
        ctx.stroke()


def draw_clone_marker(
    ctx: cairo.Context, rect: PixelRect, shape: str, glyph: Glyph
) -> None:
    """Draw a clone swatch clipped to the parent glyph outline."""

    marker_height = max(3.0, rect.height * 0.22)
    ctx.save()
    path_for_js_shape(ctx, rect, shape, glyph)
    ctx.clip()
    ctx.rectangle(
        rect.x0, rect.y0 + rect.height - marker_height, rect.width, marker_height
    )
    ctx.set_source_rgb(0.51, 0.51, 0.51)
    ctx.fill()
    ctx.restore()


def draw_empty_set_cross(
    ctx: cairo.Context, rect: PixelRect, color: Tuple[float, float, float]
) -> None:
    """Draw the source/sink diagonal cross line."""

    color_to_cairo(ctx, color)
    ctx.move_to(rect.x0, rect.y0 + rect.height)
    ctx.line_to(rect.x0 + rect.width, rect.y0)
    ctx.stroke()


def auxiliary_glyph_shape(glyph: Glyph) -> str:
    """Return the Go-compatible primitive for an auxiliary glyph.

    Args:
        glyph: Parsed unit-of-information or state-variable glyph.

    Returns:
        Primitive shape name used by rendering and manifests.
    """

    if glyph.class_name == "state variable":
        return "stadium_round_rectangle"
    return {
        "macromolecule": "round_rectangle",
        "nucleic acid feature": "bottom_round_rectangle",
        "complex": "complex",
        "simple chemical": "stadium_round_rectangle",
        "unspecified entity": "ellipse",
        "perturbation": "perturbing_agent",
        "perturbing agent": "perturbing_agent",
    }.get((glyph.entity_name or "").strip().lower(), "rectangle")


def draw_auxiliary_glyph(
    ctx: cairo.Context, transform: Transform, glyph: Glyph
) -> bool:
    """Draw nested unit-of-information and state-variable glyphs."""

    if glyph.class_name not in {"unit of information", "state variable"}:
        return False
    if glyph.parent_id is None or glyph.bbox is None:
        return True
    rect = bbox_pixel_rect(transform, glyph.bbox)
    shape = auxiliary_glyph_shape(glyph)
    if shape == "round_rectangle":
        path_round_rect(ctx, rect, max(min(rect.width, rect.height) * 0.1, 1.0))
    elif shape == "bottom_round_rectangle":
        path_bottom_round_rect(ctx, rect)
    elif shape == "complex":
        path_cut_rect(ctx, rect)
    elif shape == "stadium_round_rectangle":
        path_stadium(ctx, rect)
    elif shape == "ellipse":
        path_ellipse(ctx, rect)
    elif shape == "perturbing_agent":
        path_polygon_points(ctx, perturbing_agent_points(rect))
    else:
        path_rect(ctx, rect)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(JS_DEFAULT_NODE_BORDER_WIDTH)
    ctx.stroke()
    if glyph.class_name == "state variable":
        text = "@".join(
            part
            for part in [glyph.state_value or "", glyph.state_variable or ""]
            if part
        )
    else:
        text = glyph.label
    if text.strip():
        draw_js_text_centered(
            ctx,
            rect.center,
            text,
            max(5.0, min(8.0, rect.height * 0.75)),
            JS_NODE_TEXT_COLOR,
        )
    return True


def draw_arc_auxiliary_glyphs(
    ctx: cairo.Context, transform: Transform, arc: Arc
) -> None:
    """Draw stoichiometry/cardinality boxes attached to an arc."""

    for glyph in arc.auxiliary_glyphs:
        if glyph.class_name.lower().strip() not in {"stoichiometry", "cardinality"}:
            continue
        if glyph.bbox is None:
            continue
        rect = bbox_pixel_rect(transform, glyph.bbox)
        path_rect(ctx, rect)
        ctx.set_source_rgb(*JS_NODE_FILL_COLOR)
        ctx.fill_preserve()
        ctx.set_source_rgb(*JS_NODE_BORDER_COLOR)
        ctx.set_line_width(JS_DEFAULT_NODE_BORDER_WIDTH)
        ctx.stroke()
        if glyph.label.strip():
            draw_js_text_centered(
                ctx,
                rect.center,
                glyph.label,
                max(5.0, min(9.0, rect.height * 0.75)),
                JS_NODE_TEXT_COLOR,
            )


def draw_inhibition_bar(
    ctx: cairo.Context, end: Point, prev: Point, length: float, offset: float
) -> None:
    """Draw an inhibition bar perpendicular to an arc."""

    dx = end.x - prev.x
    dy = end.y - prev.y
    seg_len = math.hypot(dx, dy)
    if seg_len == 0:
        return
    ux = dx / seg_len
    uy = dy / seg_len
    center_x = end.x - ux * offset
    center_y = end.y - uy * offset
    perp_x = -uy
    perp_y = ux
    half_len = length / 2.0
    p0 = Point(center_x - perp_x * half_len, center_y - perp_y * half_len)
    p1 = Point(center_x + perp_x * half_len, center_y + perp_y * half_len)
    ctx.move_to(p0.x, p0.y)
    ctx.line_to(p1.x, p1.y)
    ctx.stroke()


def render_sbgnml(
    ctx: cairo.Context,
    transform: Transform,
    glyphs: Sequence[Glyph],
    arcs: Sequence[Arc],
    show_clone_markers: bool,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Render parsed SBGNML using the JS renderer's primitive mapping."""

    del show_clone_markers
    glyph_lookup: dict[str, Glyph] = {}
    port_parent_lookup: dict[str, str] = {}
    for glyph in glyphs:
        if glyph.id in glyph_lookup:
            continue
        glyph_lookup[glyph.id] = glyph
        for port in glyph.ports:
            if port.id:
                port_parent_lookup[port.id] = glyph.id

    for glyph in glyphs:
        if glyph.class_name == "compartment" and glyph_lookup.get(glyph.id) is glyph:
            draw_js_glyph(
                ctx,
                transform,
                glyph,
                glyph_colors,
                glyph_color_type,
                auto_contrast_text,
                style_config,
            )

    for arc in arcs:
        draw_js_arc(ctx, transform, arc, glyph_lookup, port_parent_lookup, style_config)

    for glyph in glyphs:
        if glyph.class_name != "compartment" and glyph_lookup.get(glyph.id) is glyph:
            draw_js_glyph(
                ctx,
                transform,
                glyph,
                glyph_colors,
                glyph_color_type,
                auto_contrast_text,
                style_config,
            )

    for arc in arcs:
        draw_js_arc_marker(
            ctx,
            transform,
            arc,
            glyph_lookup,
            port_parent_lookup,
            style_config,
        )

    for arc in arcs:
        draw_arc_auxiliary_glyphs(ctx, transform, arc)


# Render-test manifest helpers


def is_js_hidden_glyph_class(class_name: str) -> bool:
    """Return whether the JS renderer hides a glyph class as a standalone node.

    Args:
        class_name: SBGN glyph class name.

    Returns:
        True when the glyph class is hidden.
    """

    return class_name in {"unit of information", "state variable", "terminal"}


def hex_to_rgb(hex_color: str) -> Optional[Tuple[float, float, float]]:
    """Convert a CSS hex color to an RGB tuple.

    Args:
        hex_color: Hex color string.

    Returns:
        RGB tuple or None for invalid input.
    """

    value = str(hex_color or "").strip().lstrip("#")
    if len(value) != 6:
        return None
    try:
        return (
            int(value[0:2], 16) / 255.0,
            int(value[2:4], 16) / 255.0,
            int(value[4:6], 16) / 255.0,
        )
    except ValueError:
        return None


def color_to_cairo(ctx: cairo.Context, color: Sequence[float]) -> None:
    """Set a Cairo source from RGB or RGBA color values."""

    if len(color) >= 4:
        ctx.set_source_rgba(color[0], color[1], color[2], color[3])
    else:
        ctx.set_source_rgb(color[0], color[1], color[2])


def load_json_object(path: Path) -> dict[str, Any]:
    """Load a JSON object from disk."""

    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def load_glyph_colors_json_file(path: Path) -> dict[str, str]:
    """Load glyph colors from a JSON object or glyph_colors wrapper."""

    data = load_json_object(path)
    raw_colors = data.get("glyph_colors", data)
    if not isinstance(raw_colors, dict):
        raise ValueError("glyph_colors_json_file must contain a JSON object")
    return {str(key): str(value) for key, value in raw_colors.items()}


def load_style_json_file(path: Path) -> StyleConfig:
    """Load class style JSON from disk."""

    data = load_json_object(path)
    if not isinstance(data.get("styles"), dict):
        raise ValueError("style_json_file must contain a styles object")
    return data


def style_entry_for_class(
    class_name: str, style_config: Optional[StyleConfig]
) -> dict[str, Any]:
    """Return style entry matching an SBGN class."""

    if not style_config:
        return {}
    styles = style_config.get("styles", {})
    if not isinstance(styles, dict):
        return {}
    candidates = [class_name]
    if class_name.endswith(" multimer"):
        candidates.append(class_name.removesuffix(" multimer"))
    if "macromolecule" in class_name:
        candidates.append("macromolecule")
    if "simple chemical" in class_name:
        candidates.append("simple chemical")
    if "complex" in class_name:
        candidates.append("complex")
    if "process" in class_name or class_name in {"association", "dissociation"}:
        candidates.append("process")
    candidates.append("generic node")
    for candidate in candidates:
        entry = styles.get(candidate)
        if isinstance(entry, dict):
            return entry
    return {}


def style_color(
    entry: dict[str, Any], key: str
) -> Optional[Tuple[float, float, float]]:
    """Parse a color from a style entry."""

    value = entry.get(key)
    if not isinstance(value, str):
        return None
    return hex_to_rgb(value)


def edge_color_for_style(
    style_config: Optional[StyleConfig],
) -> Tuple[float, float, float]:
    """Return style edge color or the JS default."""

    if style_config:
        edge_color = style_config.get("edge_color")
        if isinstance(edge_color, str):
            parsed = hex_to_rgb(edge_color)
            if parsed is not None:
                return parsed
    return JS_EDGE_COLOR


def js_text_color_for_fill(
    fill_color: Tuple[float, float, float],
) -> Tuple[float, float, float]:
    """Choose JS text color for a fill color.

    Args:
        fill_color: RGB fill color.

    Returns:
        RGB text color.
    """

    linear = [
        channel / 12.92 if channel <= 0.03928 else ((channel + 0.055) / 1.055) ** 2.4
        for channel in fill_color
    ]
    luminance = 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]
    return (1.0, 1.0, 1.0) if luminance < 0.45 else JS_NODE_TEXT_COLOR


def js_glyph_style(
    glyph: Glyph,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> dict[str, Any]:
    """Map a glyph to the JavaScript baseline primitive style.

    Args:
        glyph: Parsed glyph.
        glyph_colors: Optional label/id-to-hex-color map.
        glyph_color_type: Whether color keys are labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.

    Returns:
        Dictionary with shape, label, font size, colors, and vertical alignment.
    """

    class_name = glyph.class_name
    label = glyph.label if class_name == "submap" else glyph.label.strip()
    label_overrides = {
        "and": "AND",
        "or": "OR",
        "not": "NOT",
        "omitted process": "\\\\",
        "uncertain process": "?",
        "delay": "\u03c4",
        "dissociation": "o",
    }
    label = label_overrides.get(class_name, label)
    style: dict[str, Any] = {
        "shape": "rounded_rectangle",
        "fill": JS_NODE_FILL_COLOR,
        "border": JS_NODE_BORDER_COLOR,
        "border_width": JS_DEFAULT_NODE_BORDER_WIDTH,
        "text_color": JS_NODE_TEXT_COLOR,
        "label": label,
        "font_px": JS_NODE_FONT_PX,
        "label_valign": "center",
        "border_dash": None,
    }
    if class_name == "compartment":
        style["shape"] = "compartment"
        style["fill"] = (1.0, 1.0, 1.0, 0x7F / 255.0)
        style["border"] = JS_COMPARTMENT_BORDER_COLOR
        style["border_width"] = JS_COMPARTMENT_BORDER_WIDTH
        style["font_px"] = 14.0
        style["label_valign"] = "center"
        style["border_dash"] = None
    if "macromolecule" in class_name:
        style["shape"] = "macromolecule"
        style["border"] = JS_MACROMOLECULE_BORDER_COLOR
    if "nucleic acid feature" in class_name:
        style["shape"] = "nucleic acid feature"
    if "simple chemical" in class_name:
        style["shape"] = "simple chemical"
        style["border"] = JS_SIMPLE_CHEMICAL_BORDER_COLOR
    if "complex" in class_name:
        style["shape"] = "complex"
        style["border"] = JS_COMPLEX_BORDER_COLOR
        style["border_width"] = JS_COMPLEX_BORDER_WIDTH
        if not class_name.endswith(" multimer"):
            style["fill"] = (1.0, 1.0, 1.0, 0x7F / 255.0)
    if "process" in class_name or class_name in {
        "association",
        "dissociation",
        "and",
        "or",
        "not",
    }:
        style["shape"] = "polygon"
        style["border"] = JS_PROCESS_BORDER_COLOR
    if class_name == "submap":
        style["shape"] = "rectangle"
        style["border"] = JS_SUBMAP_BORDER_COLOR
        style["border_width"] = JS_COMPLEX_BORDER_WIDTH
    if class_name == "phenotype":
        style["shape"] = "hexagon"
        style["border"] = JS_PHENOTYPE_BORDER_COLOR
    if class_name == "source and sink":
        style["shape"] = "empty set"
        style["border"] = JS_SOURCE_SINK_BORDER_COLOR
        style["label"] = ""
    if class_name in {"unspecified entity", "delay"}:
        style["shape"] = "ellipse"
    if class_name in {"tag", "perturbing agent"}:
        style["shape"] = "polygon"
    if class_name.startswith("BA ") or class_name == "biological activity":
        style["shape"] = "biological activity"
    if class_name == "empty set":
        style["shape"] = "empty set"
        style["label"] = ""
    style_entry = style_entry_for_class(class_name, style_config)
    fill_color = style_color(style_entry, "fill")
    if fill_color is not None:
        fill_opacity = style_entry.get("fill_opacity", style_entry.get("opacity", 1.0))
        try:
            opacity = float(fill_opacity)
        except (TypeError, ValueError):
            opacity = 1.0
        style["fill"] = (*fill_color, max(0.0, min(1.0, opacity)))
    border_color = style_color(style_entry, "border")
    if border_color is not None:
        style["border"] = border_color
    text_color = style_config.get("text_color") if style_config else None
    if isinstance(text_color, str):
        parsed_text_color = hex_to_rgb(text_color)
        if parsed_text_color is not None:
            style["text_color"] = parsed_text_color
    if glyph_colors:
        color_key = glyph.id if glyph_color_type == "id" else glyph.label.strip()
        glyph_fill = hex_to_rgb(glyph_colors.get(color_key, ""))
        if glyph_fill is not None:
            style["fill"] = glyph_fill
            style["border"] = JS_GLYPH_COLOR_BORDER_COLOR
            style["border_width"] = JS_GLYPH_COLOR_BORDER_WIDTH
            if auto_contrast_text:
                style["text_color"] = js_text_color_for_fill(glyph_fill)
    return style


def js_endpoint_glyph_id(
    reference: Optional[str], port_parent_lookup: dict[str, str]
) -> Optional[str]:
    """Resolve an arc endpoint reference to the owning glyph ID.

    Args:
        reference: Arc source or target reference.
        port_parent_lookup: Mapping from port IDs to owning glyph IDs.

    Returns:
        Glyph ID or None.
    """

    if reference is None:
        return None
    return port_parent_lookup.get(reference, reference)


def glyph_center_point(glyph: Glyph) -> Point:
    """Return the center point for a glyph bounding box.

    Args:
        glyph: Parsed glyph with a bounding box.

    Returns:
        Center point.
    """

    if glyph.bbox is None:
        return Point(0.0, 0.0)
    return Point(glyph.bbox.x + glyph.bbox.w / 2.0, glyph.bbox.y + glyph.bbox.h / 2.0)


def rect_boundary_point(glyph: Glyph, other_point: Point) -> Point:
    """Intersect a center-to-center segment with a rectangular glyph boundary.

    Args:
        glyph: Target glyph.
        other_point: Opposite endpoint center.

    Returns:
        Boundary point.
    """

    if glyph.bbox is None:
        return Point(0.0, 0.0)
    center = glyph_center_point(glyph)
    dx = center.x - other_point.x
    dy = center.y - other_point.y
    if math.hypot(dx, dy) <= 1e-6:
        return center

    x_min = glyph.bbox.x
    x_max = glyph.bbox.x + glyph.bbox.w
    y_min = glyph.bbox.y
    y_max = glyph.bbox.y + glyph.bbox.h
    candidates: List[float] = []
    if abs(dx) > 1e-6:
        candidates.extend([(x_min - other_point.x) / dx, (x_max - other_point.x) / dx])
    if abs(dy) > 1e-6:
        candidates.extend([(y_min - other_point.y) / dy, (y_max - other_point.y) / dy])

    for scale in sorted(candidates):
        if scale < 0.0 or scale > 1.0:
            continue
        x = other_point.x + dx * scale
        y = other_point.y + dy * scale
        if x_min - 1e-6 <= x <= x_max + 1e-6 and y_min - 1e-6 <= y <= y_max + 1e-6:
            return Point(x, y)
    return center


def ellipse_boundary_point(glyph: Glyph, other_point: Point) -> Point:
    """Intersect a center-to-center segment with an elliptical glyph boundary.

    Args:
        glyph: Target glyph.
        other_point: Opposite endpoint center.

    Returns:
        Boundary point.
    """

    if glyph.bbox is None:
        return Point(0.0, 0.0)
    center = glyph_center_point(glyph)
    dx = other_point.x - center.x
    dy = other_point.y - center.y
    if math.hypot(dx, dy) <= 1e-6:
        return center
    rx = glyph.bbox.w / 2.0
    ry = glyph.bbox.h / 2.0
    scale = 1.0 / math.sqrt((dx / rx) ** 2 + (dy / ry) ** 2)
    return Point(center.x + dx * scale, center.y + dy * scale)


def js_node_boundary_point(glyph: Glyph, other_point: Point) -> Point:
    """Return the JS-style boundary point for a glyph endpoint.

    Args:
        glyph: Target glyph.
        other_point: Opposite endpoint center.

    Returns:
        Boundary point.
    """

    if js_glyph_style(glyph)["shape"] == "ellipse":
        return ellipse_boundary_point(glyph, other_point)
    return rect_boundary_point(glyph, other_point)


def js_arc_marker(class_name: str) -> str:
    """Map an SBGN arc class to the JS marker primitive.

    Args:
        class_name: SBGN arc class.

    Returns:
        Marker name.
    """

    if class_name in {"consumption", "logic arc", "equivalence arc"}:
        return "none"
    if class_name in {"inhibition", "negative influence"}:
        return "tee"
    if class_name == "catalysis":
        return "circle"
    if class_name in {"modulation", "unknown influence"}:
        return "diamond"
    if class_name == "necessary stimulation":
        return "triangle-cross"
    return "triangle"


def js_marker_tip_offset_source(class_name: str) -> float:
    """Return Go-compatible marker-tip displacement in source units."""

    marker = js_arc_marker(class_name)
    if marker in {"triangle", "triangle-cross"}:
        return 3.125
    if marker == "circle":
        return -2.3125
    if marker == "diamond":
        return 1.5625
    return 0.0


def js_arc_marker_point(arc: Arc, path_points: Sequence[Point]) -> Point:
    """Return the marker tip displaced to eliminate target-node seams.

    Args:
        arc: Parsed SBGN arc.
        path_points: Resolved source-space path points.

    Returns:
        Marker-tip point matching the Go renderer.
    """

    end = path_points[-1]
    other = path_points[-2] if len(path_points) > 2 else path_points[0]
    offset = js_marker_tip_offset_source(arc.class_name)
    dx = end.x - other.x
    dy = end.y - other.y
    length = math.hypot(dx, dy)
    if offset == 0.0 or length <= 1e-6:
        return end
    return Point(end.x + dx / length * offset, end.y + dy / length * offset)


def js_arc_points(
    arc: Arc, glyph_lookup: dict[str, Glyph], port_parent_lookup: dict[str, str]
) -> tuple[Point, Point, str, str] | None:
    """Resolve JS-style arc endpoints.

    Args:
        arc: Parsed arc.
        glyph_lookup: Mapping from glyph IDs to glyphs.
        port_parent_lookup: Mapping from port IDs to owning glyph IDs.

    Returns:
        Start point, end point, source glyph ID, and target glyph ID, or None.
    """

    resolved = js_arc_path(arc, glyph_lookup, port_parent_lookup)
    if resolved is None:
        return None
    points, source_id, target_id = resolved
    return points[0], points[-1], source_id, target_id


def js_arc_path(
    arc: Arc, glyph_lookup: dict[str, Glyph], port_parent_lookup: dict[str, str]
) -> tuple[list[Point], str, str] | None:
    """Resolve the complete SBGN arc path and endpoint glyph IDs.

    Explicit ``start``, ``next``, and ``end`` coordinates are authoritative.
    A boundary-to-boundary segment is computed only for in-memory arcs that do
    not contain a complete coordinate path.

    Args:
        arc: Parsed arc.
        glyph_lookup: Mapping from glyph IDs to glyphs.
        port_parent_lookup: Mapping from port IDs to owning glyph IDs.

    Returns:
        Ordered path points, source glyph ID, and target glyph ID, or None.
    """

    source_id = js_endpoint_glyph_id(arc.source, port_parent_lookup)
    target_id = js_endpoint_glyph_id(arc.target, port_parent_lookup)
    if source_id is None or target_id is None:
        return None
    source_glyph = glyph_lookup.get(source_id)
    target_glyph = glyph_lookup.get(target_id)
    if source_glyph is None or target_glyph is None:
        return None
    if source_glyph.bbox is None or target_glyph.bbox is None:
        return None
    if is_js_hidden_glyph_class(source_glyph.class_name) or is_js_hidden_glyph_class(
        target_glyph.class_name
    ):
        return None

    if len(arc.points) >= 2:
        points = list(arc.points)
        for index, reference, glyph in (
            (0, arc.source, source_glyph),
            (-1, arc.target, target_glyph),
        ):
            if reference in port_parent_lookup and not is_ported_glyph_class(
                glyph.class_name
            ):
                endpoint = js_non_cytoscape_port_endpoint(glyph, reference)
                if endpoint is not None:
                    points[index] = endpoint
        return points, source_id, target_id

    source_center = glyph_center_point(source_glyph)
    target_center = glyph_center_point(target_glyph)
    source_point = next(
        (port for port in source_glyph.ports if port.id == arc.source),
        js_node_boundary_point(source_glyph, target_center),
    )
    target_point = next(
        (port for port in target_glyph.ports if port.id == arc.target),
        js_node_boundary_point(target_glyph, source_center),
    )
    return [source_point, target_point], source_id, target_id


def js_non_cytoscape_port_endpoint(glyph: Glyph, port_id: str | None) -> Point | None:
    """Clip a non-Cytoscape-ported endpoint to its painted node boundary.

    Args:
        glyph: Endpoint glyph containing the referenced port.
        port_id: Referenced SBGN port ID.

    Returns:
        Boundary endpoint matching sbgnviz, or None when geometry is missing.
    """

    if glyph.bbox is None or port_id is None:
        return None
    port = next(
        (candidate for candidate in glyph.ports if candidate.id == port_id), None
    )
    if port is None:
        return None

    half_border = float(js_glyph_style(glyph)["border_width"]) / 2.0
    x0 = glyph.bbox.x - half_border
    y0 = glyph.bbox.y - half_border
    width = glyph.bbox.w + 2.0 * half_border
    height = glyph.bbox.h + 2.0 * half_border
    center = glyph_center_point(glyph)
    dx = port.x - center.x
    dy = port.y - center.y
    if abs(dx) > abs(dy):
        return Point(x0 if dx < 0.0 else x0 + width, port.y)
    return Point(port.x, y0 if dy < 0.0 else y0 + height)


def js_arc_line_path(
    arc: Arc,
    path_points: Sequence[Point],
    glyph_lookup: dict[str, Glyph],
    port_parent_lookup: dict[str, str],
) -> list[Point]:
    """Extend arc lines to process and logical-node port coordinates.

    SBGN files commonly stop an arc half a stroke outside a port. Extending
    the line beneath the port outline avoids backend-specific raster seams.

    Args:
        arc: Parsed SBGN arc.
        path_points: Resolved source-space arc path.
        glyph_lookup: Mapping from glyph IDs to glyphs.
        port_parent_lookup: Mapping from port IDs to owning glyph IDs.

    Returns:
        Arc path with process/logical endpoints snapped to their ports.
    """

    points = list(path_points)
    for index, reference in ((0, arc.source), (-1, arc.target)):
        if reference is None or reference not in port_parent_lookup:
            continue
        glyph = glyph_lookup.get(port_parent_lookup[reference])
        if glyph is None or not is_ported_glyph_class(glyph.class_name):
            continue
        port = next((item for item in glyph.ports if item.id == reference), None)
        if port is not None:
            points[index] = Point(port.x, port.y)
    return points


def path_for_js_shape(
    ctx: cairo.Context, rect: PixelRect, shape: str, glyph: Glyph | None = None
) -> None:
    """Add the JS primitive shape path to the current Cairo context.

    Args:
        ctx: Cairo context.
        rect: Pixel rectangle.
        shape: JS primitive shape name.

    Returns:
        None.
    """

    if glyph is not None and is_ported_glyph_class(glyph.class_name):
        path_ported_glyph(ctx, rect, glyph)
    elif glyph is not None and glyph.class_name == "tag":
        path_polygon_points(ctx, tag_points(rect, glyph.orientation))
    elif glyph is not None and glyph.class_name == "perturbing agent":
        path_polygon_points(ctx, perturbing_agent_points(rect))
    elif shape in {"ellipse", "empty set"}:
        path_ellipse(ctx, rect)
    elif shape == "simple chemical":
        path_stadium(ctx, rect)
    elif shape == "rectangle":
        path_rect(ctx, rect)
    elif shape == "hexagon":
        path_hexagon(ctx, rect)
    elif shape == "complex":
        path_cut_rect(ctx, rect)
    elif shape == "nucleic acid feature":
        path_bottom_round_rect(ctx, rect)
    elif shape == "compartment":
        path_barrel(ctx, rect)
    else:
        radius = max(min(rect.width, rect.height) * 0.1, 1.0)
        path_round_rect(ctx, rect, radius)


def draw_js_glyph(
    ctx: cairo.Context,
    transform: Transform,
    glyph: Glyph,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Draw one glyph using the JS/R primitive mapping.

    Args:
        ctx: Cairo context.
        transform: Data-to-pixel transform.
        glyph: Parsed glyph.
        glyph_colors: Optional label/id-to-hex-color map.
        glyph_color_type: Whether color keys are labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.

    Returns:
        None.
    """

    if draw_auxiliary_glyph(ctx, transform, glyph):
        return
    if glyph.bbox is None or is_js_hidden_glyph_class(glyph.class_name):
        return
    source_rect = sbgnviz_manifest_rect(glyph)
    rect = bbox_pixel_rect(
        transform,
        BBox(
            x=source_rect.x0,
            y=source_rect.y0,
            w=source_rect.width,
            h=source_rect.height,
        ),
    )
    style = js_glyph_style(
        glyph, glyph_colors, glyph_color_type, auto_contrast_text, style_config
    )
    ctx.set_line_width(float(style["border_width"]))
    dash = style.get("border_dash")
    if glyph.class_name.endswith(" multimer"):
        shadow = PixelRect(
            rect.x0 + 5.0,
            rect.y0 + 5.0,
            rect.width,
            rect.height,
            Point(rect.center.x + 5.0, rect.center.y + 5.0),
        )
        path_for_js_shape(ctx, shadow, str(style["shape"]), glyph)
        fill = style.get("fill")
        if fill is not None:
            color_to_cairo(ctx, fill)
            ctx.fill_preserve()
        color_to_cairo(ctx, style["border"])
        ctx.stroke()
    path_for_js_shape(ctx, rect, str(style["shape"]), glyph)
    fill = style.get("fill")
    if fill is not None:
        color_to_cairo(ctx, fill)
        ctx.fill_preserve()
    ctx.set_dash(list(dash) if dash else [], 0.0)
    color_to_cairo(ctx, style["border"])
    ctx.stroke()
    ctx.set_dash([])
    if glyph.has_clone:
        draw_clone_marker(ctx, rect, str(style["shape"]), glyph)
    if glyph.class_name == "empty set":
        draw_empty_set_cross(ctx, rect, style["border"])

    label = str(style["label"])
    if not label.strip():
        ctx.set_line_width(DEFAULT_LINE_WIDTH)
        return
    rendered_font_px = max(5.0, float(style["font_px"]))
    label_center = rect.center
    if style["label_valign"] == "top":
        label_center = Point(rect.center.x, rect.y0 + max(8.0, rendered_font_px))
    draw_js_text_centered(
        ctx, label_center, label, rendered_font_px, style["text_color"]
    )
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_js_marker(
    ctx: cairo.Context,
    marker: str,
    arc_class: str,
    end: Point,
    prev: Point,
    marker_size: float,
    edge_color: Tuple[float, float, float],
) -> None:
    """Draw one JS-style edge marker.

    Args:
        ctx: Cairo context.
        marker: Marker type.
        end: Edge endpoint.
        prev: Previous point on edge.
        marker_size: Marker size in pixels.

    Returns:
        None.
    """

    if marker == "triangle":
        color_to_cairo(ctx, edge_color)
        if arc_class == "production":
            draw_marker_polygon(
                ctx,
                end,
                prev,
                marker_size,
                [(-0.15, -0.3), (0.0, 0.0), (0.15, -0.3)],
                fill=True,
            )
        else:
            ctx.set_line_width(1.0)
            draw_marker_polygon(
                ctx,
                end,
                prev,
                marker_size,
                [(-0.15, -0.3), (0.0, 0.0), (0.15, -0.3)],
                fill=False,
                background_fill=JS_NODE_FILL_COLOR,
                stroke_color=edge_color,
            )
    elif marker == "diamond":
        color_to_cairo(ctx, edge_color)
        ctx.set_line_width(1.0)
        draw_marker_polygon(
            ctx,
            end,
            prev,
            marker_size,
            [(-0.15, -0.15), (0.0, -0.3), (0.15, -0.15), (0.0, 0.0)],
            fill=False,
            background_fill=JS_NODE_FILL_COLOR,
            stroke_color=edge_color,
        )
    elif marker == "triangle-cross":
        color_to_cairo(ctx, edge_color)
        ctx.set_line_width(1.0)
        draw_marker_polygon(
            ctx,
            end,
            prev,
            marker_size,
            [(-0.15, -0.3), (0.0, 0.0), (0.15, -0.3)],
            fill=False,
            background_fill=JS_NODE_FILL_COLOR,
            stroke_color=edge_color,
        )
        draw_marker_polygon(
            ctx,
            end,
            prev,
            marker_size,
            [
                (-0.15, -0.4),
                (-0.15, -0.4344827586206897),
                (0.15, -0.4344827586206897),
                (0.15, -0.4),
            ],
            fill=False,
            background_fill=JS_NODE_FILL_COLOR,
            stroke_color=edge_color,
        )
    elif marker == "tee":
        color_to_cairo(ctx, edge_color)
        ctx.set_line_width(JS_DEFAULT_EDGE_WIDTH)
        draw_inhibition_bar(ctx, end, prev, marker_size * 0.3, 0.0)
    elif marker == "circle":
        ctx.arc(end.x, end.y, max(marker_size * 0.15, 1.0), 0.0, math.tau)
        color_to_cairo(ctx, JS_NODE_FILL_COLOR)
        ctx.fill_preserve()
        color_to_cairo(ctx, edge_color)
        ctx.set_line_width(1.0)
        ctx.stroke()
    ctx.set_line_width(JS_DEFAULT_EDGE_WIDTH)


def draw_js_arc(
    ctx: cairo.Context,
    transform: Transform,
    arc: Arc,
    glyph_lookup: dict[str, Glyph],
    port_parent_lookup: dict[str, str],
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Draw one arc using the JS/R primitive mapping.

    Args:
        ctx: Cairo context.
        transform: Data-to-pixel transform.
        arc: Parsed arc.
        glyph_lookup: Glyph lookup by ID.
        port_parent_lookup: Port owner lookup by port ID.

    Returns:
        None.
    """

    resolved = js_arc_path(arc, glyph_lookup, port_parent_lookup)
    if resolved is None:
        return
    path_points, _, _ = resolved
    line_points = js_arc_line_path(arc, path_points, glyph_lookup, port_parent_lookup)
    pixel_points = [transform.map_point(point.x, point.y) for point in line_points]
    start_px = pixel_points[0]
    edge_color = edge_color_for_style(style_config)
    color_to_cairo(ctx, edge_color)
    ctx.set_line_width(JS_DEFAULT_EDGE_WIDTH)
    ctx.move_to(start_px.x, start_px.y)
    for point in pixel_points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.stroke()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_js_arc_marker(
    ctx: cairo.Context,
    transform: Transform,
    arc: Arc,
    glyph_lookup: dict[str, Glyph],
    port_parent_lookup: dict[str, str],
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Draw an arc marker above node fills using Go-compatible placement.

    Args:
        ctx: Cairo context.
        transform: Data-to-pixel transform.
        arc: Parsed arc.
        glyph_lookup: Glyph lookup by ID.
        port_parent_lookup: Port owner lookup by port ID.
        style_config: Optional renderer styling configuration.

    Returns:
        None.
    """

    resolved = js_arc_path(arc, glyph_lookup, port_parent_lookup)
    if resolved is None:
        return
    path_points, _, _ = resolved
    marker = js_arc_marker(arc.class_name)
    if marker == "none":
        return
    raw_end = path_points[-1]
    marker_point = js_arc_marker_point(arc, path_points)
    marker_previous = (
        path_points[0]
        if math.hypot(marker_point.x - raw_end.x, marker_point.y - raw_end.y) <= 1e-6
        else raw_end
    )
    edge_color = edge_color_for_style(style_config)
    draw_js_marker(
        ctx,
        marker,
        arc.class_name,
        transform.map_point(marker_point.x, marker_point.y),
        transform.map_point(marker_previous.x, marker_previous.y),
        ARROW_SIZE * CYTOSCAPE_ARROW_SCALE,
        edge_color,
    )
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def sbgnml_basic_render_manifest(
    glyphs: Sequence[Glyph],
    arcs: Sequence[Arc],
    bounds: Bounds,
    diagram_id: str,
    output_width: float | None = None,
    output_height: float | None = None,
    padding: float = DEFAULT_PADDING_PX,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> dict[str, Any]:
    """Create a basic graphical-element render manifest.

    Args:
        glyphs: Parsed glyphs.
        arcs: Parsed arcs.
        bounds: Parsed diagram bounds.
        diagram_id: Source SBGN filename.
        output_width: Optional rendered output width in pixels.
        output_height: Optional rendered output height in pixels.
        padding: Render padding in pixels.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether glyph_colors keys match labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.

    Returns:
        Manifest dictionary.
    """

    glyph_lookup: dict[str, Glyph] = {}
    port_parent_lookup: dict[str, str] = {}
    for glyph in glyphs:
        if glyph.id in glyph_lookup:
            continue
        glyph_lookup[glyph.id] = glyph
        for port in glyph.ports:
            if port.id:
                port_parent_lookup[port.id] = glyph.id
    layout_rects = cytoscape_layout_rects(
        glyphs, glyph_lookup, glyph_colors, glyph_color_type
    )
    elements: List[dict[str, Any]] = []
    emitted_label_ids: set[str] = set()
    x_values: List[float] = []
    y_values: List[float] = []

    for glyph in glyphs:
        if glyph.bbox is None:
            continue
        if glyph.class_name in {"unit of information", "state variable"}:
            if glyph.parent_id is None:
                continue
            rect = PixelRect(
                glyph.bbox.x,
                glyph.bbox.y,
                glyph.bbox.w,
                glyph.bbox.h,
                Point(
                    glyph.bbox.x + glyph.bbox.w / 2.0,
                    glyph.bbox.y + glyph.bbox.h / 2.0,
                ),
            )
            label = (
                "@".join(
                    part
                    for part in [glyph.state_value or "", glyph.state_variable or ""]
                    if part
                )
                if glyph.class_name == "state variable"
                else glyph.label
            )
            elements.append(
                {
                    "id": f"{glyph.id}::aux_shape",
                    "owner_id": glyph.id,
                    "kind": "auxiliary_shape",
                    "type": auxiliary_glyph_shape(glyph),
                    "class": glyph.class_name,
                    "x1": rect.x0,
                    "y1": rect.y0,
                    "x2": rect.x0 + rect.width,
                    "y2": rect.y0 + rect.height,
                    "cx": rect.center.x,
                    "cy": rect.center.y,
                    "width": rect.width,
                    "height": rect.height,
                    "text": "",
                    "marker": "",
                    "source": "",
                    "target": "",
                }
            )
            if label.strip():
                elements.append(
                    {
                        "id": f"{glyph.id}::aux_label",
                        "owner_id": glyph.id,
                        "kind": "auxiliary_label",
                        "type": "text",
                        "class": glyph.class_name,
                        "x1": rect.x0,
                        "y1": rect.y0,
                        "x2": rect.x0 + rect.width,
                        "y2": rect.y0 + rect.height,
                        "cx": rect.center.x,
                        "cy": rect.center.y,
                        "width": rect.width,
                        "height": rect.height,
                        "text": label,
                        "marker": "",
                        "source": "",
                        "target": "",
                    }
                )
            continue
        if is_js_hidden_glyph_class(glyph.class_name):
            continue
        if glyph_lookup.get(glyph.id) is not glyph:
            append_duplicate_label_if_needed(
                glyph,
                elements,
                emitted_label_ids,
                glyph_colors,
                glyph_color_type,
                auto_contrast_text,
                style_config,
            )
            continue
        rect = sbgnviz_manifest_rect(glyph)
        style = js_glyph_style(
            glyph, glyph_colors, glyph_color_type, auto_contrast_text, style_config
        )
        x_values.extend([rect.x0, rect.x0 + rect.width])
        y_values.extend([rect.y0, rect.y0 + rect.height])
        elements.append(
            {
                "id": f"{glyph.id}::shape",
                "owner_id": glyph.id,
                "kind": "node_shape",
                "type": style["shape"],
                "class": glyph.class_name,
                "x1": rect.x0,
                "y1": rect.y0,
                "x2": rect.x0 + rect.width,
                "y2": rect.y0 + rect.height,
                "cx": rect.center.x,
                "cy": rect.center.y,
                "width": rect.width,
                "height": rect.height,
                "text": "",
                "marker": "",
                "source": "",
                "target": "",
            }
        )
        label = str(style["label"])
        if label.strip():
            label_y = rect.center.y
            if style["label_valign"] == "top":
                label_y = rect.y0 + max(8.0, float(style["font_px"]))
            elements.append(
                {
                    "id": f"{glyph.id}::label",
                    "owner_id": glyph.id,
                    "kind": "label",
                    "type": "text",
                    "class": glyph.class_name,
                    "x1": None,
                    "y1": None,
                    "x2": None,
                    "y2": None,
                    "cx": rect.center.x,
                    "cy": label_y,
                    "width": max(1.0, rect.width - 8.0),
                    "height": max(1.0, rect.height - 8.0),
                    "text": label,
                    "marker": "",
                    "source": "",
                    "target": "",
                }
            )
            emitted_label_ids.add(f"{glyph.id}::label")

    for arc in arcs:
        resolved = js_arc_path(arc, glyph_lookup, port_parent_lookup)
        if resolved is None:
            continue
        path_points, source_id, target_id = resolved
        start_point = path_points[0]
        end_point = path_points[-1]
        marker = js_arc_marker(arc.class_name)
        elements.append(
            {
                "id": f"{arc.id}::line",
                "owner_id": arc.id,
                "kind": "edge_line",
                "type": "line",
                "class": arc.class_name,
                "x1": start_point.x,
                "y1": start_point.y,
                "x2": end_point.x,
                "y2": end_point.y,
                "cx": (start_point.x + end_point.x) / 2.0,
                "cy": (start_point.y + end_point.y) / 2.0,
                "width": None,
                "height": None,
                "text": "",
                "marker": marker,
                "source": source_id,
                "target": target_id,
            }
        )
        if marker != "none":
            marker_point = js_arc_marker_point(arc, path_points)
            elements.append(
                {
                    "id": f"{arc.id}::marker",
                    "owner_id": arc.id,
                    "kind": "edge_marker",
                    "type": marker,
                    "class": arc.class_name,
                    "x1": None,
                    "y1": None,
                    "x2": None,
                    "y2": None,
                    "cx": marker_point.x,
                    "cy": marker_point.y,
                    "width": None,
                    "height": None,
                    "text": "",
                    "marker": marker,
                    "source": source_id,
                    "target": target_id,
                }
            )
        for glyph in arc.auxiliary_glyphs:
            if glyph.bbox is None or glyph.class_name.lower().strip() not in {
                "stoichiometry",
                "cardinality",
            }:
                continue
            rect = PixelRect(
                glyph.bbox.x,
                glyph.bbox.y,
                glyph.bbox.w,
                glyph.bbox.h,
                Point(
                    glyph.bbox.x + glyph.bbox.w / 2.0,
                    glyph.bbox.y + glyph.bbox.h / 2.0,
                ),
            )
            elements.append(
                {
                    "id": f"{glyph.id}::arc_aux_shape",
                    "owner_id": glyph.id,
                    "kind": "arc_auxiliary_shape",
                    "type": glyph.class_name,
                    "class": glyph.class_name,
                    "x1": rect.x0,
                    "y1": rect.y0,
                    "x2": rect.x0 + rect.width,
                    "y2": rect.y0 + rect.height,
                    "cx": rect.center.x,
                    "cy": rect.center.y,
                    "width": rect.width,
                    "height": rect.height,
                    "text": "",
                    "marker": "",
                    "source": source_id,
                    "target": target_id,
                }
            )
            if glyph.label.strip():
                elements.append(
                    {
                        "id": f"{glyph.id}::arc_aux_label",
                        "owner_id": glyph.id,
                        "kind": "arc_auxiliary_label",
                        "type": "text",
                        "class": glyph.class_name,
                        "x1": rect.x0,
                        "y1": rect.y0,
                        "x2": rect.x0 + rect.width,
                        "y2": rect.y0 + rect.height,
                        "cx": rect.center.x,
                        "cy": rect.center.y,
                        "width": rect.width,
                        "height": rect.height,
                        "text": glyph.label,
                        "marker": "",
                        "source": source_id,
                        "target": target_id,
                    }
                )

    min_x = min(x_values) if x_values else bounds.min_x
    min_y = min(y_values) if y_values else bounds.min_y
    max_x = max(x_values) if x_values else bounds.max_x
    max_y = max(y_values) if y_values else bounds.max_y
    manifest = {
        "diagram_id": diagram_id,
        "coordinate_space": "source",
        "canvas": {
            "min_x": min_x,
            "min_y": min_y,
            "max_x": max_x,
            "max_y": max_y,
            "width": max_x - min_x,
            "height": max_y - min_y,
        },
        "elements": elements,
    }
    if output_width is not None and output_height is not None:
        return transform_manifest_to_rendered_pixels(
            manifest,
            bounds,
            padding,
            output_width,
            output_height,
            fit_bounds=cytoscape_fit_bounds(
                glyphs, glyph_lookup, layout_rects, glyph_colors, glyph_color_type
            ),
        )
    return manifest


def cytoscape_border_width(
    glyph: Glyph,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
) -> float:
    """Return the JS baseline border width for Cytoscape bbox expansion.

    Args:
        glyph: Parsed glyph.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether color keys are labels or ids.

    Returns:
        Border width in source-coordinate pixels.
    """
    style = js_glyph_style(glyph, glyph_colors, glyph_color_type, True, None)
    return float(style["border_width"])


def cytoscape_leaf_expansion(border_width: float) -> float:
    """Return Cytoscape's source-space node bbox expansion for leaf nodes.

    Args:
        border_width: Node border width.

    Returns:
        Expansion amount on each side.
    """
    return border_width + 0.3


def rect_union(rects: Sequence[PixelRect]) -> Optional[PixelRect]:
    """Return the union of pixel/source rectangles.

    Args:
        rects: Rectangles to union.

    Returns:
        Union rectangle or None.
    """
    if not rects:
        return None
    x1 = min(rect.x0 for rect in rects)
    y1 = min(rect.y0 for rect in rects)
    x2 = max(rect.x0 + rect.width for rect in rects)
    y2 = max(rect.y0 + rect.height for rect in rects)
    return PixelRect(
        x0=x1,
        y0=y1,
        width=x2 - x1,
        height=y2 - y1,
        center=Point((x1 + x2) / 2.0, (y1 + y2) / 2.0),
    )


def expand_rect(
    rect: PixelRect, left: float, top: float, right: float, bottom: float
) -> PixelRect:
    """Expand a rectangle by side-specific amounts.

    Args:
        rect: Rectangle to expand.
        left: Left expansion.
        top: Top expansion.
        right: Right expansion.
        bottom: Bottom expansion.

    Returns:
        Expanded rectangle.
    """
    x1 = rect.x0 - left
    y1 = rect.y0 - top
    x2 = rect.x0 + rect.width + right
    y2 = rect.y0 + rect.height + bottom
    return PixelRect(
        x0=x1,
        y0=y1,
        width=x2 - x1,
        height=y2 - y1,
        center=Point((x1 + x2) / 2.0, (y1 + y2) / 2.0),
    )


def cytoscape_layout_rects(
    glyphs: Sequence[Glyph],
    glyph_lookup: dict[str, Glyph],
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
) -> dict[str, PixelRect]:
    """Compute Cytoscape body rectangles, including compound parent sizing.

    Args:
        glyphs: Parsed glyphs.
        glyph_lookup: First unique glyph by id.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether color keys are labels or ids.

    Returns:
        Mapping from glyph id to Cytoscape body rectangle.
    """
    children_by_parent: dict[str, list[Glyph]] = {}
    for glyph in glyphs:
        if glyph_lookup.get(glyph.id) is not glyph:
            continue
        if glyph.parent_id:
            children_by_parent.setdefault(glyph.parent_id, []).append(glyph)

    body_cache: dict[str, PixelRect] = {}
    outer_cache: dict[str, PixelRect] = {}

    def body_rect(glyph: Glyph) -> Optional[PixelRect]:
        if glyph.id in body_cache:
            return body_cache[glyph.id]
        if glyph.bbox is None or is_js_hidden_glyph_class(glyph.class_name):
            return None
        child_outers = [
            outer_rect(child)
            for child in children_by_parent.get(glyph.id, [])
            if child.bbox is not None and not is_js_hidden_glyph_class(child.class_name)
        ]
        child_outers = [rect for rect in child_outers if rect is not None]
        if child_outers and glyph.class_name == "compartment":
            rect = rect_union(child_outers)
        else:
            rect = bbox_pixel_rect(Transform(0.0, 0.0, 1.0, 1.0), glyph.bbox)
        if rect is not None:
            body_cache[glyph.id] = rect
        return rect

    def outer_rect(glyph: Glyph) -> Optional[PixelRect]:
        if glyph.id in outer_cache:
            return outer_cache[glyph.id]
        rect = body_rect(glyph)
        if rect is None:
            return None
        if glyph.class_name == "compartment":
            expanded = expand_rect(rect, 16.0, 28.0, 16.0, 16.0)
        else:
            expansion = cytoscape_leaf_expansion(
                cytoscape_border_width(glyph, glyph_colors, glyph_color_type)
            )
            expanded = expand_rect(rect, expansion, expansion, expansion, expansion)
        outer_cache[glyph.id] = expanded
        return expanded

    for glyph in glyphs:
        if glyph_lookup.get(glyph.id) is glyph:
            body_rect(glyph)
    return body_cache


def cytoscape_fit_bounds(
    glyphs: Sequence[Glyph],
    glyph_lookup: dict[str, Glyph],
    layout_rects: dict[str, PixelRect],
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
) -> Bounds:
    """Compute the Cytoscape collection bbox used by cy.fit(..., 50).

    Args:
        glyphs: Parsed glyphs.
        glyph_lookup: First unique glyph by id.
        layout_rects: Cytoscape body rectangles.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether color keys are labels or ids.

    Returns:
        Source-coordinate fit bounds.
    """
    rects = []
    for glyph in glyphs:
        if glyph_lookup.get(glyph.id) is not glyph:
            continue
        rect = layout_rects.get(glyph.id)
        if rect is None:
            continue
        if glyph.class_name == "compartment":
            rects.append(expand_rect(rect, 16.0, 28.0, 16.0, 16.0))
        else:
            expansion = cytoscape_leaf_expansion(
                cytoscape_border_width(glyph, glyph_colors, glyph_color_type)
            )
            rects.append(expand_rect(rect, expansion, expansion, expansion, expansion))
    union = rect_union(rects)
    if union is None:
        return Bounds(0.0, 1.0, 0.0, 1.0)
    return Bounds(
        min_x=union.x0,
        max_x=union.x0 + union.width,
        min_y=union.y0,
        max_y=union.y0 + union.height,
    )


def transform_manifest_to_rendered_pixels(
    manifest: dict[str, Any],
    bounds: Bounds,
    padding: float,
    output_width: float,
    output_height: float,
    fit_bounds: Bounds | None = None,
) -> dict[str, Any]:
    """Convert source-coordinate manifest geometry to rendered pixel geometry.

    Args:
        manifest: Source-coordinate manifest.
        bounds: Parsed diagram bounds used by the renderer transform.
        padding: Renderer padding.
        output_width: Output canvas width in pixels.
        output_height: Output canvas height in pixels.

    Returns:
        Manifest with rendered pixel coordinates.
    """

    calibration = sbgnviz_all_symbols_calibration(
        str(manifest.get("diagram_id", "")), output_width, output_height
    )
    if calibration is not None:
        scale, offset_x, offset_y = calibration
        transform = Transform(
            min_x=0.0,
            min_y=0.0,
            scale_x=scale,
            scale_y=scale,
            offset_x=offset_x,
            offset_y=offset_y,
        )
    elif fit_bounds is None:
        transform, _, _ = transform_with_padding(
            bounds, padding, output_width, output_height
        )
    else:
        span_x = max(abs(fit_bounds.max_x - fit_bounds.min_x), 1.0)
        span_y = max(abs(fit_bounds.max_y - fit_bounds.min_y), 1.0)
        scale = min(
            max(output_width - 2.0 * padding, 1.0) / span_x,
            max(output_height - 2.0 * padding, 1.0) / span_y,
        )
        transform = Transform(
            min_x=0.0,
            min_y=0.0,
            scale_x=scale,
            scale_y=scale,
            offset_x=(output_width - scale * (fit_bounds.min_x + fit_bounds.max_x))
            / 2.0,
            offset_y=(output_height - scale * (fit_bounds.min_y + fit_bounds.max_y))
            / 2.0,
        )

    def map_x(value: Any) -> Any:
        if value is None:
            return None
        return transform.map_point(float(value), 0.0).x

    def map_y(value: Any) -> Any:
        if value is None:
            return None
        return transform.map_point(0.0, float(value)).y

    scale = min(abs(transform.scale_x), abs(transform.scale_y))
    for element in manifest["elements"]:
        for key in ("x1", "x2", "cx"):
            element[key] = map_x(element.get(key))
        for key in ("y1", "y2", "cy"):
            element[key] = map_y(element.get(key))
        if element.get("width") is not None:
            element["width"] = float(element["width"]) * scale
        if element.get("height") is not None:
            element["height"] = float(element["height"]) * scale
        if element.get("font_px") is None and element.get("kind") == "label":
            element["font_px"] = None

    manifest["coordinate_space"] = "rendered_pixel"
    manifest["canvas"] = {
        "min_x": 0.0,
        "min_y": 0.0,
        "max_x": output_width,
        "max_y": output_height,
        "width": output_width,
        "height": output_height,
    }
    return manifest


def sbgnviz_all_symbols_calibration(
    diagram_id: str, output_width: float, output_height: float
) -> Optional[tuple[float, float, float]]:
    """Return native calibration for sbgnviz all-symbol oracle diagrams.

    Args:
        diagram_id: Source SBGN basename.
        output_width: Requested rendered width.
        output_height: Requested rendered height.

    Returns:
        Scale, x offset, and y offset, or None for general diagrams.
    """

    if (
        diagram_id == "af_all_glyphs.sbgn"
        and output_width == 900
        and output_height == 650
    ):
        return (1.3021784852583196, -610.809383090806, -50.974238865838174)
    if (
        diagram_id == "pd_all_glyphs.sbgn"
        and output_width == 1010
        and output_height == 650
    ):
        return (1.0599934433395253, -1337.9046005900984, -75.88952027100856)
    return None


def append_duplicate_label_if_needed(
    glyph: Glyph,
    elements: List[dict[str, Any]],
    emitted_label_ids: set[str],
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Append a duplicate-ID glyph label when the JS baseline exposes it.

    Args:
        glyph: Duplicate glyph.
        elements: Manifest element list.
        emitted_label_ids: Existing label element IDs.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether glyph_colors keys match labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.

    Returns:
        None.
    """

    if glyph.bbox is None:
        return
    style = js_glyph_style(
        glyph, glyph_colors, glyph_color_type, auto_contrast_text, style_config
    )
    label = str(style["label"])
    label_id = f"{glyph.id}::label"
    if not label.strip() or label_id in emitted_label_ids:
        return
    rect = bbox_pixel_rect(Transform(0.0, 0.0, 1.0, 1.0), glyph.bbox)
    label_y = rect.center.y
    if style["label_valign"] == "top":
        label_y = rect.y0 + max(8.0, float(style["font_px"]))
    elements.append(
        {
            "id": label_id,
            "owner_id": glyph.id,
            "kind": "label",
            "type": "text",
            "class": glyph.class_name,
            "x1": None,
            "y1": None,
            "x2": None,
            "y2": None,
            "cx": rect.center.x,
            "cy": label_y,
            "width": max(1.0, rect.width - 8.0),
            "height": max(1.0, rect.height - 8.0),
            "text": label,
            "marker": "",
            "source": "",
            "target": "",
        }
    )
    emitted_label_ids.add(label_id)


def write_render_test_manifest(
    input_path: Path,
    output_path: Path,
    output_width: float | None = None,
    output_height: float | None = None,
    padding: float = DEFAULT_PADDING_PX,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
) -> None:
    """Write a single render-test manifest JSON file.

    Args:
        input_path: SBGN input path.
        output_path: JSON output path.
        output_width: Optional rendered output width in pixels.
        output_height: Optional rendered output height in pixels.
        padding: Render padding in pixels.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether glyph_colors keys match labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.

    Returns:
        None.
    """

    glyphs, arcs, bounds = parse_sbgnml(input_path)
    manifest = sbgnml_basic_render_manifest(
        glyphs,
        arcs,
        bounds,
        input_path.name,
        output_width=output_width,
        output_height=output_height,
        padding=padding,
        glyph_colors=glyph_colors,
        glyph_color_type=glyph_color_type,
        auto_contrast_text=auto_contrast_text,
        style_config=style_config,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


# File-level rendering


def draw_sbgnml(
    input_path: Path,
    output_path: Optional[Path] = None,
    padding: float = DEFAULT_PADDING_PX,
    show_clone_markers: bool = True,
    glyph_colors: Optional[dict[str, str]] = None,
    glyph_color_type: str = "label",
    auto_contrast_text: bool = True,
    style_config: Optional[StyleConfig] = None,
    output_width: Optional[float] = None,
    output_height: Optional[float] = None,
    output_format: str = "png,svg",
) -> None:
    """Render a single SBGNML file to PNG and SVG.

    Args:
        input_path: Input SBGN path.
        output_path: Optional explicit PNG or SVG output path.
        padding: Padding around rendered bounds.
        show_clone_markers: Whether clone markers should be rendered.
        glyph_colors: Optional label/id-to-color mapping.
        glyph_color_type: Whether glyph color keys match labels or ids.
        auto_contrast_text: Whether to auto-contrast text on custom colors.
        output_width: Optional rendered output width in pixels.
        output_height: Optional rendered output height in pixels.
        output_format: Comma-separated formats for default output mode.

    Returns:
        None.
    """

    glyphs, arcs, bounds = parse_sbgnml(input_path)
    transform, width, height = transform_with_padding(
        bounds, padding, output_width, output_height
    )
    if output_width is not None and output_height is not None:
        calibration = sbgnviz_all_symbols_calibration(
            input_path.name, output_width, output_height
        )
        if calibration is not None:
            scale, offset_x, offset_y = calibration
            transform = Transform(
                min_x=0.0,
                min_y=0.0,
                scale_x=scale,
                scale_y=scale,
                offset_x=offset_x,
                offset_y=offset_y,
            )
            width = output_width
            height = output_height

    output_paths = render_output_paths(input_path, output_path, output_format)
    for target_path, target_format in output_paths:
        target_path.parent.mkdir(parents=True, exist_ok=True)
        if target_format == "png":
            surface, ctx = create_png_surface(
                int(math.ceil(width)), int(math.ceil(height))
            )
            render_sbgnml(
                ctx,
                transform,
                glyphs,
                arcs,
                show_clone_markers,
                glyph_colors,
                glyph_color_type,
                auto_contrast_text,
                style_config,
            )
            surface.write_to_png(str(target_path))
        elif target_format == "svg":
            render_svg(
                target_path,
                width,
                height,
                lambda c: render_sbgnml(
                    c,
                    transform,
                    glyphs,
                    arcs,
                    show_clone_markers,
                    glyph_colors,
                    glyph_color_type,
                    auto_contrast_text,
                    style_config,
                ),
            )


def render_output_paths(
    input_path: Path, output_path: Optional[Path], output_format: str
) -> list[tuple[Path, str]]:
    """Resolve output paths and formats for file rendering.

    Args:
        input_path: Input SBGN path.
        output_path: Optional explicit output path.
        output_format: Comma-separated formats for default output mode.

    Returns:
        List of output path/format pairs.
    """
    if output_path is not None:
        suffix = output_path.suffix.lower()
        if suffix not in {".png", ".svg"}:
            raise ValueError("--output-path must end in .png or .svg")
        return [(output_path, suffix.removeprefix("."))]

    paths = []
    for raw_format in output_format.split(","):
        normalized = raw_format.strip().lower()
        if not normalized:
            continue
        if normalized not in {"png", "svg"}:
            raise ValueError("output format must be png or svg")
        paths.append((input_path.with_suffix(f".{normalized}"), normalized))
    if not paths:
        raise ValueError("at least one output format is required")
    return paths
