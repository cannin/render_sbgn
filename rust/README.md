# render_sbgn_rs

Rust SBGN-ML renderer using `tiny-skia` and an embedded Liberation Sans font.
Crate version: 0.0.5.

The deployment artifact is a statically linked Linux musl executable. The
renderer has no Cairo or other host graphics-library dependency.

Prebuilt release executables are available for static musl Ubuntu Linux on
amd64, macOS on arm64, and Windows on amd64 from the
[project releases](https://github.com/cannin/render_sbgn/releases). On Linux or
macOS, run `chmod +x` on a downloaded executable before use.

## Build the musl release

From the repository root:

```bash
rustup target add x86_64-unknown-linux-musl
./scripts/build-rust-musl.sh
```

The executable is written to:

```text
rust/target/x86_64-unknown-linux-musl/release/render_sbgn_rs
```

## Local development and usage

Use a host build when the Linux musl executable cannot run on the development
machine:

```bash
cargo build
./target/debug/render_sbgn_rs draw_sbgnml \
  --input-path ../render_examples/sbgn_examples/colors.sbgn \
  --output-path colors.png
```

An explicit `.png` or `.svg` output path writes that format. Run
`cargo run -- --help` for styling, sizing, clone-marker, and manifest options.

## Tests

```bash
cargo test
cargo build --release --target x86_64-unknown-linux-musl
```

The `lambda` binary is retained for AWS Lambda custom-runtime deployments and
invokes `/var/task/render_sbgn_rs`.
