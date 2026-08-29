#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
output_directory="$repository_root/docs/images"
temporary_directory="$(mktemp -d)"

cleanup() {
  rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

mkdir -p "$output_directory"

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

  magick montage \
    -font Arial -pointsize 28 -fill '#24292f' -background white \
    -label 'Python' "$temporary_directory/$diagram-python.png" \
    -label 'Rust' "$temporary_directory/$diagram-rust.png" \
    -label 'Go' "$temporary_directory/$diagram-go.png" \
    -label 'R' "$temporary_directory/$diagram-r.png" \
    -tile 2x2 -geometry '800x540+24+24' miff:- | \
    magick miff:- -depth 8 -strip "$output_directory/${diagram}_renderers.png"
done

printf 'Updated renderer previews in %s\n' "$output_directory"
