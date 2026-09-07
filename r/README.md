# renderSbgnR

R SBGN-ML renderer using base graphics with `xml2` parsing.

## Requirements and installation

R 4.2 or newer is required. From the repository root:

```bash
R CMD INSTALL r
```

Package dependencies declared in `DESCRIPTION` include `xml2`, `jsonlite`,
`showtext`, and `sysfonts`. The package bundles Liberation Sans and registers it
under a private family name before rendering, so normal rendering does not
depend on system-font fallback.

The [project releases](https://github.com/cannin/render_sbgn/releases) include
an installable `renderSbgnR_<version>.tar.gz` source package that has passed
`R CMD check`. Install it with `R CMD INSTALL renderSbgnR_<version>.tar.gz`.

## Usage

From R:

```r
renderSbgnR::draw_sbgnml("input.sbgn", "output.png")
renderSbgnR::draw_sbgnml("input.sbgn", "output.svg")
```

From a source checkout:

```bash
Rscript r/draw_sbgnml.R \
  --input-path render_examples/sbgn_examples/colors.sbgn \
  --output-path colors.png
```

Run `Rscript r/draw_sbgnml.R --version` to print the coordinated version.

## Tests

```bash
./scripts/test-r.sh
```

Repository-wide conformance tests are run with
`./scripts/test-conformance.sh`.
