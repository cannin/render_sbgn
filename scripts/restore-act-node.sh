#!/usr/bin/env bash

set -euo pipefail

if [[ -z "${ACT:-}" ]]; then
  exit 0
fi

node_path="$(/usr/bin/find /opt/acttoolcache/node -type f -name node | /usr/bin/head -n 1)"
if [[ -z "$node_path" ]]; then
  printf 'Could not locate the act runner Node executable.\n' >&2
  exit 1
fi

printf '%s\n' "${node_path%/node}" >> "$GITHUB_PATH"
