#!/usr/bin/env python3
"""Exercise every renderer against the canonical SBGN-ML inputs."""

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import shutil
import struct
import subprocess
import sys
from typing import Any, Sequence

REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_INPUT_DIRECTORY = REPOSITORY_ROOT / "render_examples"
DEFAULT_OUTPUT_DIRECTORY = REPOSITORY_ROOT / "tests" / "output"
DEFAULT_WIDTH = 1200
DEFAULT_HEIGHT = 800
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
STRUCTURAL_FIELDS = ("id", "kind", "type", "text", "marker", "source", "target")


@dataclass(frozen=True)
class Renderer:
    """Describe one renderer command.

    Args:
        name: Stable name used for output directories.
        command: Executable and fixed arguments before renderer options.
        working_directory: Directory in which the command runs.
        uses_subcommand: Whether the CLI requires the draw_sbgnml subcommand.
    """

    name: str
    command: tuple[str, ...]
    working_directory: Path
    uses_subcommand: bool = True


def run_command(command: Sequence[str], working_directory: Path) -> None:
    """Run a command and fail with its native diagnostic.

    Args:
        command: Command and arguments to execute.
        working_directory: Directory in which to run the command.

    Returns:
        None.
    """
    subprocess.run(command, cwd=working_directory, check=True)


def require_tools() -> None:
    """Verify that all native toolchains are available.

    Returns:
        None.
    """
    missing = [
        name for name in ("cargo", "go", "Rscript") if shutil.which(name) is None
    ]
    if missing:
        raise RuntimeError(f"Missing required tools: {', '.join(missing)}")


def build_renderers(output_directory: Path) -> list[Renderer]:
    """Build native renderers and return their invocation details.

    Args:
        output_directory: Root for generated test artifacts.

    Returns:
        Renderer command descriptions for all four implementations.
    """
    rust_directory = REPOSITORY_ROOT / "rust"
    go_directory = REPOSITORY_ROOT / "go"
    go_binary = output_directory / "bin" / "render_sbgn_go"
    go_binary.parent.mkdir(parents=True, exist_ok=True)

    run_command(
        [
            "cargo",
            "build",
            "--manifest-path",
            str(rust_directory / "Cargo.toml"),
            "--bin",
            "render_sbgn_rs",
        ],
        REPOSITORY_ROOT,
    )
    run_command(["go", "build", "-o", str(go_binary), "."], go_directory)

    return [
        Renderer(
            "python",
            (sys.executable, "-m", "render_sbgn_py.cli"),
            REPOSITORY_ROOT / "python",
        ),
        Renderer(
            "rust",
            (str(rust_directory / "target" / "debug" / "render_sbgn_rs"),),
            rust_directory,
        ),
        Renderer("go", (str(go_binary),), go_directory),
        Renderer(
            "r",
            ("Rscript", "draw_sbgnml.R"),
            REPOSITORY_ROOT / "r",
            uses_subcommand=False,
        ),
    ]


def find_inputs(input_directory: Path, limit: int | None) -> list[Path]:
    """Find canonical SBGN inputs in stable order.

    Args:
        input_directory: Directory to search recursively.
        limit: Optional maximum number of inputs for a smoke run.

    Returns:
        Sorted paths that should participate in conformance tests.
    """
    inputs = sorted(
        path
        for path in input_directory.rglob("*.sbgn")
        if not any(part.startswith(("ignore_", "output_")) for part in path.parts)
    )
    if limit is not None:
        inputs = inputs[:limit]
    if not inputs:
        raise RuntimeError(f"No SBGN inputs found under {input_directory}")
    return inputs


def verify_png(path: Path, width: int, height: int) -> None:
    """Verify a generated PNG signature and dimensions.

    Args:
        path: PNG file to inspect.
        width: Expected pixel width.
        height: Expected pixel height.

    Returns:
        None.
    """
    header = path.read_bytes()[:24]
    if len(header) != 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        raise AssertionError(f"{path} is not a valid PNG")
    actual_width, actual_height = struct.unpack(">II", header[16:24])
    if (actual_width, actual_height) != (width, height):
        raise AssertionError(
            f"{path} is {actual_width}x{actual_height}, expected {width}x{height}"
        )


