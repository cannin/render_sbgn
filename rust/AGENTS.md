# Repository Guidelines

## Project Structure
- `src/main.rs`: renderer CLI, SBGNML parsing, and rendering.
- `src/bin/lambda.rs`: optional AWS Lambda custom-runtime entry point.
- `.cargo/config.toml`: musl linker configuration.
- `assets/`: fonts embedded into the musl-compatible binary.
- `Cargo.toml` / `Cargo.lock`: Rust package metadata.
- `target/`: build artifacts.
- Style reference repo: `../cytoscape-sbgn-stylesheet/` (sizes, offsets, SVG glyph details).
- XML parser: `xmltree` (DOM-style read).

## Build, Test, Run
- Host build: `cargo build` (debug).
- Linux musl release: `../scripts/build-rust-musl.sh`.
- Run (release): `./target/release/render_sbgn_rs draw_sbgnml --input examples/sbgn/foo.sbgn --output out.png --padding 10`.
- Batch render (examples): 
  - Use `../scripts/test-conformance.sh` from this directory.
- Tests: none yet (use `cargo test` if you add them).
- Formatting: `cargo fmt` (system `rustfmt` package is acceptable; install via `apt-get install rustfmt` if missing).
- Release binaries must target musl and remain independent of host C graphics
  libraries.

## Coding Style
- Rust 2021; run `cargo fmt` when changing structure.
- Prefer small helpers, descriptive names, and `anyhow::Context` for errors.

## Rendering & Style Notes
- Use `../cytoscape-sbgn-stylesheet/src/sbgnStyle/`:
  - `element.js` for default sizes/shapes, `glyph/` for overlays, `index.js` for selector styling.
- Key constants (see `src/main.rs`): `ARROW_SCALE=1.75`, `ARROW_SIZE=8`, `BAR_LENGTH=12`, `BAR_OFFSET=14`, `CATALYSIS_OVERLAP_RATIO`, `PORT_CONNECTOR_LEN_PX=10`.
- Fills/markers: default white; complexes white; association `#6B6B6B`; catalysis is opaque white circle that overlaps the arc line by `CATALYSIS_OVERLAP_RATIO`; stimulation/necessary stimulation triangles are opaque white; production arrows are filled.
- Coordinates: `(0,0)` is top-left; all `bbox x/y` are absolute. Unit-of-information/state-variable `bbox` are absolute (not relative). Nested glyphs render above parents (z-order). If a process/association/dissociation node lacks `orientation`, treat it as `horizontal`. Orientation markers draw outside the bbox at the center axis.
- Render extensions: supports `<renderInformation>` for background color, color definitions, and per-id styles (stroke/fill/width/font). Default style applies when `idList` is empty. `nwt:extraInfo` is ignored.
- Background: defaults to white; transparent renderInformation backgrounds are treated as white.
- Tag glyphs: notch side faces the connected arc side when possible.
- Equivalence arcs: no arrowhead markers.
- Example (absolute unit of info):
  ```xml
  <glyph id="glyph6" class="nucleic acid feature">
    <bbox y="365.0" x="571.0" h="60.0" w="108.0"/>
    <glyph id="glyph6a" class="unit of information">
      <bbox y="357.0" x="600.0" h="16.0" w="50.0"/>
    </glyph>
  </glyph>
  ```

## Process Nodes
- Process: square with two small arc ports on opposite sides; consumption/production arcs connect to port ends; modulation arcs connect to the other two sides.
- Omitted process: square with two parallel NW-to-SE slanted lines; same ports as process.
- Uncertain process: square with a question mark; same ports as process.
- Association: filled circle with two small arc ports on opposite sides.
- Dissociation: ring (circle with concentric inner circle) with two small arc ports on opposite sides.

## Logical Operators
- And/Or/Not: circle containing text "AND"/"OR"/"NOT" with two small arc ports on opposite sides.
- Logical operator orientation markers use 20px connector length (default is 10px for other glyphs).
