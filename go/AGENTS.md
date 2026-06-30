# Repository Guidelines

## Project Structure
- `main.go`: single Go binary containing CLI, SBGNML parsing, and rendering.
- `go.mod`: Go module metadata. The main rendering backend is `github.com/tdewolff/canvas`.

## Build, Test, Run
- Build: `go build ./...`
- Run:
  ```bash
  go run . draw_sbgnml --input ../render_examples/sbgn_examples/colors.sbgn --output out.png --padding 10
  ```
- PNG and SVG are emitted by default. Use `--format png`, `--format svg`, or `--format png,svg`.

## Coding Style
- Keep source ASCII-only.
- Prefer small helpers with explicit names.
- Keep constants near the top of `main.go`.
- Run `gofmt -w .` before committing.

## Commenting
- Document `main.go` for maintenance and educational purposes when changing parser, layout, rendering, or export behavior.
- Document every function with its purpose, and document all parameters in that function comment.
- Prefer comments at section boundaries and above non-obvious SBGN-specific logic, such as absolute child glyph coordinates, z-order, clone marker clipping, tag orientation inference, multimer ghost shapes, and arc marker geometry.
- Keep comments concise and useful to future maintainers; avoid restating what a single line of code already says.
- When adding a new shape, arc type, or renderInformation feature, include a short comment explaining the relevant SBGN convention or rendering tradeoff.

## Rendering Notes
- Coordinates use `canvas.CartesianIV` so `(0,0)` is top-left, matching SBGN bbox coordinates.
- `tdewolff/canvas` is used as the Go-native Cairo replacement for vector paths, text, SVG, and raster PNG output.

## Typography
- Unless the user specifically requests serif text, write code to render labels and UI text with sans-serif or monospace fonts.
- Always include font fallback stacks, especially for SVG output:
  - Sans-serif: `font-family="Arial, 'Liberation Sans', Arimo, sans-serif"`
  - Serif: `font-family="Times New Roman, 'Liberation Serif', Tinos, serif"`
  - Monospace: `font-family="Courier New, 'Liberation Mono', Cousine, monospace"`
