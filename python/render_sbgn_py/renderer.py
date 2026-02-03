"""SBGNML renderer using pycairo.

This module mirrors the rendering logic from the Rust implementation while
keeping dependencies limited to pycairo and the Python standard library.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple
import math
import xml.etree.ElementTree as ET

import cairo

# Configuration constants
DEFAULT_PADDING_PX = 10.0
DEFAULT_LINE_WIDTH = 1.5
FONT_MAIN_PX = 20.0
FONT_SMALL_PX = 12.0
FONT_FAMILY = "Liberation Sans"
TEXT_OUTLINE_WIDTH = 0.75
ARROW_SIZE = 8.0
ARROW_SCALE = 1.75
BAR_LENGTH = 12.0
BAR_OFFSET = 14.0
CATALYSIS_OVERLAP_RATIO = 0.5
PORT_CONNECTOR_LEN_PX = 12.0
LOGICAL_PORT_CONNECTOR_LEN_PX = 20.0
SHOW_PROCESS_DEBUG = False
SHOW_LOGICAL_DEBUG_BBOX = False

BORDER_COLOR = (0x55 / 255.0, 0x55 / 255.0, 0x55 / 255.0)
DEFAULT_FILL_COLOR = (0xF6 / 255.0, 0xF6 / 255.0, 0xF6 / 255.0)
AUX_LINE_COLOR = (0x6A / 255.0, 0x6A / 255.0, 0x6A / 255.0)
ASSOCIATION_FILL_COLOR = (0x6B / 255.0, 0x6B / 255.0, 0x6B / 255.0)
CLONE_MARKER_HEIGHT_RATIO = 0.30
CLONE_MARKER_FILL_COLOR = (0.82, 0.82, 0.82)
CLONE_MARKER_STROKE_WIDTH = 1.5


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


@dataclass
class Glyph:
    """Parsed glyph from SBGNML."""

    id: str
    parent_id: Optional[str]
    class_name: str
    bbox: Optional[BBox]
    label: str
    ports: List[Point]
    has_clone: bool
    state_value: Optional[str]
    state_variable: Optional[str]
    orientation: Optional[str]


@dataclass
class Arc:
    """Parsed arc with ordered points."""

    class_name: str
    points: List[Point]


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

    def map_point(self, x: float, y: float) -> Point:
        """Map a data point into pixel coordinates."""

        return Point((x - self.min_x) * self.scale_x, (y - self.min_y) * self.scale_y)

    def map_size(self, w: float, h: float) -> Tuple[float, float]:
        """Map data-space width/height into pixel units."""

        return w * self.scale_x, h * self.scale_y

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

    ports: List[Point] = []
    for child in glyph:
        if strip_tag(child.tag) == "port":
            x = parse_float(child.get("x"))
            y = parse_float(child.get("y"))
            if x is not None and y is not None:
                ports.append(Point(x, y))

    has_clone = any(strip_tag(child.tag) == "clone" for child in glyph)

    state_value = None
    state_variable = None
    for child in glyph:
        if strip_tag(child.tag) == "state":
            state_value = child.get("value")
            state_variable = child.get("variable")
            break

    orientation = glyph.get("orientation")

    glyphs.append(
        Glyph(
            id=glyph_id,
            parent_id=parent_id,
            class_name=class_name,
            bbox=bbox,
            label=label_text,
            ports=ports,
            has_clone=has_clone,
            state_value=state_value,
            state_variable=state_variable,
            orientation=orientation,
        )
    )

    for child in glyph:
        if strip_tag(child.tag) == "glyph":
            parse_glyph_node(child, glyph_id, glyphs)


def parse_sbgnml(path: Path) -> Tuple[List[Glyph], List[Arc], Bounds]:
    """Parse an SBGNML file into glyphs, arcs, and bounds."""

    tree = ET.parse(path)
    root = tree.getroot()

    map_node = None
    for node in root.iter():
        if strip_tag(node.tag) == "map":
            map_node = node
            break
    if map_node is None:
        raise ValueError("SBGN file missing map element")

    glyphs: List[Glyph] = []
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
        arcs.append(Arc(class_name=class_name, points=points))

    bounds = compute_bounds(glyphs)
    return glyphs, arcs, bounds


# Geometry helpers

def compute_bounds(glyphs: Sequence[Glyph]) -> Bounds:
    """Compute overall bounds from glyph bboxes and ports."""

    x_values: List[float] = []
    y_values: List[float] = []

    for glyph in glyphs:
        if glyph.bbox is not None:
            x_values.extend([glyph.bbox.x, glyph.bbox.x + glyph.bbox.w])
            y_values.extend([glyph.bbox.y, glyph.bbox.y + glyph.bbox.h])
        for port in glyph.ports:
            x_values.append(port.x)
            y_values.append(port.y)

    if not x_values or not y_values:
        raise ValueError("No coordinates found in SBGN file")

    return Bounds(
        min_x=min(x_values),
        max_x=max(x_values),
        min_y=min(y_values),
        max_y=max(y_values),
    )


def transform_with_padding(bounds: Bounds, padding: float) -> Tuple[Transform, float, float]:
    """Build a transform and image size from data bounds."""

    min_x = bounds.min_x - padding
    max_x = bounds.max_x + padding
    min_y = bounds.min_y - padding
    max_y = bounds.max_y + padding

    width = max(abs(max_x - min_x), 1.0)
    height = max(abs(max_y - min_y), 1.0)

    transform = Transform(
        min_x=min_x,
        min_y=min_y,
        scale_x=width / max(abs(max_x - min_x), 1.0),
        scale_y=height / max(abs(max_y - min_y), 1.0),
    )

    return transform, width, height


def bbox_pixel_rect(transform: Transform, bbox: BBox) -> PixelRect:
    """Convert a data-space bbox into pixel-space rectangle."""

    x0 = (bbox.x - transform.min_x) * transform.scale_x
    x1 = (bbox.x + bbox.w - transform.min_x) * transform.scale_x
    y0 = (bbox.y - transform.min_y) * transform.scale_y
    y1 = (bbox.y + bbox.h - transform.min_y) * transform.scale_y

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


def state_var_label(value: Optional[str], variable: Optional[str]) -> str:
    """Build a state variable label like value@variable."""

    value = value or ""
    variable = variable or ""
    if value and variable:
        return f"{value}@{variable}"
    if value:
        return value
    if variable:
        return variable
    return ""


def glyph_font_px(class_name: str) -> float:
    """Map glyph class name to font size."""

    if class_name in {
        "state variable",
        "unit of information",
        "cardinality",
        "variable value",
        "tag",
        "terminal",
    }:
        return FONT_SMALL_PX
    return FONT_MAIN_PX


def default_dimensions(class_name: str) -> Optional[Tuple[float, float]]:
    """Return default sbgnStyle dimensions for a glyph class."""

    defaults = {
        "unspecified entity": (32.0, 32.0),
        "simple chemical": (48.0, 48.0),
        "simple chemical multimer": (48.0, 48.0),
        "macromolecule": (96.0, 48.0),
        "macromolecule multimer": (96.0, 48.0),
        "nucleic acid feature": (88.0, 56.0),
        "nucleic acid feature multimer": (88.0, 52.0),
        "complex": (10.0, 10.0),
        "complex multimer": (10.0, 10.0),
        "source and sink": (60.0, 60.0),
        "perturbing agent": (140.0, 60.0),
        "phenotype": (140.0, 60.0),
        "process": (25.0, 25.0),
        "uncertain process": (25.0, 25.0),
        "omitted process": (25.0, 25.0),
        "association": (25.0, 25.0),
        "dissociation": (25.0, 25.0),
        "compartment": (50.0, 50.0),
        "tag": (100.0, 65.0),
        "and": (40.0, 40.0),
        "or": (40.0, 40.0),
        "not": (40.0, 40.0),
    }
    return defaults.get(class_name)


def ghost_offset_for(class_name: str) -> Optional[Tuple[float, float]]:
    """Return ghost offsets for multimer glyphs."""

    offsets = {
        "simple chemical": (5.0, 5.0),
        "macromolecule": (12.0, 12.0),
        "nucleic acid feature": (12.0, 12.0),
        "complex": (16.0, 16.0),
    }
    return offsets.get(class_name)


def entity_pool_border_width(class_name: str) -> float:
    """Return border width for entity pool nodes."""

    if class_name == "complex":
        return 4.0
    return 2.0


def port_connector_len_px_for_class(class_name: str) -> float:
    """Return connector length for a given class."""

    if class_name in {"and", "or", "not"}:
        return LOGICAL_PORT_CONNECTOR_LEN_PX
    return PORT_CONNECTOR_LEN_PX


# Cairo helpers

def setup_context(ctx: cairo.Context) -> None:
    """Initialize the Cairo context with defaults."""

    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.paint()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    ctx.set_line_cap(cairo.LineCap.SQUARE)


def create_png_surface(width: int, height: int) -> Tuple[cairo.ImageSurface, cairo.Context]:
    """Create a Cairo image surface and context."""

    surface = cairo.ImageSurface(cairo.Format.ARGB32, width, height)
    ctx = cairo.Context(surface)
    setup_context(ctx)
    return surface, ctx


def default_svg_output_path(output: Path) -> Path:
    """Return a default SVG output path for a PNG path."""

    return output.with_suffix(".svg")


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


def text_metrics(ctx: cairo.Context, text: str, font_px: float) -> Tuple[float, float, float]:
    """Return width, line height, and ascent for a line of text."""

    set_font(ctx, font_px)
    extents = ctx.text_extents(text)
    font_extents = ctx.font_extents()
    line_height = font_extents[2]
    ascent = font_extents[0]
    return extents.width, line_height, ascent


def draw_text_centered(ctx: cairo.Context, center: Point, text: str, font_px: float) -> None:
    """Draw centered text with optional outline."""

    if not text.strip():
        return
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
    for idx, line in enumerate(lines):
        width = widths[idx]
        x = center.x - width / 2.0
        y = y_start + idx * line_height
        ctx.move_to(x, y)
        ctx.text_path(line)
        if TEXT_OUTLINE_WIDTH > 0.0:
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.set_line_width(TEXT_OUTLINE_WIDTH)
            ctx.stroke_preserve()
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.fill()
        ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_text_bottom_centered(ctx: cairo.Context, rect: PixelRect, text: str, font_px: float) -> None:
    """Draw text aligned to the bottom center of a rectangle."""

    if not text.strip():
        return
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
    y_start = rect.y0 + rect.height - total_height + ascent - 2.0
    for idx, line in enumerate(lines):
        width = widths[idx]
        x = rect.center.x - width / 2.0
        y = y_start + idx * line_height
        ctx.move_to(x, y)
        ctx.text_path(line)
        if TEXT_OUTLINE_WIDTH > 0.0:
            ctx.set_source_rgb(1.0, 1.0, 1.0)
            ctx.set_line_width(TEXT_OUTLINE_WIDTH)
            ctx.stroke_preserve()
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.fill()
        ctx.set_line_width(DEFAULT_LINE_WIDTH)


def measure_text_width(ctx: cairo.Context, text: str, font_px: float) -> float:
    """Measure text width using Cairo."""

    set_font(ctx, font_px)
    extents = ctx.text_extents(text)
    return extents.width


# Shape primitives

def draw_shape_with_clone(
    ctx: cairo.Context,
    rect: PixelRect,
    label: str,
    font_px: float,
    has_clone: bool,
    line_width: float,
    fill_color: Optional[Tuple[float, float, float]],
    path_fn,
) -> None:
    """Draw a shape with optional clone marker and centered label."""

    ctx.set_line_width(max(line_width, 0.5))
    path_fn(ctx, rect)
    if fill_color is not None:
        ctx.set_source_rgb(*fill_color)
        ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()

    if has_clone:
        draw_clone_marker(ctx, rect, path_fn)
        path_fn(ctx, rect)
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.stroke()

    draw_text_centered(ctx, rect.center, label, font_px)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_clone_marker(ctx: cairo.Context, rect: PixelRect, path_fn) -> None:
    """Draw a clone marker overlay using clipping."""

    marker_height = max(rect.height * CLONE_MARKER_HEIGHT_RATIO, 1.0)
    marker_width = rect.width
    marker_x = rect.center.x - marker_width / 2.0
    marker_y = rect.y0 + rect.height - marker_height

    ctx.save()
    path_fn(ctx, rect)
    ctx.clip()
    ctx.new_path()
    ctx.rectangle(marker_x, marker_y, marker_width, marker_height)
    ctx.set_source_rgb(*CLONE_MARKER_FILL_COLOR)
    ctx.fill_preserve()
    ctx.set_source_rgb(*AUX_LINE_COLOR)
    ctx.set_line_width(max(CLONE_MARKER_STROKE_WIDTH, 1.0))
    ctx.stroke()
    ctx.restore()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


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


def path_cut_rect(ctx: cairo.Context, rect: PixelRect, corner: float) -> None:
    """Add a chamfered rectangle path."""

    x0 = rect.x0
    y0 = rect.y0
    x1 = rect.x0 + rect.width
    y1 = rect.y0 + rect.height
    ctx.new_path()
    ctx.move_to(x0, y0 + corner)
    ctx.line_to(x0 + corner, y0)
    ctx.line_to(x1 - corner, y0)
    ctx.line_to(x1, y0 + corner)
    ctx.line_to(x1, y1 - corner)
    ctx.line_to(x1 - corner, y1)
    ctx.line_to(x0 + corner, y1)
    ctx.line_to(x0, y1 - corner)
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


def path_concave_hexagon(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add a concave hexagon path."""

    x0 = rect.x0
    y0 = rect.y0
    w = rect.width
    h = rect.height
    points = [
        Point(x0, y0),
        Point(x0 + w, y0),
        Point(x0 + 0.85 * w, y0 + 0.5 * h),
        Point(x0 + w, y0 + h),
        Point(x0, y0 + h),
        Point(x0 + 0.15 * w, y0 + 0.5 * h),
    ]
    ctx.new_path()
    ctx.move_to(points[0].x, points[0].y)
    for point in points[1:]:
        ctx.line_to(point.x, point.y)
    ctx.close_path()


