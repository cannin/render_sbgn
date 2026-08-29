# render_sbgn

Render SBGN-ML pathway diagrams to PNG or SVG with equivalent native
implementations in Python, Rust, Go, and R. The four implementations live in
one repository so renderer behavior, examples, releases, and conformance checks
can evolve together while each package remains independently installable.

The coordinated project version is **0.0.5**.

## Choose an implementation

| Implementation | Requirements | Install/build | Documentation |
| --- | --- | --- | --- |
| [Python](python/) | Python 3.10+, uv, Cairo | `cd python && uv sync` | [Python README](python/README.md) |
| [Rust](rust/) | Rust and the musl target | `./scripts/build-rust-musl.sh` | [Rust README](rust/README.md) |
| [Go](go/) | Go 1.25+ | `cd go && go build ./...` | [Go README](go/README.md) |
| [R](r/) | R 4.2+ | `R CMD INSTALL r` | [R README](r/README.md) |

Installing one implementation does not install or require the other language
toolchains.

## Quick start

All CLIs accept the same core input and output flags. These examples render the
same shared input:

```bash
# Python
(cd python && uv run render_sbgn_py draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path colors-python.png)

# Rust (host development build)
(cd rust && cargo run -- draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path ../colors-rust.png)

# Go
(cd go && go run . draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path ../colors-go.png)

# R
Rscript r/draw_sbgnml.R \
  --input-path render_examples/sbgn_examples/colors.sbgn \
  --output-path colors-r.png
```

## Shared renderer behavior

The four CLIs accept SBGN-ML input and support PNG, SVG, fixed canvas sizes,
padding, clone markers, glyph colors, style JSON, and deterministic render-test
manifests. The common input/output flags are `--input-path` and
`--output-path`; run the selected implementation with `--help` for its complete
native command syntax.

Invalid XML, missing inputs, unsupported output extensions, invalid options,
and conflicting color/style sources return a nonzero status. PNG bytes are not
required to match across backends because font rasterization, antialiasing,
metadata, and compression can differ. Cross-language tests instead verify the
image contract and compare backend-independent manifest primitives.

## Shared examples and tests

[render_examples/](render_examples/) is the single canonical collection of
SBGN-ML test inputs. No language package contains a duplicate copy. Generated
test files are written beneath the ignored `tests/output/` directory.

Run native package checks and then render every shared input with all four
implementations:

```bash
./scripts/test-all.sh
```

Run only the shared renderer conformance suite:

```bash
./scripts/test-conformance.sh
```

The conformance suite verifies successful rendering, PNG signatures and
dimensions, and renderer manifests for every canonical `.sbgn` file.

## Continuous integration

The GitHub Actions workflow runs all four renderers on Ubuntu, including the
shared conformance suite and a statically linked Rust musl release build. Test
the same workflow locally with [act](https://github.com/nektos/act):

```bash
act push -j ubuntu-all-renderers
```

## Repository layout

- [python/](python/) - Python package and tests.
- [rust/](rust/) - Rust crate, musl configuration, CLI, and Lambda runtime.
- [go/](go/) - Go module, CLI, and Lambda wrappers.
- [r/](r/) - R package and source-checkout CLI.
- [render_examples/](render_examples/) - shared SBGN-ML inputs.
- [tests/](tests/) - cross-language conformance tooling and generated output.
- [AGENTS.md](AGENTS.md) - maintenance rules and exact verification commands.

## Versioning

Package metadata is coordinated at `0.0.5`. Repository releases use `v0.0.5`;
because the Go module is in a subdirectory, its corresponding module tag is
`go/v0.0.5`.

## License

This project is available under the [MIT License](LICENSE).
