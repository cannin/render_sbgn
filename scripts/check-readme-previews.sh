#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
preview_directory="$repository_root/docs/images"
temporary_directory="$(mktemp -d)"
generated_directory="$temporary_directory/generated"
expected_source_hash="$("$repository_root/scripts/preview-source-hash.sh")"
# The source hash is the strict stale-content gate. RMSE only accommodates
# platform-specific font rasterization while validating a fresh rerender.
maximum_normalized_rmse="0.04"

cleanup() {
  rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

preview_names=(
  af_all_glyphs_renderers.png
  pd_all_glyphs_renderers.png
)

if command -v magick >/dev/null 2>&1; then
  compare_command=(magick compare)
  identify_command=(magick identify)
elif command -v compare >/dev/null 2>&1; then
  compare_command=(compare)
  identify_command=(identify)
else
  printf 'ImageMagick is required to verify README previews.\n' >&2
  exit 1
fi

for preview_name in "${preview_names[@]}"; do
  preview_path="$preview_directory/$preview_name"
  if [[ ! -f "$preview_path" ]]; then
    printf 'Missing README preview: %s\n' "$preview_path" >&2
    exit 1
  fi
  cp "$preview_path" "$temporary_directory/$preview_name"

  stored_source_hash="$(
    "${identify_command[@]}" -format '%[comment]' "$preview_path" | \
      sed -n 's/^render_sbgn-preview-source=//p'
  )"
  if [[ "$stored_source_hash" != "$expected_source_hash" ]]; then
    printf 'Stale README preview source hash: docs/images/%s\n' \
      "$preview_name" >&2
    exit 1
  fi
done

mkdir -p "$generated_directory"
RENDER_PREVIEW_OUTPUT_DIR="$generated_directory" \
  "$repository_root/scripts/render-readme-previews.sh"

stale=0
for preview_name in "${preview_names[@]}"; do
  metric_output="$(
    "${compare_command[@]}" -metric RMSE \
      "$temporary_directory/$preview_name" \
      "$generated_directory/$preview_name" null: 2>&1 || true
  )"
  normalized_rmse="$(
    printf '%s\n' "$metric_output" | \
      sed -n 's/.*(\([^)]*\)).*/\1/p'
  )"
  if [[ -z "$normalized_rmse" ]] || ! awk \
    -v metric="$normalized_rmse" \
    -v maximum="$maximum_normalized_rmse" \
    'BEGIN { exit !(metric <= maximum) }'; then
    printf 'Stale README preview: docs/images/%s\n' "$preview_name" >&2
    stale=1
  else
    printf '%s normalized RMSE: %s\n' "$preview_name" "$normalized_rmse"
  fi
done

if ((stale)); then
  printf 'Commit the regenerated README previews before publishing.\n' >&2
  exit 1
fi

printf 'README renderer previews are current.\n'
