# render_sbgn_go

Go SBGN-ML renderer using `github.com/tdewolff/canvas`. Releases use a
subdirectory-prefixed tag such as `go/vX.Y.Z`, following Go conventions for a
module in a subdirectory.

Prebuilt release executables are available for Ubuntu Linux and Windows on
amd64, and macOS on arm64, from the
[project releases](https://github.com/cannin/render_sbgn/releases). On Linux or
macOS, run `chmod +x` on a downloaded executable before use.

## Requirements and build

Go 1.25 or newer is required. From this directory:

```bash
go build ./...
```

The executable embeds Liberation Sans, so label rendering does not depend on a
host font installation. If the embedded font cannot be loaded, the fallback
order is Liberation Sans, Arial, DejaVu Sans, Helvetica, then generic
sans-serif.

Build and test the current system plus every release target with:

```bash
make
```

## Usage

```bash
go run . draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path colors.png
```

An explicit `.png` or `.svg` output path writes that format. Run
`go run . --help` for styling, sizing, clone-marker, and manifest options.

## Tests

```bash
go test ./...
```

`cmd/lambda` and `cmd/lambda_mcp` contain optional AWS Lambda wrappers. They do
not change the standalone renderer interface.
