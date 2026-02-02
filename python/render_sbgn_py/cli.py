"""Command-line interface for render_sbgn_py."""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Iterable

from render_sbgn_py.renderer import (
    DEFAULT_PADDING_PX,
    render_sbgnml_file,
)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments.

    Returns:
        Parsed arguments namespace.
    """
    parser = argparse.ArgumentParser(description="Render SBGN diagrams to PNG/SVG using pycairo.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    draw_sbgnml = subparsers.add_parser(
        "draw_sbgnml",
        help="Render an SBGNML file.",
    )
    draw_sbgnml.add_argument(
        "--input",
        default="/workspace/examples/sbgn/regulation_of_tgfbeta-induced_metastasis.sbgn",
        help="Input SBGNML file path.",
    )
    draw_sbgnml.add_argument("--output", default="sbgnml.png", help="Output PNG path.")
    draw_sbgnml.add_argument(
        "--padding",
        type=float,
        default=DEFAULT_PADDING_PX,
        help="Padding around the diagram.",
    )
    draw_sbgnml.add_argument(
        "--clone-markers",
        action="store_true",
        help="Render clone markers when present.",
    )

    render_examples = subparsers.add_parser(
        "render-examples", help="Render all SBGN examples to an output directory."
    )
    render_examples.add_argument(
        "--input-dir",
        default=str(Path.cwd() / "examples" / "sbgn"),
        help="Input directory containing .sbgn files.",
    )
    render_examples.add_argument(
        "--output-dir",
        default=str(Path.cwd() / "output_render_sbgn_py"),
        help="Output directory for rendered PNGs.",
    )
    render_examples.add_argument(
        "--padding",
        type=float,
        default=DEFAULT_PADDING_PX,
        help="Padding around the diagram.",
    )
    render_examples.add_argument(
        "--clone-markers",
        action="store_true",
        help="Render clone markers when present.",
    )

    return parser.parse_args()


def find_sbgn_files(input_dir: Path) -> Iterable[Path]:
    """Yield all .sbgn files under the input directory.

    Args:
        input_dir: Directory to search.

    Returns:
        Iterable of .sbgn file paths.
    """
    return sorted(input_dir.rglob("*.sbgn"))


def main() -> None:
    """Entry point for the render_sbgn_py CLI.

    Returns:
        None.
    """
    args = parse_args()

    if args.command == "draw_sbgnml":
        render_sbgnml_file(
            Path(args.input),
            Path(args.output),
            padding=args.padding,
            show_clone_markers=args.clone_markers,
        )
        return

    if args.command == "render-examples":
        input_dir = Path(args.input_dir)
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        for sbgn_file in find_sbgn_files(input_dir):
            output_path = output_dir / f"{sbgn_file.stem}_python.png"
            render_sbgnml_file(
                sbgn_file,
                output_path,
                padding=args.padding,
                show_clone_markers=args.clone_markers,
            )
        return


if __name__ == "__main__":
    main()
