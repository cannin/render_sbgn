"""Regression tests for SBGN arc geometry and endpoint markers."""

import unittest
from unittest.mock import patch

import cairo

from render_sbgn_py.renderer import (
    Arc,
    BBox,
    Glyph,
    Point,
    draw_js_marker,
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


if __name__ == "__main__":
    unittest.main()
