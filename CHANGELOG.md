# Changelog

## 0.0.9 - 2026-09-07

- Bundled Liberation Sans with every renderer implementation for deterministic
  access without a host font installation.
- Standardized the fallback order as Liberation Sans, Arial, DejaVu Sans,
  Helvetica, and generic sans-serif.

## 0.0.8 - 2026-09-07

- Exposed the Python renderer and render-manifest entry points as a documented
  package-level library API.

## 0.0.7 - 2026-08-29

- Rendered `AND`, `OR`, and `NOT` logical nodes with circular cores for both
  horizontal and vertical port orientations in all four implementations.
- Preserved correctly oriented port stubs on logical nodes.
- Regenerated the shared AF and PD all-symbol renderer previews.

## 0.0.6 - 2026-08-29

- Aligned the Python, Rust, Go, and R command-line flags and help behavior.
- Added shared CLI parity tests and removed Python's batch-only CLI options.
- Migrated the R package documentation and namespace generation to roxygen2.
- Added CI and release gates that block stale multi-renderer README previews.

## 0.0.5 - 2026-08-29

- Consolidated the Python, Rust, Go, and R renderer histories into one
  repository without submodules.
- Preserved current uncommitted renderer improvements from the source working
  trees while leaving those originals untouched.
- Established `render_examples/` as the canonical shared SBGN-ML input set and
  separated generated test output.
- Added shared behavior documentation and cross-language conformance tests.
- Added an Ubuntu GitHub Actions workflow, verified locally with `act`, for all
  renderers and the Rust musl release.
- Added coordinated release automation for tagged source archives, checked
  Python and R packages, cross-platform Go and Rust executables, and checksums.
- Standardized package and CLI versions at 0.0.5.
- Retained the Rust implementation's pure-Rust rendering backend, embedded
  fonts, Lambda entry point, and Linux musl release configuration.
- Fixed the source-checkout R CLI loading its declared runtime dependencies.
