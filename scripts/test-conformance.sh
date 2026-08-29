#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

uv run --project "$repository_root/python" \
  python "$repository_root/tests/conformance.py" "$@"
