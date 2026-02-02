# render_sbgn_py

SBGNML renderer implemented in Python with a pycairo backend.

## Usage

Render a single SBGNML file (PNG + SVG):

```bash
uv run python -m render_sbgn_py.cli draw_sbgnml \
  --input /workspace/examples/sbgn/and.sbgn \
  --output /workspace/output_render_sbgn_py/and.png
```

Render all examples (PNG + SVG):

```bash
uv run python -m render_sbgn_py.cli render-examples \
  --input-dir /workspace/examples/sbgn \
  --output-dir /workspace/output_render_sbgn_py
```

## uvx usage

Run the CLI directly with `uvx` from the repo:

```bash
uvx --from /workspace/render_sbgn_py render_sbgn_py --help
uvx --from /workspace/render_sbgn_py render_sbgn_py draw_sbgnml \
  --input /workspace/examples/sbgn/and.sbgn \
  --output /workspace/output_render_sbgn_py/and.png
```

## Notes

- SVG output is generated alongside PNG output using Cairo's SVG surface.
- Font rendering expects Liberation Sans to be installed on the system.
- If pycairo wheels are unavailable for your platform, install system Cairo
  (e.g., `sudo apt-get install libcairo2` on Debian/Ubuntu) before running `uv sync`.