def path_barrel(ctx: cairo.Context, rect: PixelRect) -> None:
    """Add a barrel path."""

    x = rect.x0
    y = rect.y0
    w = rect.width
    h = rect.height
    top_y = y + 0.03 * h
    bottom_y = y + 0.97 * h

    ctx.new_path()
    ctx.move_to(x, top_y)
    ctx.line_to(x, bottom_y)
    quad_curve_to(ctx, x + 0.06 * w, y + h, x + 0.25 * w, y + h)
    ctx.line_to(x + 0.75 * w, y + h)
    quad_curve_to(ctx, x + 0.95 * w, y + h, x + w, y + 0.95 * h)
    ctx.line_to(x + w, y + 0.05 * h)
    quad_curve_to(ctx, x + w, y, x + 0.75 * w, y)
    ctx.line_to(x + 0.25 * w, y)
    quad_curve_to(ctx, x + 0.06 * w, y, x, top_y)
    ctx.close_path()


def path_tag(ctx: cairo.Context, rect: PixelRect, notch: float) -> None:
    """Add a tag path."""

    x0 = rect.x0
    y0 = rect.y0
    x1 = rect.x0 + rect.width
    y1 = rect.y0 + rect.height
    mid_y = (y0 + y1) / 2.0
    ctx.new_path()
    ctx.move_to(x0 + notch, y0)
    ctx.line_to(x1, y0)
    ctx.line_to(x1, y1)
    ctx.line_to(x0 + notch, y1)
    ctx.line_to(x0, mid_y)
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


