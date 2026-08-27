\name{draw_sbgnml}
\alias{draw_sbgnml}
\title{Render an SBGN-ML diagram}
\usage{
draw_sbgnml(
  input_path,
  output_path = NULL,
  padding = DEFAULT_PADDING_PX,
  width = NULL,
  height = NULL,
  clone_markers = TRUE,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE,
  show_process_node_labels = FALSE,
  output_format = "png,svg",
  style_config = NULL
)
}
\arguments{
\item{input_path}{Path to an SBGN-ML file.}
\item{output_path}{Optional PNG or SVG output path.}
\item{padding}{Padding around the rendered diagram.}
\item{width}{Optional output width in pixels.}
\item{height}{Optional output height in pixels.}
\item{clone_markers}{Whether clone markers are rendered.}
\item{glyph_colors}{Optional named glyph color vector.}
\item{glyph_color_type}{Whether color keys are labels or IDs.}
\item{auto_contrast_text}{Whether label contrast is adjusted automatically.}
\item{show_process_node_labels}{Whether process-node labels are rendered.}
\item{output_format}{Comma-separated formats used without an output path.}
\item{style_config}{Optional renderer style configuration.}
}
\value{Returns \code{NULL} invisibly and writes the requested image files.}
\description{Parses and renders an SBGN-ML diagram using base R graphics.}
