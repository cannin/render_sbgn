# render_sbgn_r

SBGNML renderer implemented in R using base graphics and the xml2 parser.

## Usage

Render a single SBGNML file (PNG + SVG):

```bash
Rscript -e "source('/workspace/render_sbgn_r/draw_sbgnml.R'); dir.create('/workspace/output_render_sbgn_r', showWarnings = FALSE, recursive = TRUE); draw_sbgnml('/workspace/examples/sbgn/and.sbgn', '/workspace/output_render_sbgn_r/and.png', clone_markers = TRUE)"
```

Render all examples (PNG + SVG):

```bash
cd /workspace
Rscript render_sbgn_r/render_examples.R
```

## Notes

- SVG output is generated alongside PNG output using R's `svg()` device.
- The renderer expects the `xml2` package to be installed (`install.packages('xml2')`).
- Font rendering assumes Liberation Sans is available on the system.
