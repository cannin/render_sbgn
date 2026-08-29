#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

(
  cd "$repository_root/python"
  uv run --with pytest pytest
)

(
  cd "$repository_root/rust"
  cargo fmt --check
  cargo test
)

(
  cd "$repository_root/go"
  unformatted="$(gofmt -l .)"
  if [[ -n "$unformatted" ]]; then
    printf 'Go files require gofmt:\n%s\n' "$unformatted" >&2
    exit 1
  fi
  go test ./...
)

"$repository_root/scripts/test-r.sh"

"$repository_root/scripts/test-conformance.sh"
