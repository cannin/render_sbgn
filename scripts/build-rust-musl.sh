#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
musl_target="${RUST_MUSL_TARGET:-x86_64-unknown-linux-musl}"

rustup target add "$musl_target"
(
  cd "$repository_root/rust"
  cargo build --release --target "$musl_target" --bin render_sbgn_rs
)

printf 'Built %s\n' \
  "$repository_root/rust/target/$musl_target/release/render_sbgn_rs"