def load_manifest(
    path: Path, input_path: Path, width: int, height: int
) -> dict[str, Any]:
    """Load and validate a renderer manifest.

    Args:
        path: JSON manifest path.
        input_path: Source diagram path.
        width: Expected canvas width.
        height: Expected canvas height.

    Returns:
        Parsed manifest record.
    """
    manifest = json.loads(path.read_text(encoding="utf-8"))
    if manifest.get("diagram_id") != input_path.name:
        raise AssertionError(f"Unexpected diagram_id in {path}")
    if manifest.get("coordinate_space") != "rendered_pixel":
        raise AssertionError(f"Unexpected coordinate_space in {path}")
    canvas = manifest.get("canvas", {})
    if (canvas.get("width"), canvas.get("height")) != (width, height):
        raise AssertionError(f"Unexpected canvas dimensions in {path}")
    if not manifest.get("elements"):
        raise AssertionError(f"No rendered elements in {path}")
    return manifest


def structural_signature(manifest: dict[str, Any]) -> list[tuple[Any, ...]]:
    """Return backend-independent manifest fields for comparison.

    Args:
        manifest: Parsed renderer manifest.

    Returns:
        Stable tuples describing primitive identity and topology.
    """
    return sorted(
        tuple(element.get(field) for field in STRUCTURAL_FIELDS)
        for element in manifest["elements"]
    )


def render_input(
    renderer: Renderer,
    input_path: Path,
    relative_path: Path,
    output_directory: Path,
    width: int,
    height: int,
) -> dict[str, Any]:
    """Render one image and manifest, then validate both.

    Args:
        renderer: Renderer command description.
        input_path: Canonical SBGN-ML file.
        relative_path: Input path relative to the canonical root.
        output_directory: Root for generated output.
        width: Requested image width.
        height: Requested image height.

    Returns:
        Parsed manifest record.
    """
    base_path = output_directory / renderer.name / relative_path.with_suffix("")
    image_path = base_path.with_suffix(".png")
    manifest_path = base_path.with_suffix(".json")
    image_path.parent.mkdir(parents=True, exist_ok=True)

    subcommand = ("draw_sbgnml",) if renderer.uses_subcommand else ()
    shared_args = (
        *subcommand,
        "--input-path",
        str(input_path),
        "--width",
        str(width),
        "--height",
        str(height),
    )
    run_command(
        (*renderer.command, *shared_args, "--output-path", str(image_path)),
        renderer.working_directory,
    )
    verify_png(image_path, width, height)
    run_command(
        (
            *renderer.command,
            *shared_args,
            "--output-path",
            str(manifest_path),
            "--generate-render-test-manifest",
        ),
        renderer.working_directory,
    )
    return load_manifest(manifest_path, input_path, width, height)


def main() -> None:
    """Run cross-language rendering and structural conformance checks.

    Returns:
        None.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIRECTORY)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIRECTORY)
    parser.add_argument("--width", type=int, default=DEFAULT_WIDTH)
    parser.add_argument("--height", type=int, default=DEFAULT_HEIGHT)
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    require_tools()
    renderers = build_renderers(args.output_dir)
    inputs = find_inputs(args.input_dir, args.limit)

    for index, input_path in enumerate(inputs, start=1):
        relative_path = input_path.relative_to(args.input_dir)
        print(f"[{index}/{len(inputs)}] {relative_path}", flush=True)
        manifests = {
            renderer.name: render_input(
                renderer,
                input_path,
                relative_path,
                args.output_dir,
                args.width,
                args.height,
            )
            for renderer in renderers
        }
        baseline = structural_signature(manifests["python"])
        for name, manifest in manifests.items():
            if structural_signature(manifest) != baseline:
                raise AssertionError(
                    f"{relative_path}: {name} manifest structure differs from Python"
                )

    print(
        f"Conformance passed for {len(inputs)} inputs and {len(renderers)} renderers."
    )


if __name__ == "__main__":
    main()
