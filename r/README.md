# renderSbgnR

R SBGN-ML renderer using base graphics with `xml2` parsing.

## Requirements and installation

R 4.2 or newer is required. From the repository root:

```bash
R CMD INSTALL r
```

Package dependencies declared in `DESCRIPTION` are `xml2` and `jsonlite`.

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