def path_round_bottom_rect_impl(
    ctx: cairo.Context, x: float, y: float, width: float, height: float, radius: float
) -> None:
    """Add a rectangle with rounded bottom corners."""

    radius = min(radius, width / 2.0, height / 2.0)
    right = x + width
    bottom = y + height

    ctx.new_path()
    ctx.move_to(x, y)
    ctx.line_to(right, y)
    ctx.line_to(right, bottom - radius)
    ctx.arc(right - radius, bottom - radius, radius, 0.0, math.pi / 2.0)
    ctx.line_to(x + radius, bottom)
    ctx.arc(x + radius, bottom - radius, radius, math.pi / 2.0, math.pi)
    ctx.close_path()


def quad_curve_to(ctx: cairo.Context, cx: float, cy: float, x: float, y: float) -> None:
    """Draw a quadratic curve using Cairo's cubic Bezier."""

    x0, y0 = ctx.get_current_point()
    c1x = x0 + 2.0 / 3.0 * (cx - x0)
    c1y = y0 + 2.0 / 3.0 * (cy - y0)
    c2x = x + 2.0 / 3.0 * (cx - x)
    c2y = y + 2.0 / 3.0 * (cy - y)
    ctx.curve_to(c1x, c1y, c2x, c2y, x, y)


# Drawing primitives

