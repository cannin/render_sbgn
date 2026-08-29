"""Command-line interface for render_sbgn_py."""

import argparse
import json
from pathlib import Path

from render_sbgn_py.renderer import (
    DEFAULT_PADDING_PX,
    RENDERER_VERSION,
    draw_sbgnml,
    load_glyph_colors_json_file,
    load_style_json_file,
    write_render_test_manifest,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(
        description="Render SBGN diagrams to PNG/SVG using pycairo."
    )
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=RENDERER_VERSION,
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw_sbgnml = subparsers.add_parser(
        "draw_sbgnml",
        help="Render an SBGNML file.",
    )
    draw_sbgnml.add_argument(
        "-v",
        "--version",
        action="version",
        version=RENDERER_VERSION,
    )
    draw_sbgnml.add_argument(
        "-i",
        "--input-path",
        "--input_path",
        "--input",
        dest="input_path",
        default=(
            "/workspace/examples/sbgn/" "regulation_of_tgfbeta-induced_metastasis.sbgn"
        ),
        help="Input SBGNML file path.",
    )
    draw_sbgnml.add_argument(
        "-o",
        "--output-path",
        "--output_path",
        "--output",
        dest="output_path",
        default=None,
        help="Optional output PNG or SVG path.",
    )
    draw_sbgnml.add_argument(
        "-f",
        "--format",
        default="png,svg",
        help="Comma-separated output formats used when --output-path is omitted.",
    )
    draw_sbgnml.add_argument(
        "-p",
        "--padding",
        type=float,
        default=DEFAULT_PADDING_PX,
        help="Padding around the diagram.",
    )
    draw_sbgnml.add_argument(
        "--width", type=float, default=None, help="Output width in pixels."
    )
    draw_sbgnml.add_argument(
        "--height", type=float, default=None, help="Output height in pixels."
    )
    draw_sbgnml.add_argument(
        "--clone-markers",
        "--clone_markers",
        type=parse_bool,
        default=True,
        help="Render clone markers when present.",
    )
    draw_sbgnml.add_argument(
        "--no-clone-markers",
        "--no_clone_markers",
        action="store_false",
        dest="clone_markers",
        help="Do not render clone markers.",
    )
    draw_sbgnml.add_argument(
        "--generate-render-test-manifest",
        "--generate_render_test_manifest",
        action="store_true",
        help="Write render-test manifest JSON instead of PNG/SVG images.",
    )
    draw_sbgnml.add_argument(
        "--glyph-colors",
        "--glyph_colors",
        dest="glyph_colors",
        default=None,
        help="JSON object mapping glyph labels or ids to CSS hex colors.",
    )
    draw_sbgnml.add_argument(
        "--glyph-colors-json-file",
        "--glyph_colors_json_file",
        dest="glyph_colors_json_file",
        default=None,
        help="JSON file containing glyph color mappings.",
    )
    draw_sbgnml.add_argument(
        "--style-json-file",
        "--style_json_file",
        dest="style_json_file",
        default=None,
        help="JSON file containing renderer class style definitions.",
    )
    draw_sbgnml.add_argument(
        "--glyph-color-type",
        "--glyph_color_type",
        choices=("label", "id"),
        default="label",
        help="Whether glyph color keys match labels or glyph ids.",
    )
    draw_sbgnml.add_argument(
        "--auto-contrast-text",
        "--auto_contrast_text",
        type=parse_bool,
        default=True,
        help="Auto-contrast label text against custom glyph colors.",
    )
    draw_sbgnml.add_argument(
        "--no-auto-contrast-text",
        "--no_auto_contrast_text",
        action="store_false",
        dest="auto_contrast_text",
        help="Do not adjust label text color for custom glyph colors.",
    )

    return parser.parse_args()


def parse_bool(value: str | bool) -> bool:
    """Parse a CLI boolean value.

    Args:
        value: String or boolean value.

    Returns:
        Parsed boolean.
    """
    if isinstance(value, bool):
        return value
    normalized = value.lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise argparse.ArgumentTypeError("expected true or false")


def main() -> None:
    """Entry point for the render_sbgn_py CLI.

    Returns:
        None.
    """
    args = parse_args()

    if args.command == "draw_sbgnml":
        input_path = Path(args.input_path)
        output_path = Path(args.output_path) if args.output_path else None
        has_glyph_colors = args.glyph_colors is not None
        color_inputs = sum(
            [
                has_glyph_colors,
                args.glyph_colors_json_file is not None,
                args.style_json_file is not None,
            ]
        )
        if color_inputs > 1:
            raise ValueError(
                "Use only one of --glyph-colors, --glyph-colors-json-file, "
                "or --style-json-file"
            )
        glyph_colors = json.loads(args.glyph_colors or "{}")
        if args.glyph_colors_json_file:
            glyph_colors = load_glyph_colors_json_file(
                Path(args.glyph_colors_json_file)
            )
        style_config = (
            load_style_json_file(Path(args.style_json_file))
            if args.style_json_file
            else None
        )
        if args.generate_render_test_manifest:
            write_render_test_manifest(
                input_path,
                output_path or input_path.with_suffix(".json"),
                output_width=args.width,
                output_height=args.height,
                padding=args.padding,
                glyph_colors=glyph_colors,
                glyph_color_type=args.glyph_color_type,
                auto_contrast_text=args.auto_contrast_text,
                style_config=style_config,
            )
            return
        draw_sbgnml(
            input_path,
            output_path,
            padding=args.padding,
            show_clone_markers=args.clone_markers,
            glyph_colors=glyph_colors,
            glyph_color_type=args.glyph_color_type,
            auto_contrast_text=args.auto_contrast_text,
            style_config=style_config,
            output_width=args.width,
            output_height=args.height,
            output_format=args.format,
        )
        return


if __name__ == "__main__":
    main()
