# render_sbgn_py

Python SBGN-ML renderer using pycairo. Package version: 0.0.5.

## Requirements and installation

Python 3.10 or newer, Cairo, and uv are required. From this directory:

```bash
uv sync
```

If pycairo cannot find Cairo, install the platform's Cairo development package
first.

## Usage

```bash
uv run render_sbgn_py draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path colors.png
```

An explicit `.png` or `.svg` output path writes that format. Without an output
path, `--format png,svg` writes both formats. Run `uv run render_sbgn_py --help`
for styling, sizing, clone-marker, and manifest options.

## Tests

```bash
uv run --with pytest pytest
```

Repository-wide conformance tests are run from the parent directory with
`./scripts/test-conformance.sh`.