def draw_orientation_marker(
    ctx: cairo.Context,
    rect: PixelRect,
    orientation: str,
    connector_len_px: float,
) -> None:
    """Draw orientation markers around a glyph."""

    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    if orientation == "vertical":
        ctx.new_path()
        ctx.move_to(rect.center.x, rect.y0 - connector_len_px)
        ctx.line_to(rect.center.x, rect.y0)
        ctx.move_to(rect.center.x, rect.y0 + rect.height)
        ctx.line_to(rect.center.x, rect.y0 + rect.height + connector_len_px)
        ctx.stroke()
    elif orientation == "horizontal":
        ctx.new_path()
        ctx.move_to(rect.x0 - connector_len_px, rect.center.y)
        ctx.line_to(rect.x0, rect.center.y)
        ctx.move_to(rect.x0 + rect.width, rect.center.y)
        ctx.line_to(rect.x0 + rect.width + connector_len_px, rect.center.y)
        ctx.stroke()
    elif orientation == "left":
        ctx.new_path()
        ctx.move_to(rect.x0 - connector_len_px, rect.center.y)
        ctx.line_to(rect.x0, rect.center.y)
        ctx.stroke()
    elif orientation == "right":
        ctx.new_path()
        ctx.move_to(rect.x0 + rect.width, rect.center.y)
        ctx.line_to(rect.x0 + rect.width + connector_len_px, rect.center.y)
        ctx.stroke()
    elif orientation == "up":
        ctx.new_path()
        ctx.move_to(rect.center.x, rect.y0 - connector_len_px)
        ctx.line_to(rect.center.x, rect.y0)
        ctx.stroke()
    elif orientation == "down":
        ctx.new_path()
        ctx.move_to(rect.center.x, rect.y0 + rect.height)
        ctx.line_to(rect.center.x, rect.y0 + rect.height + connector_len_px)
        ctx.stroke()


def draw_overlay_line(
    ctx: cairo.Context, rect: PixelRect, y: float, line_width: float, color: Tuple[float, float, float]
) -> None:
    """Draw a horizontal overlay line across a glyph."""

    ctx.set_line_width(max(line_width, 1.0))
    ctx.set_source_rgb(*color)
    ctx.new_path()
    ctx.move_to(rect.x0, y)
    ctx.line_to(rect.x0 + rect.width, y)
    ctx.stroke()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_unit_info(
    ctx: cairo.Context,
    x: float,
    y: float,
    height: float,
    label: str,
    border_width: float,
    font_px: float,
    padding_px: float,
) -> None:
    """Draw a unit-of-information box sized from its label."""

    text_width = measure_text_width(ctx, label, font_px)
    width = max(text_width + padding_px, 10.0)
    rect = PixelRect(
        x0=x,
        y0=y,
        width=width,
        height=height,
        center=Point(x + width / 2.0, y + height / 2.0),
    )
    ctx.set_line_width(max(border_width, 1.0))
    path_round_rect_impl(ctx, rect.x0, rect.y0, rect.width, rect.height, rect.width * 0.04)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()
    draw_text_centered(ctx, rect.center, label, font_px)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def draw_state_var(
    ctx: cairo.Context,
    x: float,
    y: float,
    height: float,
    label: str,
    border_width: float,
    font_px: float,
    padding_px: float,
    min_width: float,
) -> None:
    """Draw a state variable box sized from its label."""

    text_width = measure_text_width(ctx, label, font_px)
    width = max(text_width + padding_px, min_width)
    rect = PixelRect(
        x0=x,
        y0=y,
        width=width,
        height=height,
        center=Point(x + width / 2.0, y + height / 2.0),
    )
    ctx.set_line_width(max(border_width, 1.0))
    radius = 0.24 * max(rect.width, rect.height)
    path_round_rect_impl(ctx, rect.x0, rect.y0, rect.width, rect.height, radius)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()
    draw_text_centered(ctx, rect.center, label, font_px)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)


def px_x(rect: PixelRect, value: float, scale_x: float) -> float:
    """Convert x offset in px units to node space."""

    return rect.x0 + value * scale_x


def px_y(rect: PixelRect, value: float, scale_y: float) -> float:
    """Convert y offset in px units to node space."""

    return rect.y0 + value * scale_y


def draw_entity_pool_node(
    ctx: cairo.Context,
    rect: PixelRect,
    class_name: str,
    label: str,
    font_px: float,
    is_multimer: bool,
    has_clone: bool,
    u_info_label: Optional[str],
    s_var_label: Optional[str],
) -> None:
    """Draw an entity pool node with overlays."""

    ref_dims = default_dimensions(class_name) or (rect.width, rect.height)
    scale_x = rect.width / ref_dims[0]
    scale_y = rect.height / ref_dims[1]

    if is_multimer:
        offset = ghost_offset_for(class_name)
        if offset:
            ghost_rect = PixelRect(
                x0=rect.x0 + offset[0] * scale_x,
                y0=rect.y0 + offset[1] * scale_y,
                width=rect.width,
                height=rect.height,
                center=Point(
                    rect.center.x + offset[0] * scale_x,
                    rect.center.y + offset[1] * scale_y,
                ),
            )
            draw_entity_pool_base_shape(
                ctx,
                ghost_rect,
                class_name,
                "",
                FONT_SMALL_PX,
                False,
                DEFAULT_FILL_COLOR,
                entity_pool_border_width(class_name),
            )

    draw_entity_pool_base_shape(
        ctx,
        rect,
        class_name,
        label,
        font_px,
        has_clone,
        DEFAULT_FILL_COLOR,
        entity_pool_border_width(class_name),
    )

    draw_entity_pool_aux_items(ctx, rect, class_name, u_info_label, s_var_label)


