#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
temporary_directory="$(mktemp -d)"

cleanup() {
  rm -rf -- "$temporary_directory"
}
trap cleanup EXIT

run_r_cli() {
  (
    cd "$repository_root"
    Rscript r/draw_sbgnml.R "$@"
  )
}

cargo build --quiet --manifest-path "$repository_root/rust/Cargo.toml" \
  --bin render_sbgn_rs
(
  cd "$repository_root/go"
  go build -o "$temporary_directory/render_sbgn_go" .
)

assert_equivalent_help() {
  local implementation="$1"
  shift
  local long_help
  local short_help

  long_help="$("$@" --help)"
  short_help="$("$@" -h)"
  if [[ "$long_help" != "$short_help" ]]; then
    printf '%s: -h and --help output differ\n' "$implementation" >&2
    return 1
  fi
}

assert_draw_options() {
  local implementation="$1"
  shift
  local help_text

  help_text="$("$@" --help)"
  for option in \
    -p --padding \
    -f --format \
    -h --help \
    --no-clone-markers \
    --no-auto-contrast-text; do
    if ! grep -Fq -- "$option" <<<"$help_text"; then
      printf '%s help is missing %s\n' "$implementation" "$option" >&2
      return 1
    fi
  done
}

assert_equivalent_help Python \
  uv run --project "$repository_root/python" render_sbgn_py
assert_equivalent_help Rust \
  "$repository_root/rust/target/debug/render_sbgn_rs"
assert_equivalent_help Go "$temporary_directory/render_sbgn_go"
assert_equivalent_help R run_r_cli

assert_equivalent_help "Python draw_sbgnml" \
  uv run --project "$repository_root/python" render_sbgn_py draw_sbgnml
assert_equivalent_help "Rust draw_sbgnml" \
  "$repository_root/rust/target/debug/render_sbgn_rs" draw_sbgnml
assert_equivalent_help "Go draw_sbgnml" \
  "$temporary_directory/render_sbgn_go" draw_sbgnml
assert_equivalent_help "R draw_sbgnml" run_r_cli draw_sbgnml

assert_draw_options Python \
  uv run --project "$repository_root/python" render_sbgn_py draw_sbgnml
assert_draw_options Rust \
  "$repository_root/rust/target/debug/render_sbgn_rs" draw_sbgnml
assert_draw_options Go "$temporary_directory/render_sbgn_go" draw_sbgnml
assert_draw_options R run_r_cli draw_sbgnml

input_path="$repository_root/render_examples/sbgn_all_symbols/af_all_glyphs.sbgn"
common_arguments=(
  draw_sbgnml
  -i "$input_path"
  -p 10
  -f png
  --clone-markers true
  --auto-contrast-text true
  --no-clone-markers
  --no-auto-contrast-text
)

uv run --project "$repository_root/python" render_sbgn_py \
  "${common_arguments[@]}" -o "$temporary_directory/python.png"
"$repository_root/rust/target/debug/render_sbgn_rs" \
  "${common_arguments[@]}" -o "$temporary_directory/rust.png"
"$temporary_directory/render_sbgn_go" \
  "${common_arguments[@]}" -o "$temporary_directory/go.png"
run_r_cli "${common_arguments[@]}" -o "$temporary_directory/r.png"

for implementation in python rust go r; do
  file "$temporary_directory/$implementation.png" | grep -q 'PNG image data'
done

python_help="$(uv run --project "$repository_root/python" render_sbgn_py --help)"
if grep -Eq 'render-examples|--input-dir|--output-dir' <<<"$python_help"; then
  printf 'Python help still exposes removed batch-rendering options\n' >&2
  exit 1
fi

printf 'CLI parity checks passed for Python, Rust, Go, and R.\n'
