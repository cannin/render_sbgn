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

Validate coordinated package versions and build release inputs with:

```bash
./scripts/check-versions.sh X.Y.Z
./scripts/package-sources.sh dist HEAD
(cd python && uv build --wheel --out-dir ../dist)
./scripts/test-r.sh
make -C go
```

The default Go `make` target must remain `all: test release current`, in that
order. It creates current-system `go/dist/render_sbgn_go` plus Linux, macOS, and
Windows release binaries. Linux and Windows target amd64; macOS targets arm64.

## Release process

`.github/workflows/release.yml` is the authoritative release builder. A
`vX.Y.Z` tag builds and publishes:

- complete and per-language tagged source archives;
- a Python wheel;
- an R source package only after `R CMD check` succeeds;
- Go binaries for Ubuntu Linux amd64, macOS arm64, and Windows amd64;
- a Rust static-musl Ubuntu Linux amd64 binary, a macOS arm64 binary, and a
  Windows amd64 binary;
- `SHA256SUMS.txt` covering every uploaded artifact.

Before tagging, run `./scripts/test-all.sh`, the local `act` command above, and
`./scripts/check-versions.sh X.Y.Z`. Commit and push all release changes, then
create the coordinated tags at the same commit:

```bash
git tag -a vX.Y.Z -m "render_sbgn X.Y.Z"
git tag -a go/vX.Y.Z -m "render_sbgn Go X.Y.Z"
git push origin main
git push origin vX.Y.Z go/vX.Y.Z
```

The `vX.Y.Z` tag triggers release publication. The `go/vX.Y.Z` tag supplies the
version required for the module rooted in `go/`. Never publish artifacts from
an uncommitted working tree or move a tag that has already been published.

## Editing constraints

- Preserve the native package layout and independent installation path of each
  implementation.
- Avoid renderer-algorithm rewrites during repository maintenance.
- When common behavior changes, update the shared behavior section in
  `README.md` and test all four renderers.
- Keep package versions coordinated. Python, Rust, and R metadata and exposed
  CLI versions must agree. Go releases use subdirectory tags such as
  `go/vX.Y.Z`; do not add a version field to `go.mod`.
- Rust release artifacts must target musl and remain independent of host C
  libraries. Keep fonts embedded in the binary.
- Use ASCII source, format with Black/flake8 where configured for Python,
  `cargo fmt` for Rust, `gofmt` for Go, and `lintr` for R.

## Repository pitfalls

- The four imported histories are intentionally unrelated and joined by merge
  commits. Do not flatten or rewrite them.
- Some SBGN examples intentionally exercise uncommon glyphs; a successful
  parse/render is still expected unless `README.md` says otherwise.
- PNG bytes can vary by backend even when the image is equivalent. Conformance
  checks compare observable image properties and manifests rather than raw PNG
  hashes.
- `tests/output/`, language build directories, package archives, and Lambda zip
  files are generated and must stay untracked.
- Keep `.github/workflows/ci.yml` compatible with local `act` execution; `.actrc`
  selects an Ubuntu-compatible x86_64 runner image.
- Language README-only changes must not trigger CI. Keep the ordered negative
  `README.md` patterns after the language-directory include patterns.
- Release artifacts must be built from the tagged commit. Keep artifact names
  platform- and architecture-specific and update the release workflow, root
  README, and language README together when the distribution set changes.