def draw_entity_pool_base_shape(
    ctx: cairo.Context,
    rect: PixelRect,
    class_name: str,
    label: str,
    font_px: float,
    has_clone: bool,
    fill_color: Tuple[float, float, float],
    border_width: float,
) -> None:
    """Draw the base entity pool glyph shape."""

    if class_name in {"simple chemical", "unspecified entity"}:
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            path_ellipse,
        )
    elif class_name == "macromolecule":
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            lambda ctx, rect: path_round_rect(ctx, rect, max(min(rect.width, rect.height) * 0.1, 1.0)),
        )
    elif class_name == "nucleic acid feature":
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            lambda ctx, rect: path_round_bottom_rect_impl(
                ctx, rect.x0, rect.y0, rect.width, rect.height, max(rect.height * 0.3, 1.0)
            ),
        )
    elif class_name == "complex":
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            lambda ctx, rect: path_cut_rect(ctx, rect, max(min(rect.width, rect.height) * 0.2, 1.0)),
        )
    elif class_name == "perturbing agent":
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            path_concave_hexagon,
        )
    else:
        draw_shape_with_clone(
            ctx,
            rect,
            label,
            font_px,
            has_clone,
            border_width,
            fill_color,
            path_rect,
        )


def draw_entity_pool_aux_items(
    ctx: cairo.Context,
    rect: PixelRect,
    class_name: str,
    u_info_label: Optional[str],
    s_var_label: Optional[str],
) -> None:
    """Draw auxiliary overlays for entity pool nodes."""

    ref_dims = default_dimensions(class_name) or (rect.width, rect.height)
    scale_x = rect.width / ref_dims[0]
    scale_y = rect.height / ref_dims[1]
    scale = (scale_x + scale_y) / 2.0

    aux_item_height = 20.0 * scale_y
    border_width = 2.0 * scale
    font_px = 10.0 * scale
    clone_shrink_y = 3.0 * scale_y
    u_info_height = aux_item_height - clone_shrink_y

    if class_name == "simple chemical":
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 8.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 52.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                px_x(rect, 12.0, scale_x),
                px_y(rect, 0.0, scale_y),
                u_info_height,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )
    elif class_name == "unspecified entity":
        if u_info_label or s_var_label:
            draw_overlay_line(ctx, rect, px_y(rect, 8.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 52.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                px_x(rect, 20.0, scale_x),
                px_y(rect, 44.0, scale_y),
                u_info_height,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )
        if s_var_label:
            draw_state_var(
                ctx,
                px_x(rect, 40.0, scale_x),
                rect.y0,
                u_info_height,
                s_var_label,
                border_width,
                font_px,
                10.0 * scale,
                30.0 * scale,
            )
    elif class_name == "macromolecule":
        if u_info_label or s_var_label:
            draw_overlay_line(ctx, rect, px_y(rect, 8.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 52.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                px_x(rect, 20.0, scale_x),
                px_y(rect, 44.0, scale_y),
                u_info_height,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )
        if s_var_label:
            draw_state_var(
                ctx,
                px_x(rect, 40.0, scale_x),
                rect.y0,
                u_info_height,
                s_var_label,
                border_width,
                font_px,
                10.0 * scale,
                30.0 * scale,
            )
    elif class_name == "nucleic acid feature":
        if s_var_label:
            draw_overlay_line(ctx, rect, px_y(rect, 8.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 52.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                px_x(rect, 20.0, scale_x),
                px_y(rect, 44.0, scale_y),
                u_info_height,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )
        if s_var_label:
            draw_state_var(
                ctx,
                px_x(rect, 40.0, scale_x),
                rect.y0,
                u_info_height,
                s_var_label,
                border_width,
                font_px,
                10.0 * scale,
                30.0 * scale,
            )
    elif class_name == "complex":
        if u_info_label or s_var_label:
            draw_overlay_line(ctx, rect, px_y(rect, 11.0, scale_y), 6.0 * scale, BORDER_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                rect.x0 + rect.width * 0.25,
                rect.y0,
                24.0 * scale_y - clone_shrink_y,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )
        if s_var_label:
            draw_state_var(
                ctx,
                rect.x0 + rect.width * 0.88,
                rect.y0,
                24.0 * scale_y - clone_shrink_y,
                s_var_label,
                border_width,
                font_px,
                10.0 * scale,
                30.0 * scale,
            )
    elif class_name == "perturbing agent":
        if u_info_label:
            draw_overlay_line(ctx, rect, px_y(rect, 8.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label is not None:
            draw_overlay_line(ctx, rect, px_y(rect, 56.0, scale_y), 1.0 * scale, AUX_LINE_COLOR)
        if u_info_label:
            draw_unit_info(
                ctx,
                px_x(rect, 20.0, scale_x),
                rect.y0,
                u_info_height,
                u_info_label,
                border_width,
                font_px,
                5.0 * scale,
            )


def draw_source_sink(ctx: cairo.Context, rect: PixelRect, has_clone: bool) -> None:
    """Draw a source/sink glyph with a diagonal slash."""

    path_ellipse(ctx, rect)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    ctx.set_source_rgb(*DEFAULT_FILL_COLOR)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()
    if has_clone:
        draw_clone_marker(ctx, rect, path_ellipse)
        path_ellipse(ctx, rect)
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.stroke()
    ctx.new_path()
    ctx.move_to(rect.x0, rect.y0 + rect.height)
    ctx.line_to(rect.x0 + rect.width, rect.y0)
    ctx.stroke()


def draw_double_circle(ctx: cairo.Context, rect: PixelRect, label: str, font_px: float) -> None:
    """Draw a dissociation glyph with two concentric circles."""

    radius = max(min(rect.width, rect.height) / 2.0, 1.0)
    ctx.new_path()
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    ctx.arc(rect.center.x, rect.center.y, radius, 0.0, math.tau)
    ctx.set_source_rgb(*DEFAULT_FILL_COLOR)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()
    ctx.new_path()
    ctx.arc(rect.center.x, rect.center.y, max(radius * 0.6, 1.0), 0.0, math.tau)
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()
    draw_text_centered(ctx, rect.center, label, font_px)


def draw_square_bbox(
    ctx: cairo.Context,
    bbox: BBox,
    transform: Transform,
    label: str,
    font_px: float,
) -> PixelRect:
    """Draw a square process glyph."""

    center = transform.map_point(bbox.x + bbox.w / 2.0, bbox.y + bbox.h / 2.0)
    side = min(bbox.w, bbox.h)
    side_px, _ = transform.map_size(side, side)
    rect = PixelRect(
        x0=center.x - side_px / 2.0,
        y0=center.y - side_px / 2.0,
        width=side_px,
        height=side_px,
        center=center,
    )
    draw_shape_with_clone(
        ctx,
        rect,
        label,
        font_px,
        False,
        DEFAULT_LINE_WIDTH,
        DEFAULT_FILL_COLOR,
        path_rect,
    )
    return rect


def draw_hexagon_bbox(
    ctx: cairo.Context,
    rect: PixelRect,
    label: str,
    font_px: float,
    has_clone: bool,
) -> None:
    """Draw a hexagon glyph."""

    draw_shape_with_clone(
        ctx,
        rect,
        label,
        font_px,
        has_clone,
        DEFAULT_LINE_WIDTH,
        DEFAULT_FILL_COLOR,
        path_hexagon,
    )


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


def diamond_points(end: Point, prev: Point, size: float) -> Optional[List[Point]]:
    """Compute diamond points for modulation arrowheads."""

    dx = end.x - prev.x
    dy = end.y - prev.y
    length = math.hypot(dx, dy)
    if length == 0:
        return None
    ux = dx / length
    uy = dy / length
    center = Point(end.x - ux * size * 0.5, end.y - uy * size * 0.5)
    base = Point(end.x - ux * size, end.y - uy * size)
    perp_x = -uy
    perp_y = ux
    half_width = size * 0.6
    p1 = Point(center.x + perp_x * half_width, center.y + perp_y * half_width)
    p2 = Point(center.x - perp_x * half_width, center.y - perp_y * half_width)
    return [end, p1, base, p2]


def draw_open_triangle(ctx: cairo.Context, end: Point, prev: Point, size: float) -> None:
    """Draw an open triangle arrowhead."""

    pts = triangle_points(end, prev, size)
    if not pts:
        return
    ctx.move_to(pts[0].x, pts[0].y)
    ctx.line_to(pts[2].x, pts[2].y)
    ctx.line_to(pts[1].x, pts[1].y)
    ctx.close_path()
    ctx.stroke()


def draw_open_triangle_opaque(ctx: cairo.Context, end: Point, prev: Point, size: float) -> None:
    """Draw an open triangle arrowhead filled with white."""

    pts = triangle_points(end, prev, size)
    if not pts:
        return
    ctx.move_to(pts[0].x, pts[0].y)
    ctx.line_to(pts[2].x, pts[2].y)
    ctx.line_to(pts[1].x, pts[1].y)
    ctx.close_path()
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()


def draw_filled_triangle(ctx: cairo.Context, end: Point, prev: Point, size: float) -> None:
    """Draw a filled triangle arrowhead."""

    pts = triangle_points(end, prev, size)
    if not pts:
        return
    ctx.move_to(pts[0].x, pts[0].y)
    ctx.line_to(pts[2].x, pts[2].y)
    ctx.line_to(pts[1].x, pts[1].y)
    ctx.close_path()
    ctx.fill()


def draw_open_diamond_opaque(ctx: cairo.Context, end: Point, prev: Point, size: float) -> None:
    """Draw an open diamond arrowhead filled with white."""

    pts = diamond_points(end, prev, size)
    if not pts:
        return
    ctx.move_to(pts[0].x, pts[0].y)
    ctx.line_to(pts[1].x, pts[1].y)
    ctx.line_to(pts[2].x, pts[2].y)
    ctx.line_to(pts[3].x, pts[3].y)
    ctx.close_path()
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()


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


def draw_open_circle(ctx: cairo.Context, center: Point, radius: float) -> None:
    """Draw an open circle marker."""

    ctx.arc(center.x, center.y, max(radius, 1.0), 0.0, math.tau)
    ctx.stroke()


def draw_filled_circle(ctx: cairo.Context, center: Point, radius: float) -> None:
    """Draw a filled circle with border."""

    ctx.arc(center.x, center.y, max(radius, 1.0), 0.0, math.tau)
    ctx.set_source_rgb(1.0, 1.0, 1.0)
    ctx.fill_preserve()
    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.stroke()


def draw_filled_circle_tangent(ctx: cairo.Context, end: Point, prev: Point, radius: float) -> None:
    """Draw a filled circle tangent to an arc end."""

    dx = end.x - prev.x
    dy = end.y - prev.y
    length = math.hypot(dx, dy)
    if length == 0:
        draw_filled_circle(ctx, end, radius)
        return
    ux = dx / length
    uy = dy / length
    overlap = radius * CATALYSIS_OVERLAP_RATIO
    offset = max(radius - overlap, 0.0)
    center = Point(end.x - ux * offset, end.y - uy * offset)
    draw_filled_circle(ctx, center, radius)


def draw_arc(
    ctx: cairo.Context,
    points: Sequence[Point],
    class_name: str,
    arrow_size: float,
    bar_length: float,
    bar_offset: float,
) -> None:
    """Draw an arc line and its terminator."""

    if len(points) < 2:
        return

    ctx.set_source_rgb(*BORDER_COLOR)
    ctx.set_line_width(DEFAULT_LINE_WIDTH)
    for p0, p1 in zip(points, points[1:]):
        ctx.move_to(p0.x, p0.y)
        ctx.line_to(p1.x, p1.y)
        ctx.stroke()

    end = points[-1]
    prev = points[-2]

    if class_name in {"assignment", "unknown influence"}:
        draw_open_triangle(ctx, end, prev, arrow_size)
    elif class_name in {"positive influence", "stimulation"}:
        draw_open_triangle_opaque(ctx, end, prev, arrow_size)
    elif class_name == "modulation":
        draw_open_diamond_opaque(ctx, end, prev, arrow_size)
    elif class_name == "production":
        draw_filled_triangle(ctx, end, prev, arrow_size)
    elif class_name in {"negative influence", "inhibition"}:
        draw_inhibition_bar(ctx, end, prev, bar_length, 0.0)
    elif class_name == "absolute inhibition":
        draw_inhibition_bar(ctx, end, prev, bar_length, 0.0)
        draw_inhibition_bar(ctx, end, prev, bar_length, bar_offset)
    elif class_name == "necessary stimulation":
        draw_inhibition_bar(ctx, end, prev, bar_length, bar_offset)
        draw_open_triangle_opaque(ctx, end, prev, arrow_size)
    elif class_name == "catalysis":
        draw_filled_circle_tangent(ctx, end, prev, arrow_size * 0.4)
    elif class_name == "equivalence arc":
        draw_open_circle(ctx, end, arrow_size * 0.4)


# Main rendering entry points

def render_sbgnml_to_image(
    glyphs: Sequence[Glyph],
    arcs: Sequence[Arc],
    bounds: Bounds,
    padding: float,
    show_clone_markers: bool,
) -> cairo.ImageSurface:
    """Render parsed glyphs and arcs to a PNG surface."""

    transform, width, height = transform_with_padding(bounds, padding)
    surface, ctx = create_png_surface(int(math.ceil(width)), int(math.ceil(height)))
    render_sbgnml(ctx, transform, glyphs, arcs, show_clone_markers)
    return surface


def render_sbgnml(
    ctx: cairo.Context,
    transform: Transform,
    glyphs: Sequence[Glyph],
    arcs: Sequence[Arc],
    show_clone_markers: bool,
) -> None:
    """Render parsed SBGNML glyphs and arcs using bbox geometry."""

    child_map: Dict[str, List[Glyph]] = {}
    for glyph in glyphs:
        if glyph.parent_id:
            child_map.setdefault(glyph.parent_id, []).append(glyph)

    aux_glyphs = [
        glyph
        for glyph in glyphs
        if glyph.parent_id
        and glyph.class_name in {"unit of information", "state variable"}
    ]

    for glyph in glyphs:
        if glyph.parent_id is None:
            render_glyph_tree(ctx, transform, glyph, child_map, show_clone_markers)

    for glyph in aux_glyphs:
        if glyph.bbox is None:
            continue
        label = glyph.label
        if glyph.class_name == "state variable" and not label.strip():
            label = state_var_label(glyph.state_value, glyph.state_variable)
        font_px = glyph_font_px(glyph.class_name)
        rect = bbox_pixel_rect(transform, glyph.bbox)
        if glyph.class_name == "unit of information":
            draw_shape_with_clone(
                ctx,
                rect,
                label,
                font_px,
                show_clone_markers and glyph.has_clone,
                DEFAULT_LINE_WIDTH,
                DEFAULT_FILL_COLOR,
                lambda ctx, rect: path_round_rect(ctx, rect, max(min(rect.width, rect.height) * 0.1, 1.0)),
            )
        elif glyph.class_name == "state variable":
            draw_shape_with_clone(
                ctx,
                rect,
                label,
                font_px,
                show_clone_markers and glyph.has_clone,
                DEFAULT_LINE_WIDTH,
                DEFAULT_FILL_COLOR,
                lambda ctx, rect: path_round_rect(ctx, rect, 0.24 * max(rect.width, rect.height)),
            )

    arrow_size_px = transform.scale_scalar(ARROW_SIZE * ARROW_SCALE)
    bar_length_px = transform.scale_scalar(BAR_LENGTH * ARROW_SCALE)
    bar_offset_px = transform.scale_scalar(BAR_OFFSET * ARROW_SCALE)

    for arc in arcs:
        points_px = [transform.map_point(pt.x, pt.y) for pt in arc.points]
        draw_arc(ctx, points_px, arc.class_name, arrow_size_px, bar_length_px, bar_offset_px)


def render_glyph_tree(
    ctx: cairo.Context,
    transform: Transform,
    glyph: Glyph,
    child_map: Dict[str, List[Glyph]],
    show_clone_markers: bool,
) -> None:
    """Render a glyph and its children recursively."""

    if glyph.bbox is None:
        return

    class_name = glyph.class_name
    class_base = class_name.replace(" multimer", "")
    is_multimer = class_name.endswith(" multimer")
    label_override = {
        "and": "AND",
        "or": "OR",
        "not": "NOT",
        "omitted process": "\\\\",
        "uncertain process": "?",
    }
    label = label_override.get(class_name, glyph.label)
    if class_name == "state variable" and not label.strip():
        label = state_var_label(glyph.state_value, glyph.state_variable)
    font_px = glyph_font_px(class_name)
    has_clone = show_clone_markers and glyph.has_clone

    children = child_map.get(glyph.id, [])
    has_u_info_bbox = any(child.class_name == "unit of information" and child.bbox for child in children)
    has_s_var_bbox = any(child.class_name == "state variable" and child.bbox for child in children)

    u_info_label = None
    if not has_u_info_bbox:
        for child in children:
            if child.class_name == "unit of information" and child.label.strip():
                u_info_label = child.label
                break

    s_var_label = None
    if not has_s_var_bbox:
        for child in children:
            if child.class_name == "state variable":
                if child.label.strip():
                    s_var_label = child.label
                else:
                    s_var_label = state_var_label(child.state_value, child.state_variable)
                if s_var_label:
                    break

    place_label_bottom = class_base == "complex" or class_name == "compartment"
    shape_label = "" if place_label_bottom else label

    rect = bbox_pixel_rect(transform, glyph.bbox)

    if class_name in {"phenotype", "outcome"}:
        draw_hexagon_bbox(ctx, rect, shape_label, font_px, False)
    elif class_name == "perturbing agent":
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            None,
        )
    elif class_name in {"simple chemical", "simple chemical multimer"}:
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            None,
        )
    elif class_name == "unspecified entity":
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            s_var_label,
        )
    elif class_name in {"macromolecule", "macromolecule multimer"}:
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            s_var_label,
        )
    elif class_name in {"nucleic acid feature", "nucleic acid feature multimer"}:
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            s_var_label,
        )
    elif class_name in {"complex", "complex multimer"}:
        draw_entity_pool_node(
            ctx,
            rect,
            class_base,
            shape_label,
            font_px,
            is_multimer,
            has_clone,
            u_info_label,
            s_var_label,
        )
    elif class_name == "source and sink":
        draw_source_sink(ctx, rect, has_clone)
    elif class_name == "compartment":
        draw_shape_with_clone(
            ctx,
            rect,
            shape_label,
            font_px,
            has_clone,
            4.0,
            DEFAULT_FILL_COLOR,
            path_barrel,
        )
    elif class_name == "tag":
        notch = max(rect.height * 0.3, 2.0)
        draw_shape_with_clone(
            ctx,
            rect,
            shape_label,
            font_px,
            has_clone,
            DEFAULT_LINE_WIDTH,
            DEFAULT_FILL_COLOR,
            lambda ctx, rect: path_tag(ctx, rect, notch),
        )
    elif class_name == "association":
        path_ellipse(ctx, rect)
        ctx.set_line_width(DEFAULT_LINE_WIDTH)
        ctx.set_source_rgb(*ASSOCIATION_FILL_COLOR)
        ctx.fill_preserve()
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.stroke()
        draw_text_centered(ctx, rect.center, shape_label, font_px)
    elif class_name == "dissociation":
        draw_double_circle(ctx, rect, shape_label, font_px)
    elif class_name in {"process", "omitted process", "uncertain process"}:
        draw_square_bbox(ctx, glyph.bbox, transform, shape_label, font_px)
        if SHOW_PROCESS_DEBUG:
            debug_rect = PixelRect(
                x0=rect.x0 - 10.0,
                y0=rect.y0 - 10.0,
                width=rect.width + 20.0,
                height=rect.height + 20.0,
                center=rect.center,
            )
            ctx.set_source_rgb(1.0, 0.0, 1.0)
            ctx.set_line_width(1.0)
            path_rect(ctx, debug_rect)
            ctx.stroke()
            ctx.set_source_rgb(*BORDER_COLOR)
            ctx.set_line_width(DEFAULT_LINE_WIDTH)
    elif class_name == "unit of information":
        draw_shape_with_clone(
            ctx,
            rect,
            shape_label,
            font_px,
            False,
            DEFAULT_LINE_WIDTH,
            DEFAULT_FILL_COLOR,
            lambda ctx, rect: path_round_rect(ctx, rect, max(min(rect.width, rect.height) * 0.1, 1.0)),
        )
    elif class_name == "state variable":
        draw_shape_with_clone(
            ctx,
            rect,
            shape_label,
            font_px,
            False,
            DEFAULT_LINE_WIDTH,
            DEFAULT_FILL_COLOR,
            lambda ctx, rect: path_round_rect(ctx, rect, 0.24 * max(rect.width, rect.height)),
        )
    elif class_name in {"and", "or", "not"}:
        path_ellipse(ctx, rect)
        ctx.set_line_width(DEFAULT_LINE_WIDTH)
        ctx.set_source_rgb(*DEFAULT_FILL_COLOR)
        ctx.fill_preserve()
        ctx.set_source_rgb(*BORDER_COLOR)
        ctx.stroke()
        draw_text_centered(ctx, rect.center, shape_label, font_px)
        if SHOW_LOGICAL_DEBUG_BBOX:
            ctx.set_source_rgb(1.0, 0.0, 1.0)
            ctx.set_line_width(1.0)
            path_rect(ctx, rect)
            ctx.stroke()
            ctx.set_source_rgb(*BORDER_COLOR)
            ctx.set_line_width(DEFAULT_LINE_WIDTH)
    else:
        draw_shape_with_clone(
            ctx,
            rect,
            shape_label,
            font_px,
            has_clone,
            DEFAULT_LINE_WIDTH,
            DEFAULT_FILL_COLOR,
            path_rect,
        )

    orientation = glyph.orientation
    if orientation is None and class_name in {
        "process",
        "omitted process",
        "uncertain process",
        "association",
        "dissociation",
    }:
        orientation = "horizontal"
    if orientation:
        connector_len = port_connector_len_px_for_class(class_name)
        draw_orientation_marker(ctx, rect, orientation, connector_len)

    if place_label_bottom:
        draw_text_bottom_centered(ctx, rect, label, font_px)

    for child in children:
        if child.class_name in {"unit of information", "state variable"}:
            continue
        render_glyph_tree(ctx, transform, child, child_map, show_clone_markers)


# File-level rendering

def render_sbgnml_file(
    input_path: Path,
    output_path: Path,
    padding: float = DEFAULT_PADDING_PX,
    show_clone_markers: bool = False,
) -> None:
    """Render a single SBGNML file to PNG and SVG."""

    glyphs, arcs, bounds = parse_sbgnml(input_path)
    transform, width, height = transform_with_padding(bounds, padding)

    surface, ctx = create_png_surface(int(math.ceil(width)), int(math.ceil(height)))
    render_sbgnml(ctx, transform, glyphs, arcs, show_clone_markers)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    surface.write_to_png(str(output_path))

    svg_path = default_svg_output_path(output_path)
    render_svg(svg_path, width, height, lambda c: render_sbgnml(c, transform, glyphs, arcs, show_clone_markers))
