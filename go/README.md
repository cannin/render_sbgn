# render_sbgn_go

Go CLI for rendering SBGNML diagrams to PNG and SVG.

This project is a Go-native port of `../render_sbgn_rs`. It replaces Cairo/Pango with
[`github.com/tdewolff/canvas`](https://github.com/tdewolff/canvas), which provides vector paths,
text rendering, and SVG/PNG output from one drawing model.

## Build

```bash
go build ./...
```

## Run

```bash
go run . draw_sbgnml \
  --input ../render_examples/sbgn_examples/colors.sbgn \
  --output out.png \
  --padding 10
```

`--input` is required. PNG and SVG outputs are written by default using the `--output` path to
derive each extension.

Useful flags:

```text
-i, --input           SBGNML input file
-o, --output          Output base path
-f, --format          Comma-separated output formats: png,svg
-p, --padding         Padding in output units
    --clone-markers   Draw clone markers, default true
```

## Lambda MCP wrapper

`cmd/lambda_mcp` is a separate AWS Lambda Function URL wrapper that exposes the
renderer as a small MCP-style JSON-RPC server. It keeps the CLI unchanged and
invokes `/var/task/render_sbgn_go` as a subprocess.

Build the MCP deployment zip:

```bash
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o render_sbgn_go .
CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build -o bootstrap_mcp ./cmd/lambda_mcp
mkdir -p /tmp/render_sbgn_go_mcp_pkg
cp bootstrap_mcp /tmp/render_sbgn_go_mcp_pkg/bootstrap
cp render_sbgn_go /tmp/render_sbgn_go_mcp_pkg/render_sbgn_go
(cd /tmp/render_sbgn_go_mcp_pkg && zip -r /workspace/render_sbgn_go/function_mcp.zip bootstrap render_sbgn_go)
```

The MCP tool is `render_sbgn_png`. It accepts:

```json
{"xml":"<sbgn>...</sbgn>"}
```

It renders a PNG, uploads it to `s3://YOUR_BUCKET/TIMESTAMP_HASH.png`, and
returns the file location as JSON text in the MCP `tools/call` response:

```json
{
  "url": "https://s3.us-east-1.amazonaws.com/YOUR_BUCKET/TIMESTAMP_HASH.png",
  "s3_uri": "s3://YOUR_BUCKET/TIMESTAMP_HASH.png",
  "bucket": "YOUR_BUCKET",
  "key": "TIMESTAMP_HASH.png"
}
```

The Lambda execution role must allow `s3:PutObject` on the bucket, and the
bucket or object policy must make the returned URL readable by your MCP client.
