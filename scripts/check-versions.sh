#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
expected_version="${1:-0.0.6}"

python_version="$(awk -F ' = ' '$1 == "version" { gsub(/"/, "", $2); print $2; exit }' "$repository_root/python/pyproject.toml")"
rust_version="$(awk -F ' = ' '$1 == "version" { gsub(/"/, "", $2); print $2; exit }' "$repository_root/rust/Cargo.toml")"
r_version="$(awk -F ': ' '$1 == "Version" { print $2; exit }' "$repository_root/r/DESCRIPTION")"
go_version="$(awk -F '"' '/rendererVersion[[:space:]]*=/{ print $2; exit }' "$repository_root/go/main.go")"

for version_entry in \
  "Python:$python_version" \
  "Rust:$rust_version" \
  "Go:$go_version" \
  "R:$r_version"; do
  implementation="${version_entry%%:*}"
  actual_version="${version_entry#*:}"
  if [[ "$actual_version" != "$expected_version" ]]; then
    printf '%s version is %s; expected %s\n' \
      "$implementation" "$actual_version" "$expected_version" >&2
    exit 1
  fi
done

printf 'All implementation versions are %s.\n' "$expected_version"
