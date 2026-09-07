#!/usr/bin/env Rscript

# PURPOSE ----
# Run the renderer directly from a source checkout.

# LOAD DATA ----

suppressPackageStartupMessages(library(jsonlite))
suppressPackageStartupMessages(library(showtext))
suppressPackageStartupMessages(library(sysfonts))
suppressPackageStartupMessages(library(xml2))

arguments <- commandArgs(trailingOnly = FALSE)
file_argument <- arguments[grepl("^--file=", arguments)]
script_dir <- if (length(file_argument) == 0) {
  normalizePath(".", mustWork = TRUE)
} else {
  dirname(normalizePath(sub("^--file=", "", file_argument[1]), mustWork = TRUE))
}
options(renderSbgnR.source_root = script_dir)
source(file.path(script_dir, "R", "draw_sbgnml.R"))

# ANALYSIS ----

main()
