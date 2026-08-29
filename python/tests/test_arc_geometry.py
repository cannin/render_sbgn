"""Regression tests for SBGN arc geometry and endpoint markers."""

import unittest
from unittest.mock import patch

import cairo

from render_sbgn_py.renderer import (
    Arc,
    BBox,
    Glyph,
    JS_NODE_FILL_COLOR,
    Point,
    Port,
    auxiliary_glyph_shape,
    draw_js_marker,
    js_arc_line_path,
    js_arc_marker_point,
    js_arc_path,
)


def make_glyph(glyph_id: str, x: float) -> Glyph:
    """Build a small biological-activity glyph for geometry tests.

    Args:
        glyph_id: Glyph identifier.
        x: Left edge of the glyph bounding box.

    Returns:
        Test glyph with a 10-by-10 bounding box.
    """

    return Glyph(
        id=glyph_id,
        parent_id=None,
        class_name="biological activity",
        bbox=BBox(x=x, y=0.0, w=10.0, h=10.0),
        extra_width=None,
        extra_height=None,
        label=glyph_id,
        ports=[],
        has_clone=False,
        state_value=None,
        state_variable=None,
        orientation=None,
    )


class ArcGeometryTests(unittest.TestCase):
    """Verify that renderer arcs retain SBGN geometry and marker sizing."""

    def setUp(self) -> None:
        """Create two glyphs and their renderer lookup."""

        self.source = make_glyph("source", 0.0)
        self.target = make_glyph("target", 30.0)
        self.glyph_lookup = {
            self.source.id: self.source,
            self.target.id: self.target,
        }

    def test_explicit_arc_path_keeps_intermediate_points(
        self,
    ) -> None:
        """Keep explicit start, next, and end points in order."""

        expected_points = [
            Point(10.0, 5.0),
            Point(20.0, 15.0),
            Point(30.0, 5.0),
        ]
        arc = Arc(
            id="arc",
            class_name="stimulation",
            source="source",
            target="target",
            points=expected_points,
        )

        resolved = js_arc_path(arc, self.glyph_lookup, {})

        self.assertIsNotNone(resolved)
        points, source_id, target_id = resolved
        self.assertEqual(points, expected_points)
        self.assertEqual(source_id, "source")
        self.assertEqual(target_id, "target")

    def test_missing_arc_path_uses_glyph_boundaries(self) -> None:
        """Keep a fallback arc outside both endpoint glyph interiors."""

        arc = Arc(
            id="arc",
            class_name="stimulation",
            source="source",
            target="target",
            points=[],
        )

        resolved = js_arc_path(arc, self.glyph_lookup, {})

        self.assertIsNotNone(resolved)
        points, _, _ = resolved
        self.assertEqual(points, [Point(10.0, 5.0), Point(30.0, 5.0)])

    def test_inhibition_bar_uses_cytoscape_marker_width(self) -> None:
        """Scale a tee to its 0.3-wide Cytoscape marker coordinates."""

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 20, 20)
        context = cairo.Context(surface)
        with patch("render_sbgn_py.renderer.draw_inhibition_bar") as draw_bar:
            draw_js_marker(
                context,
                "tee",
                "negative influence",
                Point(10.0, 10.0),
                Point(0.0, 10.0),
                100.0,
                (0.0, 0.0, 0.0),
            )

        draw_bar.assert_called_once()
        self.assertAlmostEqual(draw_bar.call_args.args[3], 30.0)

    def test_entity_names_select_auxiliary_shapes(self) -> None:
        """Map unit-of-information entity names to their SBGN shapes."""

        expected_shapes = {
            "macromolecule": "round_rectangle",
            "nucleic acid feature": "bottom_round_rectangle",
            "complex": "complex",
            "simple chemical": "stadium_round_rectangle",
            "unspecified entity": "ellipse",
            "perturbation": "perturbing_agent",
        }
        glyph = make_glyph("auxiliary", 0.0)
        glyph.class_name = "unit of information"
        glyph.parent_id = "parent"
        for entity_name, expected_shape in expected_shapes.items():
            with self.subTest(entity_name=entity_name):
                glyph.entity_name = entity_name
                self.assertEqual(auxiliary_glyph_shape(glyph), expected_shape)

    def test_hollow_stimulation_marker_masks_underlying_line(self) -> None:
        """Fill hollow stimulation markers with the node background."""

        surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, 20, 20)
        context = cairo.Context(surface)
        with patch("render_sbgn_py.renderer.draw_marker_polygon") as draw_polygon:
            draw_js_marker(
                context,
                "triangle",
                "stimulation",
                Point(10.0, 10.0),
                Point(0.0, 10.0),
                20.0,
                (0.0, 0.0, 0.0),
            )

        self.assertEqual(
            draw_polygon.call_args.kwargs["background_fill"], JS_NODE_FILL_COLOR
        )

    def test_triangle_marker_tip_overlaps_target_boundary(self) -> None:
        """Move triangle tips into targets to avoid visible connection seams."""

        arc = Arc(
            id="arc",
            class_name="stimulation",
            source="source",
            target="target",
            points=[Point(0.0, 0.0), Point(10.0, 0.0)],
        )

        marker_point = js_arc_marker_point(arc, arc.points)

        self.assertEqual(marker_point, Point(13.125, 0.0))

    def test_arc_line_extends_to_process_port(self) -> None:
        """Eliminate half-stroke seams at process and logical-node ports."""

        self.source.class_name = "process"
        self.source.ports = [Port(x=12.0, y=5.0, id="source.1")]
        arc = Arc(
            id="arc",
            class_name="production",
            source="source.1",
            target="target",
            points=[Point(12.625, 5.0), Point(30.0, 5.0)],
        )

        points = js_arc_line_path(
            arc,
            arc.points,
            self.glyph_lookup,
            {"source.1": "source"},
        )

        self.assertEqual(points[0], Point(12.0, 5.0))

    def test_delay_arc_clips_to_painted_boundary(self) -> None:
        """Remove the empty port gap around a delay glyph."""

        self.source.class_name = "delay"
        self.source.ports = [Port(x=5.0, y=-4.0, id="source.1")]
        arc = Arc(
            id="arc",
            class_name="positive influence",
            source="source.1",
            target="target",
            points=[Point(5.0, -4.0), Point(30.0, 5.0)],
        )

        resolved = js_arc_path(
            arc,
            self.glyph_lookup,
            {"source.1": "source"},
        )

        self.assertIsNotNone(resolved)
        points, _, _ = resolved
        self.assertEqual(points[0], Point(5.0, -0.625))


if __name__ == "__main__":
    unittest.main()
