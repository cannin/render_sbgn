# Changelog

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
