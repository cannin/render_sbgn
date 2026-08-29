#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

git -C "$repository_root" ls-files --cached --others --exclude-standard -- \
  python rust go r \
  render_examples/sbgn_all_symbols/af_all_glyphs.sbgn \
  render_examples/sbgn_all_symbols/pd_all_glyphs.sbgn \
  scripts/preview-source-hash.sh \
  scripts/render-readme-previews.sh | \
  LC_ALL=C sort | \
  while IFS= read -r source_path; do
    case "$source_path" in
      python/README.md | rust/README.md | go/README.md | r/README.md)
        continue
        ;;
    esac
    printf '%s  %s\n' \
      "$(git -C "$repository_root" hash-object -- "$source_path")" \
      "$source_path"
  done | git -C "$repository_root" hash-object --stdin
