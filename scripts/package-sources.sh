#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_directory="${1:-$repository_root/dist}"
release_ref="${2:-HEAD}"
version="$(awk -F ' = ' '$1 == "version" { gsub(/"/, "", $2); print $2; exit }' "$repository_root/python/pyproject.toml")"

mkdir -p "$output_directory"

git -C "$repository_root" archive \
  --format=tar.gz \
  --prefix="render_sbgn-$version/" \
  --output="$output_directory/render_sbgn-$version-all-source.tar.gz" \
  "$release_ref"

for language in python rust go r; do
  git -C "$repository_root" archive \
    --format=tar.gz \
    --prefix="render_sbgn-$language-$version/" \
    --output="$output_directory/render_sbgn-$language-$version-source.tar.gz" \
    "$release_ref:$language"
done

printf 'Packaged source from %s in %s\n' "$release_ref" "$output_directory"
