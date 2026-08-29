# Repository Guidelines

## Purpose and boundaries

This repository contains one SBGN-ML renderer specification with independent
Python, Rust, Go, and R implementations. Keep implementation-specific code in
its language directory. Do not add Git submodules or make one implementation
depend on another language runtime.

The source repositories under `../rsbgn/` are retained originals. Do not edit
them while working in this monorepo.

## Canonical inputs and outputs

- `render_examples/` is the only shared renderer-input collection.
- Do not copy it into `python/`, `rust/`, `go/`, or `r/`.
- Write generated conformance artifacts only to `tests/output/`.
- Commit golden files only deliberately under `tests/expected/`.

## Required commands

Run the complete suite from repository root:

```bash
./scripts/test-all.sh
```

Run individual checks with:

```bash
(cd python && uv run --with pytest pytest)
(cd rust && cargo test)
(cd go && go test ./...)
./scripts/test-r.sh
./scripts/test-conformance.sh
```

Build the Linux musl Rust release with:

```bash
./scripts/build-rust-musl.sh
```

Run the Ubuntu GitHub Actions job locally with:

```bash
act push -j ubuntu-all-renderers
```

## Editing constraints

- Preserve the native package layout and independent installation path of each
  implementation.
- Avoid renderer-algorithm rewrites during repository maintenance.
- When common behavior changes, update the shared behavior section in
  `README.md` and test all four renderers.
- Keep package versions coordinated. Python, Rust, and R metadata and exposed
  CLI versions must agree. Go releases use subdirectory tags such as
  `go/v0.0.5`; do not add a version field to `go.mod`.
- Rust release artifacts must target musl and remain independent of host C
  libraries. Keep fonts embedded in the binary.
- Use ASCII source, format with Black/flake8 where configured for Python,
  `cargo fmt` for Rust, `gofmt` for Go, and `lintr` for R.

## Repository pitfalls

- The four imported histories are intentionally unrelated and joined by merge
  commits. Do not flatten or rewrite them.
- Some SBGN examples intentionally exercise malformed alignment or uncommon
  glyphs; a successful parse/render is still expected unless `README.md` says
  otherwise.
- PNG bytes can vary by backend even when the image is equivalent. Conformance
  checks compare observable image properties and manifests rather than raw PNG
  hashes.
- `tests/output/`, language build directories, package archives, and Lambda zip
  files are generated and must stay untracked.
- Keep `.github/workflows/ci.yml` compatible with local `act` execution; `.actrc`
  selects an Ubuntu-compatible x86_64 runner image.
