# Render all SBGN-ML examples to output_render_sbgn_r using base R graphics.

suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(xml2))

arguments <- commandArgs(trailingOnly = FALSE)
file_argument <- arguments[grepl("^--file=", arguments)]
script_dir <- if (length(file_argument) == 0) {
  normalizePath(".", mustWork = TRUE)
} else {
  dirname(normalizePath(sub("^--file=", "", file_argument[1]), mustWork = TRUE))
}
source(file.path(script_dir, "R", "draw_sbgnml.R"))

INPUT_DIR <- file.path(script_dir, "..", "render_examples")
OUTPUT_DIR <- file.path(script_dir, "..", "tests", "output", "r")

dir.create(OUTPUT_DIR, showWarnings = FALSE, recursive = TRUE)

sbgn_files <- list.files(
  INPUT_DIR,
  pattern = "\\.sbgn$",
  full.names = TRUE,
  recursive = TRUE
)
if (length(sbgn_files) == 0) {
  stop("No .sbgn files found in the shared render_examples directory")
}

for (sbgn_file in sbgn_files) {
  base_name <- tools::file_path_sans_ext(basename(sbgn_file))
  png_out <- file.path(OUTPUT_DIR, sprintf("%s_render_sbgn_r.png", base_name))
  draw_sbgnml(sbgn_file, png_out, padding = DEFAULT_PADDING_PX, clone_markers = TRUE)
}
