# Changelog

## 0.0.5 - 2026-08-29

- Consolidated the Python, Rust, Go, and R renderer histories into one
  repository without submodules.
- Preserved current uncommitted renderer improvements from the source working
  trees while leaving those originals untouched.
- Established `render_examples/` as the canonical shared SBGN-ML input set and
  separated generated test output.
- Added shared behavior documentation and cross-language conformance tests.
- Standardized package and CLI versions at 0.0.5.
- Retained the Rust implementation's pure-Rust rendering backend, embedded
  fonts, Lambda entry point, and Linux musl release configuration.
- Fixed the source-checkout R CLI loading its declared runtime dependencies.
