#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_directory="${RENDER_PREVIEW_OUTPUT_DIR:-$repository_root/docs/images}"
temporary_directory="$(mktemp -d)"
preview_font="$repository_root/rust/assets/LiberationSans-Regular.ttf"
preview_source_hash="$("$repository_root/scripts/preview-source-hash.sh")"

cleanup() {
  rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

mkdir -p "$output_directory"

if command -v magick >/dev/null 2>&1; then
  montage_command=(magick montage)
  convert_command=(magick)
elif command -v montage >/dev/null 2>&1 && command -v convert >/dev/null 2>&1; then
  montage_command=(montage)
  convert_command=(convert)
else
  printf 'ImageMagick is required to build README previews.\n' >&2
  exit 1
fi

for diagram in af_all_glyphs pd_all_glyphs; do
  input_path="$repository_root/render_examples/sbgn_all_symbols/$diagram.sbgn"

  uv run --project "$repository_root/python" render_sbgn_py draw_sbgnml \
    --input-path "$input_path" \
    --output-path "$temporary_directory/$diagram-python.png"

  cargo run --quiet --manifest-path "$repository_root/rust/Cargo.toml" \
    --bin render_sbgn_rs -- draw_sbgnml \
    --input-path "$input_path" \
    --output-path "$temporary_directory/$diagram-rust.png"

  (
    cd "$repository_root/go"
    go run . draw_sbgnml \
      --input-path "$input_path" \
      --output-path "$temporary_directory/$diagram-go.png"
  )

  (
    cd "$repository_root"
    Rscript r/draw_sbgnml.R \
      --input-path "$input_path" \
      --output-path "$temporary_directory/$diagram-r.png"
  )

  "${montage_command[@]}" \
    -font "$preview_font" -pointsize 28 -fill '#24292f' -background white \
    -label 'Python' "$temporary_directory/$diagram-python.png" \
    -label 'Rust' "$temporary_directory/$diagram-rust.png" \
    -label 'Go' "$temporary_directory/$diagram-go.png" \
    -label 'R' "$temporary_directory/$diagram-r.png" \
    -tile 2x2 -geometry '800x540+24+24' miff:- | \
    "${convert_command[@]}" miff:- -depth 8 -strip png:- | \
    "${convert_command[@]}" png:- \
      -set comment "render_sbgn-preview-source=$preview_source_hash" \
      "$output_directory/${diagram}_renderers.png"
done

printf 'Updated renderer previews in %s\n' "$output_directory"
