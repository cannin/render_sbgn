# render_sbgn_py

Python SBGN-ML renderer using pycairo.

## Requirements and installation

Python 3.10 or newer, Cairo, and uv are required. From this directory:

```bash
uv sync
```

If pycairo cannot find Cairo, install the platform's Cairo development package
first.

Alternatively, download the `.whl` file from the
[project releases](https://github.com/cannin/render_sbgn/releases) and install
it with `python -m pip install ./render_sbgn_py-<version>-py3-none-any.whl`.

## Usage

```bash
uv run render_sbgn_py draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path colors.png
```

An explicit `.png` or `.svg` output path writes that format. Without an output
path, `--format png,svg` writes both formats. Run `uv run render_sbgn_py --help`
for styling, sizing, clone-marker, and manifest options.

## Library usage

The renderer can also be called directly from Python:

```python
from pathlib import Path

from render_sbgn_py import draw_sbgnml


draw_sbgnml(Path("diagram.sbgn"), Path("diagram.png"))
```

The public package API also exports `write_render_test_manifest`. Both functions
accept filesystem paths, write their results to disk, and return `None`.

## Tests

```bash
uv run --with pytest pytest
```

Repository-wide conformance tests are run from the parent directory with
`./scripts/test-conformance.sh`.
