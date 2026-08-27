\name{write_render_test_manifest}
\alias{write_render_test_manifest}
\title{Write an SBGN render-test manifest}
\usage{
write_render_test_manifest(
  input_path,
  output_path,
  output_width = NULL,
  output_height = NULL,
  padding = DEFAULT_PADDING_PX,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE,
  style_config = NULL
)
}
\arguments{
\item{input_path}{Path to an SBGN-ML file.}
\item{output_path}{Destination JSON path.}
\item{output_width}{Optional rendered width.}
\item{output_height}{Optional rendered height.}
\item{padding}{Padding around the diagram.}
\item{glyph_colors}{Optional named glyph color vector.}
\item{glyph_color_type}{Whether color keys are labels or IDs.}
\item{auto_contrast_text}{Whether label contrast is adjusted automatically.}
\item{style_config}{Optional renderer style configuration.}
}
\value{Returns \code{NULL} invisibly and writes a JSON manifest.}
\description{Produces a machine-readable manifest of rendered primitives.}
