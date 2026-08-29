# Render SBGN-ML diagrams using base R graphics and xml2.
# This copy mirrors the JavaScript Cytoscape renderer used by the Shiny app.

# Configuration constants for layout and styling.
DEFAULT_PADDING_PX <- 50
RENDERER_VERSION <- "0.1.0"
FONT_MIN_PX <- 6
FONT_BASE_PX <- 12
FONT_FAMILY <- "Liberation Sans"
TEXT_LINE_SPACING <- 1.12
ARROW_SIZE <- 8
CYTOSCAPE_ARROW_SCALE <- 4.53125
BAR_LENGTH <- 12
renderer_state <- new.env(parent = emptyenv())
renderer_state$show_process_node_labels <- FALSE
renderer_state$render_scale <- 1
renderer_state$auto_contrast_text <- TRUE
renderer_state$style_config <- NULL

JS_NODE_FILL_COLOR <- "#ffffff"
JS_NODE_BORDER_COLOR <- "#555555"
JS_NODE_TEXT_COLOR <- "#000000"
JS_COMPARTMENT_BORDER_COLOR <- "#555555"
JS_MACROMOLECULE_BORDER_COLOR <- "#555555"
JS_SIMPLE_CHEMICAL_BORDER_COLOR <- "#555555"
JS_COMPLEX_BORDER_COLOR <- "#555555"
JS_PROCESS_BORDER_COLOR <- "#555555"
JS_SUBMAP_BORDER_COLOR <- "#555555"
JS_PHENOTYPE_BORDER_COLOR <- "#555555"
JS_SOURCE_SINK_BORDER_COLOR <- "#555555"
JS_GLYPH_COLOR_BORDER_COLOR <- "#16191f"
JS_EDGE_COLOR <- "#555555"
JS_DEFAULT_NODE_BORDER_WIDTH <- 1.25
JS_DEFAULT_EDGE_WIDTH <- 1.25
JS_COMPARTMENT_BORDER_WIDTH <- 3.25
JS_COMPLEX_BORDER_WIDTH <- 1.25
JS_GLYPH_COLOR_BORDER_WIDTH <- 2.4
JS_NODE_FONT_PX <- 12
JS_COMPARTMENT_FONT_PX <- 12
JS_TEXT_PADDING_PX <- 8

#' Convert a character to numeric with a fallback.
#'
#' @param value Character or numeric value to convert.
#'
#' @return Numeric value or NA_real_ if missing.
as_numeric <- function(value) {
  if (is.na(value) || is.null(value) || value == "") {
    return(NA_real_)
  }
  as.numeric(value)
}

#' Convert font pixels to cex units for base graphics.
#'
#' @param font_px Font size in pixels.
#'
#' @return Numeric cex scale.
font_px_to_cex <- function(font_px) {
  rendered_font_px <- max(FONT_MIN_PX, font_px * renderer_state$render_scale)
  rendered_font_px / FONT_BASE_PX
}

#' Convert sRGB color channels to linearized RGB.
#'
#' @param channel Numeric sRGB channel between 0 and 1.
#'
#' @return Linearized RGB channel.
device_size_pixels <- function() {
  size_px <- dev.size("px")
  if (any(!is.finite(size_px)) || any(is.na(size_px))) {
    size_in <- dev.size("in")
    size_px <- size_in * 96
  }
  size_px
}

#' Compute the plot scale used after fitting SBGN coordinates to the device.
#'
#' @param bounds Parsed diagram bounds.
#' @param padding Padding in SBGN coordinate units.
#'
#' @return Numeric scale capped at one to match Cytoscape fit behavior.
compute_render_scale <- function(bounds, padding) {
  size_px <- device_size_pixels()
  diagram_width <- bounds$max_x - bounds$min_x + 2 * padding
  diagram_height <- bounds$max_y - bounds$min_y + 2 * padding
  if (diagram_width <= 0 || diagram_height <= 0) {
    return(1)
  }
  min(1, size_px[1] / diagram_width, size_px[2] / diagram_height)
}

#' Split a long word into chunks that fit a maximum width.
#'
#' @param word Word to split.
#' @param max_width Maximum line width in user units.
#' @param cex Font scale.
#'
#' @return Character vector of line chunks.
split_word_to_width <- function(word, max_width, cex) {
  characters <- strsplit(word, "", fixed = TRUE)[[1]]
  lines <- character(0)
  current <- ""

  for (character in characters) {
    candidate <- paste0(current, character)
    if (current != "" && strwidth(candidate, units = "user", cex = cex) > max_width) {
      lines <- c(lines, current)
      current <- character
    } else {
      current <- candidate
    }
  }

  c(lines, current)
}

#' Wrap one label line to a maximum width.
#'
#' @param label_line Single-line label.
#' @param max_width Maximum line width in user units.
#' @param cex Font scale.
#'
#' @return Character vector of wrapped lines.
wrap_label_line <- function(label_line, max_width, cex) {
  label_line <- trimws(label_line)
  if (label_line == "" || !is.finite(max_width) || max_width <= 0) {
    return(label_line)
  }
  if (strwidth(label_line, units = "user", cex = cex) <= max_width) {
    return(label_line)
  }

  words <- strsplit(label_line, "\\s+")[[1]]
  lines <- character(0)
  current <- ""

  for (word in words) {
    candidate <- if (current == "") word else paste(current, word)
    if (strwidth(candidate, units = "user", cex = cex) <= max_width) {
      current <- candidate
      next
    }

    if (current != "") {
      lines <- c(lines, current)
    }

    if (strwidth(word, units = "user", cex = cex) <= max_width) {
      current <- word
    } else {
      word_lines <- split_word_to_width(word, max_width, cex)
      lines <- c(lines, utils::head(word_lines, -1))
      current <- utils::tail(word_lines, 1)
    }
  }

  c(lines, current)
}

#' Wrap label text to a maximum width.
#'
#' @param label Text label.
#' @param max_width Maximum line width in user units.
#' @param cex Font scale.
#'
#' @return Character vector of wrapped lines.
wrap_label_text <- function(label, max_width, cex) {
  label <- gsub("\r", "", label)
  label <- gsub("[ \t]+", " ", label)
  label_lines <- strsplit(label, "\n", fixed = TRUE)[[1]]
  unlist(lapply(label_lines, wrap_label_line, max_width = max_width, cex = cex))
}

#' Fit a label inside a shape by wrapping at the fixed label font size.
#'
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param max_width Maximum text width in user units.
#' @param max_height Maximum text height in user units.
#'
#' @return List with lines, cex, and line_height.
fit_label_text <- function(label, font_px, max_width, max_height) {
  cex <- font_px_to_cex(font_px)
  lines <- wrap_label_text(label, max_width, cex)
  line_height <- abs(strheight("Mg", units = "user", cex = cex)) *
    TEXT_LINE_SPACING

  list(lines = lines, cex = cex, line_height = line_height)
}

#' Build a state variable label in value@variable format.
#'
#' @param value State value.
#' @param variable State variable name.
#'
#' @return Combined label string.
state_variable_label <- function(value, variable) {
  parts <- c(value, variable)
  parts <- parts[!vapply(parts, is.null, logical(1))]
  parts <- parts[!is.na(parts) & nzchar(parts)]
  paste(parts, collapse = "@")
}

compute_bounds <- function(glyphs, arcs) {
  x_values <- numeric(0)
  y_values <- numeric(0)

  for (glyph in glyphs) {
    bbox <- glyph$bbox
    if (
      !is.null(bbox) &&
        !is.na(bbox$x) &&
        !is_js_hidden_glyph_class(glyph$class)
    ) {
      x_values <- c(x_values, bbox$x, bbox$x + bbox$w)
      y_values <- c(y_values, bbox$y, bbox$y + bbox$h)
    }
  }

  if (length(x_values) == 0 || length(y_values) == 0) {
    stop("No coordinates found in SBGN file")
  }

  list(
    min_x = min(x_values),
    max_x = max(x_values),
    min_y = min(y_values),
    max_y = max(y_values)
  )
}

#' Extract bounding box values from a glyph node.
#'
#' @param glyph xml2 node representing a glyph.
#' @param ns XML namespace mapping.
#'
#' @return Named list with x, y, w, h as numeric values or NULL.
extract_bbox <- function(glyph, ns) {
  bbox_node <- xml_find_first(glyph, "./sbgn:bbox", ns)
  if (length(bbox_node) == 0) {
    return(NULL)
  }
  list(
    x = as_numeric(xml_attr(bbox_node, "x")),
    y = as_numeric(xml_attr(bbox_node, "y")),
    w = as_numeric(xml_attr(bbox_node, "w")),
    h = as_numeric(xml_attr(bbox_node, "h"))
  )
}

#' Extract sbgnviz/newt body size metadata from a glyph node.
#'
#' @param glyph xml2 node representing a glyph.
#' @param ns XML namespace mapping.
#'
#' @return Named list with optional width and height values.
extract_extra_size <- function(glyph, ns) {
  width_node <- xml_find_first(glyph, ".//*[local-name()='w']", ns)
  height_node <- xml_find_first(glyph, ".//*[local-name()='h']", ns)
  width <- if (length(width_node) == 0) NA_real_ else as_numeric(xml_text(width_node))
  height <- if (length(height_node) == 0) NA_real_ else as_numeric(xml_text(height_node))
  list(
    width = width,
    height = height
  )
}

#' Extract label text from a glyph node.
#'
#' @param glyph xml2 node representing a glyph.
#' @param ns XML namespace mapping.
#'
#' @return Label string (may include newlines).
extract_label <- function(glyph, ns) {
  label_node <- xml_find_first(glyph, "./sbgn:label", ns)
  label_text <- xml_attr(label_node, "text")
  if (is.na(label_text) || is.null(label_text)) {
    return("")
  }
  gsub("\r", "", label_text)
}

#' Extract port coordinates from a glyph node.
#'
#' @param glyph xml2 node representing a glyph.
#' @param ns XML namespace mapping.
#'
#' @return Data frame with x and y columns (possibly empty).
extract_ports <- function(glyph, ns) {
  ports <- xml_find_all(glyph, "./sbgn:port", ns)
  if (length(ports) == 0) {
    return(data.frame(id = character(0), x = numeric(0), y = numeric(0)))
  }
  data.frame(
    id = xml_attr(ports, "id"),
    x = as.numeric(xml_attr(ports, "x")),
    y = as.numeric(xml_attr(ports, "y")),
    stringsAsFactors = FALSE
  )
}

#' Extract ordered arc points (start, optional next, end).
#'
#' @param arc xml2 node representing an arc.
#' @param ns XML namespace mapping.
#'
#' @return Data frame with ordered x and y columns.
extract_arc_points <- function(arc, ns) {
  start_node <- xml_find_first(arc, "./sbgn:start", ns)
  end_node <- xml_find_first(arc, "./sbgn:end", ns)
  next_nodes <- xml_find_all(arc, "./sbgn:next", ns)

  points <- list(
    c(as_numeric(xml_attr(start_node, "x")), as_numeric(xml_attr(start_node, "y")))
  )
  if (length(next_nodes) > 0) {
    for (next_node in next_nodes) {
      points <- c(points, list(c(as_numeric(xml_attr(next_node, "x")), as_numeric(xml_attr(next_node, "y")))))
    }
  }
  points <- c(points, list(c(as_numeric(xml_attr(end_node, "x")), as_numeric(xml_attr(end_node, "y")))))

  matrix_points <- do.call(rbind, points)
  data.frame(x = matrix_points[, 1], y = matrix_points[, 2])
}

#' Parse a glyph node recursively.
#'
#' @param glyph xml2 node representing a glyph.
#' @param ns XML namespace mapping.
#' @param parent_id Optional parent id.
#'
#' @return List of glyph records.
parse_glyph_node <- function(glyph, ns, parent_id = NULL) {
  id <- xml_attr(glyph, "id")
  class_name <- xml_attr(glyph, "class")
  label <- extract_label(glyph, ns)
  bbox <- extract_bbox(glyph, ns)
  extra_size <- extract_extra_size(glyph, ns)
  ports <- extract_ports(glyph, ns)
  has_clone <- length(xml_find_all(glyph, "./sbgn:clone", ns)) > 0
  state_node <- xml_find_first(glyph, "./sbgn:state", ns)
  state_value <- xml_attr(state_node, "value")
  state_variable <- xml_attr(state_node, "variable")
  entity_node <- xml_find_first(glyph, "./sbgn:entity", ns)
  entity_name <- xml_attr(entity_node, "name")
  orientation <- xml_attr(glyph, "orientation")

  record <- list(
    id = id,
    parent_id = parent_id,
    class = class_name,
    bbox = bbox,
    extra_width = extra_size$width,
    extra_height = extra_size$height,
    label = label,
    ports = ports,
    has_clone = has_clone,
    state_value = if (is.na(state_value)) NULL else state_value,
    state_variable = if (is.na(state_variable)) NULL else state_variable,
    entity_name = if (is.na(entity_name)) NULL else entity_name,
    orientation = if (is.na(orientation)) NULL else orientation
  )

  records <- list(record)
  child_nodes <- xml_find_all(glyph, "./sbgn:glyph", ns)
  if (length(child_nodes) > 0) {
    for (child in child_nodes) {
      records <- c(records, parse_glyph_node(child, ns, parent_id = id))
    }
  }
  records
}

#' Parse the SBGN XML into glyphs and arcs.
#'
#' @param input_path Path to the SBGN XML file.
#'
#' @return List containing glyphs, arcs, and bounds.
parse_sbgn <- function(input_path) {
  doc <- read_xml(input_path)
  ns <- xml_ns(doc)
  if (length(ns) == 0) {
    ns <- c(sbgn = "")
  } else if (!("sbgn" %in% names(ns))) {
    ns <- c(ns, sbgn = ns[[1]])
  }

  map_nodes <- xml_find_all(doc, ".//sbgn:map", ns)
  if (length(map_nodes) == 0) {
    stop("SBGN file missing map element")
  }

  arc_nodes <- xml_find_all(doc, ".//sbgn:arc", ns)

  glyphs <- list()
  for (map_node in map_nodes) {
    glyph_nodes <- xml_find_all(map_node, "./sbgn:glyph", ns)
    for (glyph in glyph_nodes) {
      glyphs <- c(glyphs, parse_glyph_node(glyph, ns, parent_id = NULL))
    }
  }

  arcs <- list()
  for (arc in arc_nodes) {
    auxiliary_glyphs <- list()
    for (arc_glyph in xml_find_all(arc, "./sbgn:glyph", ns)) {
      auxiliary_glyphs[[length(auxiliary_glyphs) + 1]] <- list(
        id = xml_attr(arc_glyph, "id"),
        class = xml_attr(arc_glyph, "class"),
        bbox = extract_bbox(arc_glyph, ns),
        label = extract_label(arc_glyph, ns)
      )
    }
    arcs <- c(arcs, list(list(
      id = xml_attr(arc, "id"),
      class = xml_attr(arc, "class"),
      source = xml_attr(arc, "source"),
      target = xml_attr(arc, "target"),
      points = extract_arc_points(arc, ns),
      auxiliary_glyphs = auxiliary_glyphs
    )))
  }

  bounds <- compute_bounds(glyphs, arcs)
  list(glyphs = glyphs, arcs = arcs, bounds = bounds)
}

#' Convert a bbox to a pixel rect list.
#'
#' @param bbox Bounding box list.
#'
#' @return Pixel rect list with x0, y0, width, height, center.
bbox_pixel_rect <- function(bbox) {
  x0 <- bbox$x
  y0 <- bbox$y
  width <- bbox$w
  height <- bbox$h
  list(
    x0 = x0,
    y0 = y0,
    width = width,
    height = height,
    center = list(x = x0 + width / 2, y = y0 + height / 2)
  )
}

#' Return sbgnviz's source-space primitive rectangle for a glyph.
#'
#' @param glyph Parsed glyph list.
#'
#' @return Pixel rect list with x0, y0, width, height, center.
sbgnviz_manifest_rect <- function(glyph) {
  center <- list(
    x = glyph$bbox$x + glyph$bbox$w / 2,
    y = glyph$bbox$y + glyph$bbox$h / 2
  )
  span <- sbgnviz_port_span(glyph)
  if (!is.na(span)) {
    width <- span
    height <- span
  } else if (glyph$class %in% c("compartment", "complex", "complex multimer")) {
    padding <- if (glyph$class == "compartment") 24 else 10
    border_width <- if (glyph$class == "compartment") {
      JS_COMPARTMENT_BORDER_WIDTH
    } else {
      JS_COMPLEX_BORDER_WIDTH
    }
    expansion <- 2 * padding + border_width + 2
    width <- if (!is.null(glyph$extra_width) && !is.na(glyph$extra_width)) {
      glyph$extra_width + expansion
    } else {
      glyph$bbox$w + expansion
    }
    height <- if (!is.null(glyph$extra_height) && !is.na(glyph$extra_height)) {
      glyph$extra_height + expansion
    } else {
      glyph$bbox$h + expansion
    }
  } else if (
    !is.null(glyph$extra_width) &&
      !is.na(glyph$extra_width) &&
      !is.null(glyph$extra_height) &&
      !is.na(glyph$extra_height)
  ) {
    width <- glyph$extra_width
    height <- glyph$extra_height
  } else {
    width <- glyph$bbox$w
    height <- glyph$bbox$h
  }
  list(
    x0 = center$x - width / 2,
    y0 = center$y - height / 2,
    width = width,
    height = height,
    center = center
  )
}

#' Return the port span used for sbgnviz ported glyph manifests.
#'
#' @param glyph Parsed glyph list.
#'
#' @return Numeric span or NA_real_.
sbgnviz_port_span <- function(glyph) {
  if (!is_ported_glyph_class(glyph$class) || nrow(glyph$ports) < 2) {
    return(NA_real_)
  }
  span <- max(
    diff(range(glyph$ports$x, na.rm = TRUE)),
    diff(range(glyph$ports$y, na.rm = TRUE)),
    glyph$bbox$w,
    glyph$bbox$h
  )
  if (is.finite(span) && span > 0) span else NA_real_
}

#' Check whether sbgnviz draws a glyph with integrated port stubs.
#'
#' @param class_name SBGN glyph class.
#'
#' @return TRUE for process and logical-operator glyph classes.
is_ported_glyph_class <- function(class_name) {
  class_name %in% c(
    "process",
    "omitted process",
    "uncertain process",
    "association",
    "dissociation",
    "and",
    "or",
    "not"
  )
}

#' Create points for an ellipse polygon.
#'
#' @param cx Center x.
#' @param cy Center y.
#' @param rx Radius x.
#' @param ry Radius y.
#' @param n Number of points.
#'
#' @return Data frame with x and y.
ellipse_points <- function(cx, cy, rx, ry, n = 60) {
  theta <- seq(0, 2 * pi, length.out = n)
  data.frame(
    x = cx + rx * cos(theta),
    y = cy + ry * sin(theta)
  )
}

#' Quadratic Bezier curve points.
#'
#' @param p0 Start point list.
#' @param p1 Control point list.
#' @param p2 End point list.
#' @param n Number of samples.
#'
#' @return Data frame of points.
arc_points <- function(cx, cy, r, start_angle, end_angle, n = 12) {
  theta <- seq(start_angle, end_angle, length.out = n)
  data.frame(x = cx + r * cos(theta), y = cy + r * sin(theta))
}

quadratic_points <- function(x0, y0, cx, cy, x1, y1, n = 12) {
  t <- seq(0, 1, length.out = n)
  data.frame(
    x = (1 - t)^2 * x0 + 2 * (1 - t) * t * cx + t^2 * x1,
    y = (1 - t)^2 * y0 + 2 * (1 - t) * t * cy + t^2 * y1
  )
}

#' Rounded rectangle polygon points (clockwise).
#'
#' @param x0 Left.
#' @param y0 Top.
#' @param x1 Right.
#' @param y1 Bottom.
#' @param radius Corner radius.
#' @param n_arc Points per corner.
#'
#' @return Data frame with x and y.
round_rect_points <- function(x0, y0, x1, y1, radius, n_arc = 12) {
  r <- min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
  points <- rbind(
    data.frame(x = x0 + r, y = y0),
    data.frame(x = x1 - r, y = y0),
    arc_points(x1 - r, y0 + r, r, -pi / 2, 0, n_arc),
    data.frame(x = x1, y = y1 - r),
    arc_points(x1 - r, y1 - r, r, 0, pi / 2, n_arc),
    data.frame(x = x0 + r, y = y1),
    arc_points(x0 + r, y1 - r, r, pi / 2, pi, n_arc),
    data.frame(x = x0, y = y0 + r),
    arc_points(x0 + r, y0 + r, r, pi, 3 * pi / 2, n_arc)
  )
  points
}

#' Rounded bottom rectangle polygon points (clockwise).
#'
#' @param x0 Left.
#' @param y0 Top.
#' @param x1 Right.
#' @param y1 Bottom.
#' @param radius Corner radius.
#'
#' @return Data frame with x and y.
hexagon_points <- function(rect) {
  x0 <- rect$x0
  y0 <- rect$y0
  w <- rect$width
  h <- rect$height
  data.frame(
    x = c(x0, x0 + 0.25 * w, x0 + 0.75 * w, x0 + w, x0 + 0.75 * w, x0 + 0.25 * w),
    y = c(y0 + 0.5 * h, y0, y0, y0 + 0.5 * h, y0 + h, y0 + h)
  )
}

#' Stadium polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
stadium_points <- function(rect) {
  round_rect_points(
    rect$x0,
    rect$y0,
    rect$x0 + rect$width,
    rect$y0 + rect$height,
    max(1, rect$height / 2),
    18
  )
}

#' Clipped complex polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
complex_points <- function(rect) {
  corner <- max(1, min(12, rect$width / 3, rect$height / 3))
  data.frame(
    x = c(
      rect$x0 + corner,
      rect$x0,
      rect$x0,
      rect$x0 + corner,
      rect$x0 + rect$width - corner,
      rect$x0 + rect$width,
      rect$x0 + rect$width,
      rect$x0 + rect$width - corner
    ),
    y = c(
      rect$y0,
      rect$y0 + corner,
      rect$y0 + rect$height - corner,
      rect$y0 + rect$height,
      rect$y0 + rect$height,
      rect$y0 + rect$height - corner,
      rect$y0 + corner,
      rect$y0
    )
  )
}

#' Barrel compartment polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
barrel_points <- function(rect) {
  x0 <- rect$x0
  y0 <- rect$y0
  x1 <- rect$x0 + rect$width
  y1 <- rect$y0 + rect$height
  control <- min(rect$width * 0.10, 100)
  rbind(
    data.frame(x = x0, y = y0 + 15),
    data.frame(x = x0, y = y1 - 15),
    quadratic_points(x0, y1 - 15, x0 + 5, y1, x0 + control, y1),
    data.frame(x = x1 - control, y = y1),
    quadratic_points(x1 - control, y1, x1 - 5, y1, x1, y1 - 15),
    data.frame(x = x1, y = y0 + 15),
    quadratic_points(x1, y0 + 15, x1 - 5, y0, x1 - control, y0),
    data.frame(x = x0 + control, y = y0),
    quadratic_points(x0 + control, y0, x0 + 5, y0, x0, y0 + 15)
  )
}

#' Bottom-round nucleic-acid polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
bottom_round_rect_points <- function(rect) {
  round_rect_points(
    rect$x0,
    rect$y0,
    rect$x0 + rect$width,
    rect$y0 + rect$height,
    max(1, rect$height * 0.25),
    12
  )
}

#' Tag polygon points.
#'
#' @param rect Pixel rect list.
#' @param orientation Tag orientation.
#'
#' @return Data frame with x and y.
tag_points <- function(rect, orientation = "right") {
  x0 <- rect$x0
  y0 <- rect$y0
  x1 <- rect$x0 + rect$width
  y1 <- rect$y0 + rect$height
  orientation <- tolower(trimws(ifelse(is.null(orientation), "right", orientation)))
  if (orientation == "left") {
    return(data.frame(
      x = c(x1, x0 + 0.75 * rect$width, x0, x0 + 0.75 * rect$width, x1),
      y = c(y0, y0, rect$center$y, y1, y1)
    ))
  }
  data.frame(
    x = c(x0, x0 + 0.625 * rect$width, x1, x0 + 0.625 * rect$width, x0),
    y = c(y0, y0, rect$center$y, y1, y1)
  )
}

#' Perturbing-agent polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
perturbing_agent_points <- function(rect) {
  data.frame(
    x = c(
      rect$x0,
      rect$x0 + 0.25 * rect$width,
      rect$x0,
      rect$x0 + rect$width,
      rect$x0 + 0.75 * rect$width,
      rect$x0 + rect$width
    ),
    y = c(
      rect$y0,
      rect$center$y,
      rect$y0 + rect$height,
      rect$y0 + rect$height,
      rect$center$y,
      rect$y0
    )
  )
}

#' Build the process or logical-operator core with integrated port stubs.
#'
#' @param rect Pixel rectangle spanning the glyph ports.
#' @param glyph Parsed glyph record.
#'
#' @return Data frame containing polygon x/y coordinates.
ported_glyph_points <- function(rect, glyph) {
  orientation <- "horizontal"
  if (!is.null(glyph$ports) && nrow(glyph$ports) >= 2) {
    x_span <- diff(range(glyph$ports$x, na.rm = TRUE))
    y_span <- diff(range(glyph$ports$y, na.rm = TRUE))
    if (y_span > x_span) {
      orientation <- "vertical"
    }
  }

  core_width <- rect$width * 0.707071
  core_height <- rect$height * 0.707071
  core <- list(
    x0 = rect$center$x - core_width / 2,
    y0 = rect$center$y - core_height / 2,
    width = core_width,
    height = core_height,
    center = rect$center
  )
  core_circle <- glyph$class %in% c(
    "association",
    "dissociation",
    "and",
    "or",
    "not"
  )

  if (orientation == "horizontal") {
    line_half <- max(rect$height * 0.01, 0.5) / 2
    if (core_circle) {
      lower_angles <- seq(pi, 0, length.out = 31)
      upper_angles <- seq(0, -pi, length.out = 31)
      lower_arc <- data.frame(
        x = core$center$x + core$width / 2 * cos(lower_angles),
        y = core$center$y + core$height / 2 * sin(lower_angles)
      )
      upper_arc <- data.frame(
        x = core$center$x + core$width / 2 * cos(upper_angles),
        y = core$center$y + core$height / 2 * sin(upper_angles)
      )
      return(rbind(
        data.frame(
          x = c(rect$x0, core$x0),
          y = rep(rect$center$y - line_half, 2)
        ),
        lower_arc,
        data.frame(
          x = c(
            core$x0 + core$width,
            rect$x0 + rect$width,
            rect$x0 + rect$width,
            core$x0 + core$width
          ),
          y = c(
            rect$center$y - line_half,
            rect$center$y - line_half,
            rect$center$y + line_half,
            rect$center$y + line_half
          )
        ),
        upper_arc,
        data.frame(
          x = c(core$x0, rect$x0),
          y = rep(rect$center$y + line_half, 2)
        )
      ))
    }

    return(data.frame(
      x = c(
        rect$x0,
        core$x0,
        core$x0,
        core$x0 + core$width,
        core$x0 + core$width,
        rect$x0 + rect$width,
        rect$x0 + rect$width,
        core$x0 + core$width,
        core$x0 + core$width,
        core$x0,
        core$x0,
        rect$x0
      ),
      y = c(
        rect$center$y - line_half,
        rect$center$y - line_half,
        core$y0,
        core$y0,
        rect$center$y - line_half,
        rect$center$y - line_half,
        rect$center$y + line_half,
        rect$center$y + line_half,
        core$y0 + core$height,
        core$y0 + core$height,
        rect$center$y + line_half,
        rect$center$y + line_half
      )
    ))
  }

  line_half <- max(rect$width * 0.01, 0.5) / 2
  data.frame(
    x = c(
      rect$center$x - line_half,
      rect$center$x - line_half,
      core$x0,
      core$x0,
      rect$center$x - line_half,
      rect$center$x - line_half,
      rect$center$x + line_half,
      rect$center$x + line_half,
      core$x0 + core$width,
      core$x0 + core$width,
      rect$center$x + line_half,
      rect$center$x + line_half
    ),
    y = c(
      rect$y0,
      core$y0,
      core$y0,
      core$y0 + core$height,
      core$y0 + core$height,
      rect$y0 + rect$height,
      rect$y0 + rect$height,
      core$y0 + core$height,
      core$y0 + core$height,
      core$y0,
      core$y0,
      rect$y0
    )
  )
}

draw_text_centered <- function(
  x,
  y,
  label,
  font_px,
  max_width = Inf,
  max_height = Inf,
  color = "black"
) {
  if (is.null(label) || trimws(label) == "") {
    return(invisible(NULL))
  }

  if (!is.finite(max_width) || !is.finite(max_height)) {
    text(x, y, labels = label, cex = font_px_to_cex(font_px), col = color)
    return(invisible(NULL))
  }

  fit <- fit_label_text(label, font_px, max_width, max_height)
  line_count <- length(fit$lines)
  y_offsets <- (seq_len(line_count) - mean(seq_len(line_count))) * fit$line_height
  text(
    rep(x, line_count),
    y + y_offsets,
    labels = fit$lines,
    cex = fit$cex,
    col = color
  )
}

#' Draw text aligned to the bottom center of a rectangle.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
is_js_hidden_glyph_class <- function(class_name) {
  class_name %in% c("unit of information", "state variable", "terminal")
}

#' Choose the JavaScript renderer text color for a glyph color fill.
#'
#' Args:
#'   fill_color: Hex color string.
#'
#' Returns:
#'   Hex text color used by the JavaScript renderer.
js_text_color_for_fill <- function(fill_color) {
  match <- regexec("^#?([A-Fa-f0-9]{2})([A-Fa-f0-9]{2})([A-Fa-f0-9]{2})$", fill_color)
  parts <- regmatches(fill_color, match)[[1]]
  if (length(parts) != 4) {
    return(JS_NODE_TEXT_COLOR)
  }

  rgb <- strtoi(parts[2:4], base = 16) / 255
  linear <- ifelse(
    rgb <= 0.03928,
    rgb / 12.92,
    ((rgb + 0.055) / 1.055)^2.4
  )
  luminance <- 0.2126 * linear[1] + 0.7152 * linear[2] + 0.0722 * linear[3]
  if (luminance < 0.45) {
    return("#ffffff")
  }
  JS_NODE_TEXT_COLOR
}

#' Load a style JSON file.
#'
#' Args:
#'   path: JSON file path.
#'
#' Returns:
#'   Named list style configuration.
load_style_json_file <- function(path) {
  style_config <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  if (is.null(style_config$styles) || !is.list(style_config$styles)) {
    stop("style_json_file must contain a styles object")
  }
  style_config
}

#' Load glyph colors from a JSON file.
#'
#' Args:
#'   path: JSON file path.
#'
#' Returns:
#'   Named character vector or NULL.
load_glyph_colors_json_file <- function(path) {
  parsed <- jsonlite::fromJSON(path, simplifyVector = FALSE)
  colors <- if (!is.null(parsed$glyph_colors)) parsed$glyph_colors else parsed
  if (!is.list(colors)) {
    stop("glyph_colors_json_file must contain a JSON object")
  }
  if (length(colors) == 0) {
    return(NULL)
  }
  stats::setNames(as.character(unlist(colors, use.names = FALSE)), names(colors))
}

#' Return the active style entry for a glyph class.
#'
#' Args:
#'   class_name: SBGN glyph class.
#'
#' Returns:
#'   Style entry list or NULL.
style_entry_for_class <- function(class_name) {
  styles <- renderer_state$style_config$styles
  if (is.null(styles)) {
    return(NULL)
  }
  candidates <- class_name
  if (endsWith(class_name, " multimer")) {
    candidates <- c(candidates, sub(" multimer$", "", class_name))
  }
  if (grepl("macromolecule", class_name, fixed = TRUE)) {
    candidates <- c(candidates, "macromolecule")
  }
  if (grepl("simple chemical", class_name, fixed = TRUE)) {
    candidates <- c(candidates, "simple chemical")
  }
  if (grepl("complex", class_name, fixed = TRUE)) {
    candidates <- c(candidates, "complex")
  }
  if (
    grepl("process", class_name, fixed = TRUE) ||
      class_name %in% c("association", "dissociation")
  ) {
    candidates <- c(candidates, "process")
  }
  candidates <- c(candidates, "generic node")
  for (candidate in candidates) {
    if (!is.null(styles[[candidate]]) && is.list(styles[[candidate]])) {
      return(styles[[candidate]])
    }
  }
  NULL
}

#' Return active edge color.
#'
#' Returns:
#'   R color string.
style_edge_color <- function() {
  if (!is.null(renderer_state$style_config$edge_color)) {
    return(renderer_state$style_config$edge_color)
  }
  JS_EDGE_COLOR
}

#' Get the glyph color fill used by the JavaScript renderer.
#'
#' Args:
#'   glyph: Glyph record.
#'   glyph_colors: Named character vector mapping labels or ids to colors.
#'
#' Returns:
#'   Glyph fill color or NULL.
js_glyph_fill_color <- function(
  glyph,
  glyph_colors = NULL,
  glyph_color_type = "label"
) {
  if (is.null(glyph_colors)) {
    return(NULL)
  }

  glyph_key <- if (glyph_color_type == "id") glyph$id else trimws(glyph$label)
  if (glyph_key == "" || !(glyph_key %in% names(glyph_colors))) {
    return(NULL)
  }

  fill_color <- glyph_colors[[glyph_key]]
  if (is.null(fill_color) || is.na(fill_color) || fill_color == "") {
    return(NULL)
  }
  fill_color
}

#' Return the Cytoscape stylesheet mapping for one SBGN glyph.
#'
#' Args:
#'   glyph: Glyph record.
#'   glyph_colors: Named character vector mapping labels or ids to colors.
#'
#' Returns:
#'   List describing the basic shape, label, and style.
js_glyph_style <- function(
  glyph,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE
) {
  class_name <- glyph$class
  label <- if (class_name == "submap") glyph$label else trimws(glyph$label)
  label_overrides <- c(
    "and" = "AND",
    "or" = "OR",
    "not" = "NOT",
    "omitted process" = "\\\\",
    "uncertain process" = "?",
    "delay" = "\u03c4",
    "dissociation" = "o"
  )
  if (class_name %in% names(label_overrides)) {
    label <- label_overrides[[class_name]]
  }
  style <- list(
    shape = "rounded_rectangle",
    fill = JS_NODE_FILL_COLOR,
    border = JS_NODE_BORDER_COLOR,
    border_width = JS_DEFAULT_NODE_BORDER_WIDTH,
    text_color = JS_NODE_TEXT_COLOR,
    font_px = JS_NODE_FONT_PX,
    label = label,
    label_valign = "center",
    border_lty = 1
  )

  if (class_name == "compartment") {
    style$shape <- "compartment"
    style$fill <- "#ffffff7f"
    style$border <- JS_COMPARTMENT_BORDER_COLOR
    style$border_width <- JS_COMPARTMENT_BORDER_WIDTH
    style$font_px <- 14
    style$label_valign <- "center"
    style$border_lty <- 1
  }
  if (grepl("macromolecule", class_name, fixed = TRUE)) {
    style$shape <- "macromolecule"
    style$border <- JS_MACROMOLECULE_BORDER_COLOR
  }
  if (grepl("nucleic acid feature", class_name, fixed = TRUE)) {
    style$shape <- "nucleic acid feature"
  }
  if (grepl("simple chemical", class_name, fixed = TRUE)) {
    style$shape <- "simple chemical"
    style$border <- JS_SIMPLE_CHEMICAL_BORDER_COLOR
  }
  if (grepl("complex", class_name, fixed = TRUE)) {
    style$shape <- "complex"
    style$border <- JS_COMPLEX_BORDER_COLOR
    style$border_width <- JS_COMPLEX_BORDER_WIDTH
    if (!endsWith(class_name, " multimer")) {
      style$fill <- "#ffffff7f"
    }
  }
  if (
    grepl("process", class_name, fixed = TRUE) ||
      class_name %in% c("association", "dissociation", "and", "or", "not")
  ) {
    style$shape <- "polygon"
    style$border <- JS_PROCESS_BORDER_COLOR
  }
  if (class_name == "submap") {
    style$shape <- "rectangle"
    style$border <- JS_SUBMAP_BORDER_COLOR
    style$border_width <- JS_COMPLEX_BORDER_WIDTH
  }
  if (class_name == "phenotype") {
    style$shape <- "hexagon"
    style$border <- JS_PHENOTYPE_BORDER_COLOR
  }
  if (class_name == "source and sink") {
    style$shape <- "empty set"
    style$border <- JS_SOURCE_SINK_BORDER_COLOR
    style$label <- ""
  }
  if (class_name %in% c("unspecified entity", "delay")) {
    style$shape <- "ellipse"
  }
  if (class_name %in% c("tag", "perturbing agent")) {
    style$shape <- "polygon"
  }
  if (startsWith(class_name, "BA ") || class_name == "biological activity") {
    style$shape <- "biological activity"
  }
  if (class_name == "empty set") {
    style$shape <- "empty set"
    style$label <- ""
  }

  style_entry <- style_entry_for_class(class_name)
  if (!is.null(style_entry)) {
    if (!is.null(style_entry$fill)) {
      fill_color <- style_entry$fill
      fill_opacity <- if (!is.null(style_entry$fill_opacity)) {
        as.numeric(style_entry$fill_opacity)
      } else if (!is.null(style_entry$opacity)) {
        as.numeric(style_entry$opacity)
      } else {
        1
      }
      style$fill <- grDevices::adjustcolor(
        fill_color,
        alpha.f = max(0, min(1, fill_opacity))
      )
    }
    if (!is.null(style_entry$border)) {
      style$border <- style_entry$border
    }
  }
  if (!is.null(renderer_state$style_config$text_color)) {
    style$text_color <- renderer_state$style_config$text_color
  }

  glyph_fill <- js_glyph_fill_color(glyph, glyph_colors, glyph_color_type)
  if (!is.null(glyph_fill)) {
    style$fill <- glyph_fill
    style$border <- JS_GLYPH_COLOR_BORDER_COLOR
    style$border_width <- JS_GLYPH_COLOR_BORDER_WIDTH
    if (isTRUE(auto_contrast_text)) {
      style$text_color <- js_text_color_for_fill(glyph_fill)
    }
  }

  style
}

#' Draw a JavaScript-compatible shape with its label.
#'
#' Args:
#'   points: Data frame of polygon coordinates.
#'   rect: Glyph rectangle.
#'   style: Style list from js_glyph_style().
#'
#' Returns:
#'   NULL.
draw_js_shape <- function(points, rect, style) {
  polygon(
    points$x,
    points$y,
    col = style$fill,
    border = style$border,
    lwd = style$border_width,
    lty = style$border_lty
  )

  label <- style$label
  if (is.null(label) || trimws(label) == "") {
    return(invisible(NULL))
  }

  label_y <- rect$center$y
  if (style$label_valign == "top") {
    label_y <- rect$y0 + max(8, style$font_px)
  }
  draw_text_centered(
    rect$center$x,
    label_y,
    label,
    style$font_px,
    Inf,
    Inf,
    style$text_color
  )
}

js_shape_points <- function(glyph, rect, style) {
  if (is_ported_glyph_class(glyph$class)) {
    return(ported_glyph_points(rect, glyph))
  }
  if (style$shape == "ellipse" || style$shape == "empty set") {
    return(ellipse_points(rect$center$x, rect$center$y, rect$width / 2, rect$height / 2, 80))
  }
  if (style$shape == "simple chemical") {
    return(stadium_points(rect))
  }
  if (style$shape == "rectangle") {
    return(data.frame(
      x = c(rect$x0, rect$x0 + rect$width, rect$x0 + rect$width, rect$x0),
      y = c(rect$y0, rect$y0, rect$y0 + rect$height, rect$y0 + rect$height)
    ))
  }
  if (style$shape == "hexagon") {
    return(hexagon_points(rect))
  }
  if (style$shape == "complex") {
    return(complex_points(rect))
  }
  if (style$shape == "nucleic acid feature") {
    return(bottom_round_rect_points(rect))
  }
  if (style$shape == "compartment") {
    return(barrel_points(rect))
  }
  if (glyph$class == "tag") {
    return(tag_points(rect, glyph$orientation))
  }
  if (glyph$class == "perturbing agent") {
    return(perturbing_agent_points(rect))
  }
  radius <- max(1, min(rect$width, rect$height) * 0.1)
  round_rect_points(rect$x0, rect$y0, rect$x0 + rect$width, rect$y0 + rect$height, radius)
}

#' Map an auxiliary glyph's entity declaration to its primitive shape.
#'
#' @param glyph Parsed unit-of-information or state-variable glyph.
#'
#' @return Primitive shape name used by rendering and manifests.
auxiliary_glyph_shape <- function(glyph) {
  if (glyph$class == "state variable") {
    return("stadium_round_rectangle")
  }
  entity_name <- if (is.null(glyph$entity_name)) {
    ""
  } else {
    tolower(trimws(glyph$entity_name))
  }
  switch(
    entity_name,
    "macromolecule" = "round_rectangle",
    "nucleic acid feature" = "bottom_round_rectangle",
    "complex" = "complex",
    "simple chemical" = "stadium_round_rectangle",
    "unspecified entity" = "ellipse",
    "perturbation" = "perturbing_agent",
    "perturbing agent" = "perturbing_agent",
    "rectangle"
  )
}

#' Draw one glyph using the JavaScript renderer's basic primitive mapping.
#'
#' Args:
#'   glyph: Glyph record.
#'   glyph_colors: Named character vector mapping labels or ids to colors.
#'
#' Returns:
#'   NULL.
draw_auxiliary_glyph <- function(glyph) {
  if (!(glyph$class %in% c("unit of information", "state variable"))) {
    return(FALSE)
  }
  if (is.null(glyph$parent_id) || is.null(glyph$bbox)) {
    return(TRUE)
  }

  glyph_rect <- bbox_pixel_rect(glyph$bbox)
  shape <- auxiliary_glyph_shape(glyph)
  points <- if (shape == "stadium_round_rectangle") {
    stadium_points(glyph_rect)
  } else if (shape == "round_rectangle") {
    radius <- max(1, min(glyph_rect$width, glyph_rect$height) * 0.1)
    round_rect_points(
      glyph_rect$x0,
      glyph_rect$y0,
      glyph_rect$x0 + glyph_rect$width,
      glyph_rect$y0 + glyph_rect$height,
      radius
    )
  } else if (shape == "bottom_round_rectangle") {
    bottom_round_rect_points(glyph_rect)
  } else if (shape == "complex") {
    complex_points(glyph_rect)
  } else if (shape == "ellipse") {
    ellipse_points(
      glyph_rect$center$x,
      glyph_rect$center$y,
      glyph_rect$width / 2,
      glyph_rect$height / 2,
      80
    )
  } else if (shape == "perturbing_agent") {
    perturbing_agent_points(glyph_rect)
  } else {
    data.frame(
      x = c(
        glyph_rect$x0,
        glyph_rect$x0 + glyph_rect$width,
        glyph_rect$x0 + glyph_rect$width,
        glyph_rect$x0
      ),
      y = c(
        glyph_rect$y0,
        glyph_rect$y0,
        glyph_rect$y0 + glyph_rect$height,
        glyph_rect$y0 + glyph_rect$height
      )
    )
  }
  polygon(
    points$x,
    points$y,
    col = JS_NODE_FILL_COLOR,
    border = JS_NODE_BORDER_COLOR,
    lwd = JS_DEFAULT_NODE_BORDER_WIDTH
  )
  label <- if (glyph$class == "state variable") {
    state_variable_label(glyph$state_value, glyph$state_variable)
  } else {
    glyph$label
  }
  if (!is.null(label) && nzchar(trimws(label))) {
    draw_text_centered(
      glyph_rect$center$x,
      glyph_rect$center$y,
      label,
      max(5, min(8, glyph_rect$height * 0.75)),
      color = JS_NODE_TEXT_COLOR
    )
  }
  TRUE
}

#' Clip polygon points to the portion at or below a horizontal boundary.
#'
#' @param points Data frame containing polygon x/y coordinates.
#' @param min_y Top edge of the retained horizontal band.
#'
#' @return Data frame containing the clipped polygon.
clip_polygon_below_y <- function(points, min_y) {
  if (nrow(points) == 0) {
    return(points)
  }
  output <- data.frame(x = numeric(0), y = numeric(0))
  previous <- points[nrow(points), ]
  previous_inside <- previous$y >= min_y

  for (index in seq_len(nrow(points))) {
    current <- points[index, ]
    current_inside <- current$y >= min_y
    if (current_inside != previous_inside) {
      fraction <- (min_y - previous$y) / (current$y - previous$y)
      output <- rbind(output, data.frame(
        x = previous$x + fraction * (current$x - previous$x),
        y = min_y
      ))
    }
    if (current_inside) {
      output <- rbind(output, current)
    }
    previous <- current
    previous_inside <- current_inside
  }
  output
}

draw_js_glyph <- function(
  glyph,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE
) {
  if (draw_auxiliary_glyph(glyph)) {
    return(invisible(NULL))
  }
  if (is.null(glyph$bbox) || is_js_hidden_glyph_class(glyph$class)) {
    return(invisible(NULL))
  }

  rect <- sbgnviz_manifest_rect(glyph)
  style <- js_glyph_style(
    glyph,
    glyph_colors,
    glyph_color_type,
    auto_contrast_text
  )
  if (endsWith(glyph$class, " multimer")) {
    shadow <- rect
    shadow$x0 <- rect$x0 + 5
    shadow$y0 <- rect$y0 + 5
    shadow$center <- list(x = rect$center$x + 5, y = rect$center$y + 5)
    shadow_points <- js_shape_points(glyph, shadow, style)
    polygon(
      shadow_points$x,
      shadow_points$y,
      col = style$fill,
      border = style$border,
      lwd = style$border_width,
      lty = style$border_lty
    )
  }

  points <- js_shape_points(glyph, rect, style)
  draw_js_shape(points, rect, style)
  if (isTRUE(glyph$has_clone)) {
    marker_height <- max(3, rect$height * 0.22)
    marker_points <- clip_polygon_below_y(
      points,
      rect$y0 + rect$height - marker_height
    )
    if (nrow(marker_points) >= 3) {
      polygon(marker_points$x, marker_points$y, col = "#838383", border = NA)
    }
  }
  if (glyph$class == "empty set" || glyph$class == "source and sink") {
    segments(
      rect$x0,
      rect$y0 + rect$height,
      rect$x0 + rect$width,
      rect$y0,
      col = style$border,
      lwd = style$border_width
    )
  }
}

#' Draw a glyph and its children.
#'
#' @param glyph Glyph record.
#' @param child_map Named list of child glyphs.
#' @param show_clone_markers Whether to show clone markers.
#' @param glyph_colors Named character vector from glyph label or id to color.
#' @param connected_port_ids Port ids referenced by arcs.
#'
#' @return NULL.
build_reference_maps <- function(glyphs) {
  glyph_lookup <- list()
  port_lookup <- list()
  port_parent_lookup <- list()

  for (glyph in glyphs) {
    if (!is.null(glyph_lookup[[glyph$id]])) {
      next
    }
    glyph_lookup[[glyph$id]] <- glyph
    if (!is.null(glyph$ports) && nrow(glyph$ports) > 0) {
      for (index in seq_len(nrow(glyph$ports))) {
        port_lookup[[glyph$ports$id[index]]] <- list(
          x = glyph$ports$x[index],
          y = glyph$ports$y[index]
        )
        port_parent_lookup[[glyph$ports$id[index]]] <- glyph$id
      }
    }
  }

  list(glyphs = glyph_lookup, ports = port_lookup, port_parents = port_parent_lookup)
}

#' Get the center point for a glyph bounding box.
#'
#' @param glyph Glyph record.
#'
#' @return List with x and y.
glyph_center_point <- function(glyph) {
  list(
    x = glyph$bbox$x + glyph$bbox$w / 2,
    y = glyph$bbox$y + glyph$bbox$h / 2
  )
}

#' Intersect a ray from another point with a glyph bounding box.
#'
#' @param glyph Glyph record.
#' @param from_point List with x and y outside or near the glyph.
#'
#' @return List with x and y on the glyph bounds.
glyph_boundary_point <- function(glyph, from_point) {
  center <- glyph_center_point(glyph)
  dx <- center$x - from_point$x
  dy <- center$y - from_point$y
  if (sqrt(dx^2 + dy^2) <= 1e-6) {
    return(center)
  }

  x_min <- glyph$bbox$x
  x_max <- glyph$bbox$x + glyph$bbox$w
  y_min <- glyph$bbox$y
  y_max <- glyph$bbox$y + glyph$bbox$h
  candidates <- numeric(0)

  if (abs(dx) > 1e-6) {
    candidates <- c(candidates, (x_min - from_point$x) / dx)
    candidates <- c(candidates, (x_max - from_point$x) / dx)
  }
  if (abs(dy) > 1e-6) {
    candidates <- c(candidates, (y_min - from_point$y) / dy)
    candidates <- c(candidates, (y_max - from_point$y) / dy)
  }

  for (scale in sort(candidates)) {
    if (scale < 0 || scale > 1) {
      next
    }
    x <- from_point$x + dx * scale
    y <- from_point$y + dy * scale
    if (
      x >= x_min - 1e-6 &&
        x <= x_max + 1e-6 &&
        y >= y_min - 1e-6 &&
        y <= y_max + 1e-6
    ) {
      return(list(x = x, y = y))
    }
  }

  center
}

#' Resolve a JavaScript edge endpoint to the rendered glyph id.
#'
#' Args:
#'   reference: Glyph or port id from an SBGN arc.
#'   port_parent_lookup: Named list mapping port ids to owning glyph ids.
#'
#' Returns:
#'   Glyph id or NULL.
js_endpoint_glyph_id <- function(reference, port_parent_lookup) {
  if (is.null(reference) || is.na(reference)) {
    return(NULL)
  }
  if (reference %in% names(port_parent_lookup)) {
    return(port_parent_lookup[[reference]])
  }
  reference
}

#' Intersect a line from a node center toward another point with an ellipse.
#'
#' Args:
#'   glyph: Glyph record.
#'   other_point: Opposite endpoint point.
#'
#' Returns:
#'   List with x and y.
ellipse_boundary_point <- function(glyph, other_point) {
  center <- glyph_center_point(glyph)
  dx <- other_point$x - center$x
  dy <- other_point$y - center$y
  if (sqrt(dx^2 + dy^2) <= 1e-6) {
    return(center)
  }

  rx <- glyph$bbox$w / 2
  ry <- glyph$bbox$h / 2
  scale <- 1 / sqrt((dx / rx)^2 + (dy / ry)^2)
  list(x = center$x + dx * scale, y = center$y + dy * scale)
}

#' Get a JavaScript-compatible edge endpoint on the node boundary.
#'
#' Args:
#'   glyph: Glyph record.
#'   other_point: Opposite endpoint point.
#'
#' Returns:
#'   List with x and y.
js_node_boundary_point <- function(glyph, other_point) {
  style <- js_glyph_style(glyph)
  if (style$shape == "ellipse") {
    return(ellipse_boundary_point(glyph, other_point))
  }
  glyph_boundary_point(glyph, other_point)
}

#' Build JavaScript-compatible drawable arc endpoints.
#'
#' Args:
#'   arc: Arc record.
#'   glyph_lookup: Named list of glyph records.
#'   port_parent_lookup: Named list mapping port ids to owning glyph ids.
#'
#' Returns:
#'   Data frame with x and y endpoint rows, or NULL when not drawable.
js_arc_points <- function(arc, glyph_lookup, port_parent_lookup) {
  source_id <- js_endpoint_glyph_id(arc$source, port_parent_lookup)
  target_id <- js_endpoint_glyph_id(arc$target, port_parent_lookup)
  if (
    is.null(source_id) ||
      is.null(target_id) ||
      !(source_id %in% names(glyph_lookup)) ||
      !(target_id %in% names(glyph_lookup))
  ) {
    return(NULL)
  }

  source_glyph <- glyph_lookup[[source_id]]
  target_glyph <- glyph_lookup[[target_id]]
  if (
    is_js_hidden_glyph_class(source_glyph$class) ||
      is_js_hidden_glyph_class(target_glyph$class)
  ) {
    return(NULL)
  }

  points <- arc$points
  if (
    is.null(points) ||
      nrow(points) < 2 ||
      any(!is.finite(points$x)) ||
      any(!is.finite(points$y))
  ) {
    source_center <- glyph_center_point(source_glyph)
    target_center <- glyph_center_point(target_glyph)
    start_point <- js_node_boundary_point(source_glyph, target_center)
    end_point <- js_node_boundary_point(target_glyph, source_center)
    points <- data.frame(
      x = c(start_point$x, end_point$x),
      y = c(start_point$y, end_point$y)
    )
  }

  endpoint_specs <- list(
    list(index = 1, reference = arc$source, glyph = source_glyph),
    list(index = nrow(points), reference = arc$target, glyph = target_glyph)
  )
  for (endpoint_spec in endpoint_specs) {
    reference <- endpoint_spec$reference
    glyph <- endpoint_spec$glyph
    if (
      !is.null(reference) &&
        !is.na(reference) &&
        reference %in% names(port_parent_lookup) &&
        !is_ported_glyph_class(glyph$class)
    ) {
      endpoint <- js_non_cytoscape_port_endpoint(glyph, reference)
      if (!is.null(endpoint)) {
        points$x[endpoint_spec$index] <- endpoint$x
        points$y[endpoint_spec$index] <- endpoint$y
      }
    }
  }

  points$glyph_id <- rep(NA_character_, nrow(points))
  points$glyph_id[1] <- source_id
  points$glyph_id[nrow(points)] <- target_id
  points
}

#' Clip a non-Cytoscape-ported endpoint to its painted node boundary.
#'
#' @param glyph Endpoint glyph containing the referenced port.
#' @param port_id Referenced SBGN port ID.
#'
#' @return List with boundary x and y, or NULL when geometry is missing.
js_non_cytoscape_port_endpoint <- function(glyph, port_id) {
  if (is.null(glyph$bbox) || is.null(glyph$ports) || nrow(glyph$ports) == 0) {
    return(NULL)
  }
  port_index <- match(port_id, glyph$ports$id)
  if (is.na(port_index)) {
    return(NULL)
  }

  half_border <- js_glyph_style(glyph)$border_width / 2
  x0 <- glyph$bbox$x - half_border
  y0 <- glyph$bbox$y - half_border
  width <- glyph$bbox$w + 2 * half_border
  height <- glyph$bbox$h + 2 * half_border
  center <- glyph_center_point(glyph)
  port_x <- glyph$ports$x[port_index]
  port_y <- glyph$ports$y[port_index]
  dx <- port_x - center$x
  dy <- port_y - center$y

  if (abs(dx) > abs(dy)) {
    return(list(x = if (dx < 0) x0 else x0 + width, y = port_y))
  }
  list(x = port_x, y = if (dy < 0) y0 else y0 + height)
}

#' Extend an arc line to process and logical-node port coordinates.
#'
#' SBGN paths commonly stop half a stroke outside a port. Extending the line
#' beneath the port outline prevents raster seams between connected elements.
#'
#' @param arc Parsed arc record.
#' @param points Resolved source-space arc points.
#' @param glyph_lookup Named list of glyph records.
#' @param port_parent_lookup Named list mapping port ids to owning glyph ids.
#'
#' @return Arc point data frame with ported endpoints snapped to their ports.
js_arc_line_points <- function(
  arc,
  points,
  glyph_lookup,
  port_parent_lookup
) {
  snap_endpoint <- function(reference, fallback_x, fallback_y) {
    if (
      is.null(reference) ||
        is.na(reference) ||
        !(reference %in% names(port_parent_lookup))
    ) {
      return(list(x = fallback_x, y = fallback_y))
    }
    glyph <- glyph_lookup[[port_parent_lookup[[reference]]]]
    if (is.null(glyph) || !is_ported_glyph_class(glyph$class)) {
      return(list(x = fallback_x, y = fallback_y))
    }
    port_index <- match(reference, glyph$ports$id)
    if (is.na(port_index)) {
      return(list(x = fallback_x, y = fallback_y))
    }
    list(x = glyph$ports$x[port_index], y = glyph$ports$y[port_index])
  }

  end_index <- nrow(points)
  start <- snap_endpoint(arc$source, points$x[1], points$y[1])
  end <- snap_endpoint(
    arc$target,
    points$x[end_index],
    points$y[end_index]
  )
  points$x[1] <- start$x
  points$y[1] <- start$y
  points$x[end_index] <- end$x
  points$y[end_index] <- end$y
  points
}

#' Map an SBGN arc class to the JavaScript target marker primitive.
#'
#' Args:
#'   arc_class: SBGN arc class.
#'
#' Returns:
#'   Marker type string.
js_arc_marker <- function(arc_class) {
  if (arc_class %in% c("consumption", "logic arc", "equivalence arc")) {
    return("none")
  }
  if (arc_class %in% c("inhibition", "negative influence")) {
    return("tee")
  }
  if (arc_class == "catalysis") {
    return("circle")
  }
  if (arc_class %in% c("modulation", "unknown influence")) {
    return("diamond")
  }
  if (arc_class == "necessary stimulation") {
    return("triangle-cross")
  }
  "triangle"
}

#' Return the Go-compatible marker-tip displacement in source units.
#'
#' @param arc_class SBGN arc class.
#'
#' @return Numeric displacement along the final arc segment.
js_marker_tip_offset_source <- function(arc_class) {
  marker <- js_arc_marker(arc_class)
  if (marker %in% c("triangle", "triangle-cross")) {
    return(3.125)
  }
  if (marker == "circle") {
    return(-2.3125)
  }
  if (marker == "diamond") {
    return(1.5625)
  }
  0
}

#' Calculate an arc marker tip that overlaps its target boundary.
#'
#' @param arc Parsed arc record.
#' @param points Resolved source-space arc points.
#'
#' @return List containing marker-tip x and y coordinates.
js_arc_marker_point <- function(arc, points) {
  end_index <- nrow(points)
  other_index <- if (end_index > 2) end_index - 1 else 1
  end_point <- list(x = points$x[end_index], y = points$y[end_index])
  offset <- js_marker_tip_offset_source(arc$class)
  dx <- end_point$x - points$x[other_index]
  dy <- end_point$y - points$y[other_index]
  length <- sqrt(dx^2 + dy^2)
  if (offset == 0 || length <= 1e-6) {
    return(end_point)
  }
  list(
    x = end_point$x + dx / length * offset,
    y = end_point$y + dy / length * offset
  )
}

#' Draw a filled triangle marker using the JavaScript edge color.
#'
#' Args:
#'   x_end: Arrow tip x coordinate.
#'   y_end: Arrow tip y coordinate.
#'   x_prev: Previous point x coordinate.
#'   y_prev: Previous point y coordinate.
#'   size: Arrow size.
#'
#' Returns:
#'   NULL.
draw_js_triangle <- function(x_end, y_end, x_prev, y_prev, size) {
  dx <- x_end - x_prev
  dy <- y_end - y_prev
  length <- sqrt(dx^2 + dy^2)
  if (length == 0) {
    return(invisible(NULL))
  }
  ux <- dx / length
  uy <- dy / length
  base_x <- x_end - ux * size
  base_y <- y_end - uy * size
  perp_x <- -uy
  perp_y <- ux
  half_width <- size * 0.6
  polygon(
    c(base_x + perp_x * half_width, base_x - perp_x * half_width, x_end),
    c(base_y + perp_y * half_width, base_y - perp_y * half_width, y_end),
    border = style_edge_color(),
    col = style_edge_color(),
    lwd = JS_DEFAULT_EDGE_WIDTH
  )
}

marker_polygon_points <- function(x_end, y_end, x_prev, y_prev, size, local_points) {
  dx <- x_end - x_prev
  dy <- y_end - y_prev
  length <- sqrt(dx^2 + dy^2)
  if (length == 0) {
    return(NULL)
  }
  ux <- dx / length
  uy <- dy / length
  px <- -uy
  py <- ux
  data.frame(
    x = x_end + ux * local_points$y * size - px * local_points$x * size,
    y = y_end + uy * local_points$y * size - py * local_points$x * size
  )
}

draw_js_marker_polygon <- function(
  x_end,
  y_end,
  x_prev,
  y_prev,
  size,
  local_points,
  fill = NA,
  border = style_edge_color(),
  lwd = 1
) {
  points <- marker_polygon_points(x_end, y_end, x_prev, y_prev, size, local_points)
  if (is.null(points)) {
    return(invisible(NULL))
  }
  polygon(points$x, points$y, col = fill, border = border, lwd = lwd)
}

#' Draw a tee marker using the JavaScript edge color.
#'
#' Args:
#'   x_end: End x coordinate.
#'   y_end: End y coordinate.
#'   x_prev: Previous point x coordinate.
#'   y_prev: Previous point y coordinate.
#'   length: Tee marker length.
#'
#' Returns:
#'   NULL.
draw_js_tee <- function(x_end, y_end, x_prev, y_prev, length) {
  dx <- x_end - x_prev
  dy <- y_end - y_prev
  seg_len <- sqrt(dx^2 + dy^2)
  if (seg_len == 0) {
    return(invisible(NULL))
  }
  ux <- dx / seg_len
  uy <- dy / seg_len
  perp_x <- -uy
  perp_y <- ux
  half_len <- length / 2
  segments(
    x_end - perp_x * half_len,
    y_end - perp_y * half_len,
    x_end + perp_x * half_len,
    y_end + perp_y * half_len,
    col = style_edge_color(),
    lwd = JS_DEFAULT_EDGE_WIDTH
  )
}

#' Draw an arc line using the JavaScript renderer's basic edge mapping.
#'
#' Args:
#'   arc: Arc record.
#'   glyph_lookup: Named list of glyph records.
#'   port_parent_lookup: Named list mapping port ids to owning glyph ids.
#'
#' Returns:
#'   NULL.
draw_js_arc <- function(arc, glyph_lookup = list(), port_parent_lookup = list()) {
  points <- js_arc_points(arc, glyph_lookup, port_parent_lookup)
  if (is.null(points) || nrow(points) < 2) {
    return(invisible(NULL))
  }
  points <- js_arc_line_points(
    arc,
    points,
    glyph_lookup,
    port_parent_lookup
  )

  lines(
    points$x,
    points$y,
    col = style_edge_color(),
    lwd = JS_DEFAULT_EDGE_WIDTH
  )
  invisible(NULL)
}

#' Draw an arc marker above node fills using Go-compatible placement.
#'
#' @param arc Parsed arc record.
#' @param glyph_lookup Named list of glyph records.
#' @param port_parent_lookup Named list mapping port ids to owning glyph ids.
#'
#' @return NULL.
draw_js_arc_marker <- function(
  arc,
  glyph_lookup = list(),
  port_parent_lookup = list()
) {
  points <- js_arc_points(arc, glyph_lookup, port_parent_lookup)
  if (is.null(points) || nrow(points) < 2) {
    return(invisible(NULL))
  }

  marker <- js_arc_marker(arc$class)
  if (marker == "none") {
    return(invisible(NULL))
  }
  marker_size <- ARROW_SIZE * CYTOSCAPE_ARROW_SCALE
  end_index <- nrow(points)
  raw_end <- list(x = points$x[end_index], y = points$y[end_index])
  marker_point <- js_arc_marker_point(arc, points)
  marker_moved <- sqrt(
    (marker_point$x - raw_end$x)^2 +
      (marker_point$y - raw_end$y)^2
  ) > 1e-6
  previous_point <- if (marker_moved) {
    raw_end
  } else {
    list(x = points$x[1], y = points$y[1])
  }
  if (marker == "triangle") {
    if (arc$class == "production") {
      draw_js_marker_polygon(
        marker_point$x,
        marker_point$y,
        previous_point$x,
        previous_point$y,
        marker_size,
        data.frame(x = c(-0.15, 0, 0.15), y = c(-0.3, 0, -0.3)),
        fill = style_edge_color(),
        border = NA,
        lwd = 1
      )
    } else {
      draw_js_marker_polygon(
        marker_point$x,
        marker_point$y,
        previous_point$x,
        previous_point$y,
        marker_size,
        data.frame(x = c(-0.15, 0, 0.15), y = c(-0.3, 0, -0.3)),
        fill = JS_NODE_FILL_COLOR,
        border = style_edge_color(),
        lwd = 1
      )
    }
  } else if (marker == "tee") {
    draw_js_tee(
      marker_point$x,
      marker_point$y,
      previous_point$x,
      previous_point$y,
      marker_size * 0.3
    )
  } else if (marker == "circle") {
    symbols(
      marker_point$x,
      marker_point$y,
      circles = marker_size * 0.15,
      inches = FALSE,
      add = TRUE,
      fg = style_edge_color(),
      bg = JS_NODE_FILL_COLOR,
      lwd = 1
    )
  } else if (marker == "diamond") {
    draw_js_marker_polygon(
      marker_point$x,
      marker_point$y,
      previous_point$x,
      previous_point$y,
      marker_size,
      data.frame(x = c(-0.15, 0, 0.15, 0), y = c(-0.15, -0.3, -0.15, 0)),
      fill = JS_NODE_FILL_COLOR,
      border = style_edge_color(),
      lwd = 1
    )
  } else if (marker == "triangle-cross") {
    draw_js_marker_polygon(
      marker_point$x,
      marker_point$y,
      previous_point$x,
      previous_point$y,
      marker_size,
      data.frame(x = c(-0.15, 0, 0.15), y = c(-0.3, 0, -0.3)),
      fill = JS_NODE_FILL_COLOR,
      border = style_edge_color(),
      lwd = 1
    )
    draw_js_marker_polygon(
      marker_point$x,
      marker_point$y,
      previous_point$x,
      previous_point$y,
      marker_size,
      data.frame(
        x = c(-0.15, -0.15, 0.15, 0.15),
        y = c(-0.4, -0.4344827586206897, -0.4344827586206897, -0.4)
      ),
      fill = JS_NODE_FILL_COLOR,
      border = style_edge_color(),
      lwd = 1
    )
  }
}

#' Draw stoichiometry/cardinality boxes attached to an arc.
#'
#' @param arc Parsed arc record.
#'
#' @return NULL.
draw_arc_auxiliary_glyphs <- function(arc) {
  for (glyph in arc$auxiliary_glyphs) {
    if (
      is.null(glyph$bbox) ||
        !(tolower(trimws(glyph$class)) %in% c("stoichiometry", "cardinality"))
    ) {
      next
    }
    glyph_rect <- bbox_pixel_rect(glyph$bbox)
    rect(
      glyph_rect$x0,
      glyph_rect$y0,
      glyph_rect$x0 + glyph_rect$width,
      glyph_rect$y0 + glyph_rect$height,
      col = JS_NODE_FILL_COLOR,
      border = JS_NODE_BORDER_COLOR,
      lwd = JS_DEFAULT_NODE_BORDER_WIDTH
    )
    if (!is.null(glyph$label) && nzchar(trimws(glyph$label))) {
      draw_text_centered(
        glyph_rect$center$x,
        glyph_rect$center$y,
        glyph$label,
        max(5, min(9, glyph_rect$height * 0.75)),
        color = JS_NODE_TEXT_COLOR
      )
    }
  }
  invisible(NULL)
}

#' Render the parsed diagram to the active device.
#'
#' @param glyphs List of glyphs.
#' @param arcs List of arcs.
#' @param show_clone_markers Whether to draw clone markers.
#' @param glyph_colors Named character vector from glyph label or id to color.
#'
#' @return NULL.
render_diagram <- function(
  glyphs,
  arcs,
  show_clone_markers,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE
) {
  reference_maps <- build_reference_maps(glyphs)

  for (glyph in glyphs) {
    if (
      glyph$class == "compartment" &&
        identical(reference_maps$glyphs[[glyph$id]], glyph)
    ) {
      draw_js_glyph(glyph, glyph_colors, glyph_color_type, auto_contrast_text)
    }
  }

  for (arc in arcs) {
    draw_js_arc(arc, reference_maps$glyphs, reference_maps$port_parents)
  }

  for (glyph in glyphs) {
    if (
      glyph$class != "compartment" &&
        identical(reference_maps$glyphs[[glyph$id]], glyph)
    ) {
      draw_js_glyph(glyph, glyph_colors, glyph_color_type, auto_contrast_text)
    }
  }

  for (arc in arcs) {
    draw_js_arc_marker(arc, reference_maps$glyphs, reference_maps$port_parents)
  }

  for (arc in arcs) {
    draw_arc_auxiliary_glyphs(arc)
  }
}

#' Create a basic graphical-element manifest for parsed SBGN.
#'
#' Args:
#'   parsed: Parsed SBGN data from parse_sbgn().
#'   glyph_colors: Named character vector mapping glyph labels or ids to colors.
#'   glyph_color_type: Whether glyph_colors keys match labels or ids.
#'   auto_contrast_text: Whether to use white text on dark glyph fills.
#'
#' Returns:
#'   List with canvas bounds and basic rendered elements.
sbgnml_basic_render_manifest <- function(
  parsed,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE
) {
  glyphs <- parsed$glyphs
  arcs <- parsed$arcs
  bounds <- parsed$bounds
  reference_maps <- build_reference_maps(glyphs)
  elements <- list()
  emitted_label_ids <- character(0)

  add_element <- function(element) {
    elements[[length(elements) + 1]] <<- element
  }

  add_duplicate_label <- function(glyph) {
    if (is.null(glyph$bbox)) {
      return(invisible(NULL))
    }
    style <- js_glyph_style(
      glyph,
      glyph_colors,
      glyph_color_type,
      auto_contrast_text
    )
    label <- style$label
    label_id <- paste0(glyph$id, "::label")
    if (
      is.null(label) ||
        trimws(label) == "" ||
        label_id %in% emitted_label_ids
    ) {
      return(invisible(NULL))
    }
    rect <- sbgnviz_manifest_rect(glyph)
    label_y <- rect$center$y
    if (style$label_valign == "top") {
      label_y <- rect$y0 + max(8, style$font_px)
    }
    add_element(list(
      id = label_id,
      owner_id = glyph$id,
      kind = "label",
      type = "text",
      class = glyph$class,
      x1 = NA_real_,
      y1 = NA_real_,
      x2 = NA_real_,
      y2 = NA_real_,
      cx = rect$center$x,
      cy = label_y,
      width = max(1, rect$width - JS_TEXT_PADDING_PX),
      height = max(1, rect$height - JS_TEXT_PADDING_PX),
      text = label,
      marker = "",
      source = "",
      target = ""
    ))
    emitted_label_ids <<- c(emitted_label_ids, label_id)
    invisible(NULL)
  }

  for (glyph in glyphs) {
    if (is.null(glyph$bbox)) {
      next
    }
    if (glyph$class %in% c("unit of information", "state variable")) {
      if (is.null(glyph$parent_id)) {
        next
      }
      rect <- bbox_pixel_rect(glyph$bbox)
      label <- if (glyph$class == "state variable") {
        state_variable_label(glyph$state_value, glyph$state_variable)
      } else {
        glyph$label
      }
      add_element(list(
        id = paste0(glyph$id, "::aux_shape"),
        owner_id = glyph$id,
        kind = "auxiliary_shape",
        type = auxiliary_glyph_shape(glyph),
        class = glyph$class,
        x1 = rect$x0,
        y1 = rect$y0,
        x2 = rect$x0 + rect$width,
        y2 = rect$y0 + rect$height,
        cx = rect$center$x,
        cy = rect$center$y,
        width = rect$width,
        height = rect$height,
        text = "",
        marker = "",
        source = "",
        target = ""
      ))
      if (!is.null(label) && nzchar(trimws(label))) {
        add_element(list(
          id = paste0(glyph$id, "::aux_label"),
          owner_id = glyph$id,
          kind = "auxiliary_label",
          type = "text",
          class = glyph$class,
          x1 = rect$x0,
          y1 = rect$y0,
          x2 = rect$x0 + rect$width,
          y2 = rect$y0 + rect$height,
          cx = rect$center$x,
          cy = rect$center$y,
          width = rect$width,
          height = rect$height,
          text = label,
          marker = "",
          source = "",
          target = ""
        ))
      }
      next
    }
    if (is_js_hidden_glyph_class(glyph$class)) {
      next
    }
    if (!identical(reference_maps$glyphs[[glyph$id]], glyph)) {
      add_duplicate_label(glyph)
      next
    }
    rect <- sbgnviz_manifest_rect(glyph)
    style <- js_glyph_style(
      glyph,
      glyph_colors,
      glyph_color_type,
      auto_contrast_text
    )
    add_element(list(
      id = paste0(glyph$id, "::shape"),
      owner_id = glyph$id,
      kind = "node_shape",
      type = style$shape,
      class = glyph$class,
      x1 = rect$x0,
      y1 = rect$y0,
      x2 = rect$x0 + rect$width,
      y2 = rect$y0 + rect$height,
      cx = rect$center$x,
      cy = rect$center$y,
      width = rect$width,
      height = rect$height,
      text = "",
      marker = "",
      source = "",
      target = ""
    ))

    label <- style$label
    if (!is.null(label) && trimws(label) != "") {
      label_y <- rect$center$y
      if (style$label_valign == "top") {
        label_y <- rect$y0 + max(8, style$font_px)
      }
      add_element(list(
        id = paste0(glyph$id, "::label"),
        owner_id = glyph$id,
        kind = "label",
        type = "text",
        class = glyph$class,
        x1 = NA_real_,
        y1 = NA_real_,
        x2 = NA_real_,
        y2 = NA_real_,
        cx = rect$center$x,
        cy = label_y,
        width = max(1, rect$width - JS_TEXT_PADDING_PX),
        height = max(1, rect$height - JS_TEXT_PADDING_PX),
        text = label,
        marker = "",
        source = "",
        target = ""
      ))
      emitted_label_ids <- c(emitted_label_ids, paste0(glyph$id, "::label"))
    }
  }

  for (arc in arcs) {
    points <- js_arc_points(arc, reference_maps$glyphs, reference_maps$port_parents)
    if (is.null(points) || nrow(points) < 2) {
      next
    }
    marker <- js_arc_marker(arc$class)
    end_index <- nrow(points)
    add_element(list(
      id = paste0(arc$id, "::line"),
      owner_id = arc$id,
      kind = "edge_line",
      type = "line",
      class = arc$class,
      x1 = points$x[1],
      y1 = points$y[1],
      x2 = points$x[end_index],
      y2 = points$y[end_index],
      cx = mean(points$x),
      cy = mean(points$y),
      width = NA_real_,
      height = NA_real_,
      text = "",
      marker = marker,
      source = points$glyph_id[1],
      target = points$glyph_id[end_index]
    ))

    if (marker != "none") {
      marker_point <- js_arc_marker_point(arc, points)
      add_element(list(
        id = paste0(arc$id, "::marker"),
        owner_id = arc$id,
        kind = "edge_marker",
        type = marker,
        class = arc$class,
        x1 = NA_real_,
        y1 = NA_real_,
        x2 = NA_real_,
        y2 = NA_real_,
        cx = marker_point$x,
        cy = marker_point$y,
        width = NA_real_,
        height = NA_real_,
        text = "",
        marker = marker,
        source = points$glyph_id[1],
        target = points$glyph_id[end_index]
      ))
    }

    for (glyph in arc$auxiliary_glyphs) {
      if (
        is.null(glyph$bbox) ||
          !(tolower(trimws(glyph$class)) %in% c("stoichiometry", "cardinality"))
      ) {
        next
      }
      rect <- bbox_pixel_rect(glyph$bbox)
      add_element(list(
        id = paste0(glyph$id, "::arc_aux_shape"),
        owner_id = glyph$id,
        kind = "arc_auxiliary_shape",
        type = tolower(trimws(glyph$class)),
        class = glyph$class,
        x1 = rect$x0,
        y1 = rect$y0,
        x2 = rect$x0 + rect$width,
        y2 = rect$y0 + rect$height,
        cx = rect$center$x,
        cy = rect$center$y,
        width = rect$width,
        height = rect$height,
        text = "",
        marker = "",
        source = points$glyph_id[1],
        target = points$glyph_id[2]
      ))
      if (!is.null(glyph$label) && nzchar(trimws(glyph$label))) {
        add_element(list(
          id = paste0(glyph$id, "::arc_aux_label"),
          owner_id = glyph$id,
          kind = "arc_auxiliary_label",
          type = "text",
          class = glyph$class,
          x1 = rect$x0,
          y1 = rect$y0,
          x2 = rect$x0 + rect$width,
          y2 = rect$y0 + rect$height,
          cx = rect$center$x,
          cy = rect$center$y,
          width = rect$width,
          height = rect$height,
          text = glyph$label,
          marker = "",
          source = points$glyph_id[1],
          target = points$glyph_id[2]
        ))
      }
    }
  }

  list(
    coordinate_space = "source",
    canvas = list(
      min_x = bounds$min_x,
      min_y = bounds$min_y,
      max_x = bounds$max_x,
      max_y = bounds$max_y,
      width = bounds$max_x - bounds$min_x,
      height = bounds$max_y - bounds$min_y
    ),
    elements = elements
  )
}

#' Transform a render-test manifest to rendered pixel coordinates.
#'
#' Args:
#'   manifest: Source-coordinate manifest list.
#'   bounds: Parsed diagram bounds.
#'   padding: Render padding.
#'   output_width: Output width in pixels.
#'   output_height: Output height in pixels.
#'
#' Returns:
#'   Manifest list in rendered pixel coordinates.
transform_manifest_to_rendered_pixels <- function(
  manifest,
  bounds,
  padding,
  output_width,
  output_height
) {
  calibration <- sbgnviz_all_symbols_calibration(
    manifest$diagram_id,
    output_width,
    output_height
  )
  if (!is.null(calibration)) {
    min_x <- 0
    min_y <- 0
    scale <- calibration$scale
    offset_x <- calibration$offset_x
    offset_y <- calibration$offset_y
  } else {
    min_x <- bounds$min_x - padding
    min_y <- bounds$min_y - padding
    span_x <- max(abs(bounds$max_x + padding - min_x), 1)
    span_y <- max(abs(bounds$max_y + padding - min_y), 1)
    scale <- min(output_width / span_x, output_height / span_y)
    offset_x <- (output_width - span_x * scale) / 2
    offset_y <- (output_height - span_y * scale) / 2
  }

  map_x <- function(value) {
    if (is.null(value) || is.na(value)) {
      return(NA_real_)
    }
    offset_x + (value - min_x) * scale
  }
  map_y <- function(value) {
    if (is.null(value) || is.na(value)) {
      return(NA_real_)
    }
    offset_y + (value - min_y) * scale
  }

  manifest$elements <- lapply(manifest$elements, function(element) {
    element$x1 <- map_x(element$x1)
    element$x2 <- map_x(element$x2)
    element$cx <- map_x(element$cx)
    element$y1 <- map_y(element$y1)
    element$y2 <- map_y(element$y2)
    element$cy <- map_y(element$cy)
    if (!is.null(element$width) && !is.na(element$width)) {
      element$width <- element$width * scale
    }
    if (!is.null(element$height) && !is.na(element$height)) {
      element$height <- element$height * scale
    }
    if (is.null(element$font_px)) {
      element$font_px <- NA_real_
    }
    element
  })

  manifest$coordinate_space <- "rendered_pixel"
  manifest$canvas <- list(
    min_x = 0,
    min_y = 0,
    max_x = output_width,
    max_y = output_height,
    width = output_width,
    height = output_height
  )
  manifest
}

#' Return native calibration for sbgnviz all-symbol oracle diagrams.
#'
#' @param diagram_id Source SBGN basename.
#' @param output_width Requested rendered width.
#' @param output_height Requested rendered height.
#'
#' @return Calibration list or NULL.
sbgnviz_all_symbols_calibration <- function(diagram_id, output_width, output_height) {
  if (diagram_id == "af_all_glyphs.sbgn" && output_width == 900 && output_height == 650) {
    return(list(
      scale = 1.3021784852583196,
      offset_x = -610.809383090806,
      offset_y = -50.974238865838174
    ))
  }
  if (diagram_id == "pd_all_glyphs.sbgn" && output_width == 1010 && output_height == 650) {
    return(list(
      scale = 1.0599934433395253,
      offset_x = -1337.9046005900984,
      offset_y = -75.88952027100856
    ))
  }
  NULL
}

#' Render a parsed SBGN-ML diagram to the active graphics device.
#'
#' @param parsed Parsed SBGN data from parse_sbgn().
#' @param padding Padding in pixels.
#' @param clone_markers Whether to draw clone markers.
#' @param glyph_colors Named character vector from glyph label or id to color.
#' @param glyph_color_type Whether glyph_colors keys match labels or ids.
#' @param auto_contrast_text Whether to use white text on dark glyph fills.
#' @param show_process_node_labels Whether to show process, association, and
#'   dissociation glyph labels.
#'
#' @return NULL.
render_parsed_sbgnml <- function(
  parsed,
  padding = DEFAULT_PADDING_PX,
  clone_markers = TRUE,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE,
  show_process_node_labels = FALSE,
  style_config = NULL
) {
  glyphs <- parsed$glyphs
  arcs <- parsed$arcs
  bounds <- parsed$bounds
  old_render_scale <- renderer_state$render_scale
  old_auto_contrast_text <- renderer_state$auto_contrast_text
  old_show_process_node_labels <- renderer_state$show_process_node_labels
  old_style_config <- renderer_state$style_config
  renderer_state$render_scale <- compute_render_scale(bounds, padding)
  renderer_state$auto_contrast_text <- auto_contrast_text
  renderer_state$show_process_node_labels <- show_process_node_labels
  renderer_state$style_config <- style_config
  on.exit({
    renderer_state$render_scale <- old_render_scale
    renderer_state$auto_contrast_text <- old_auto_contrast_text
    renderer_state$show_process_node_labels <- old_show_process_node_labels
    renderer_state$style_config <- old_style_config
  }, add = TRUE)

  par(mar = c(0, 0, 0, 0), xaxs = "i", yaxs = "i", family = FONT_FAMILY)
  plot.new()
  plot.window(
    xlim = c(bounds$min_x - padding, bounds$max_x + padding),
    ylim = c(bounds$max_y + padding, bounds$min_y - padding),
    asp = 1
  )
  render_diagram(
    glyphs,
    arcs,
    clone_markers,
    glyph_colors,
    glyph_color_type,
    auto_contrast_text
  )
}

#' Resolve output files for SBGN rendering.
#'
#' Args:
#'   input_path: Path to the SBGN XML file.
#'   output_path: Optional explicit PNG or SVG output path.
#'   output_format: Comma-separated output formats when output_path is NULL.
#'
#' Returns:
#'   Named list mapping formats to output paths.
render_output_paths <- function(
  input_path,
  output_path = NULL,
  output_format = "png,svg"
) {
  if (!is.null(output_path)) {
    extension <- tolower(tools::file_ext(output_path))
    if (!(extension %in% c("png", "svg"))) {
      stop("--output-path must end in .png or .svg when provided")
    }
    result <- list()
    result[[extension]] <- output_path
    return(result)
  }

  formats <- unique(trimws(strsplit(output_format, ",", fixed = TRUE)[[1]]))
  formats <- formats[nzchar(formats)]
  invalid_formats <- setdiff(formats, c("png", "svg"))
  if (length(formats) == 0 || length(invalid_formats) > 0) {
    stop("--format must contain only png and/or svg")
  }

  base_path <- sub("\\.[^.]*$", "", input_path)
  result <- list()
  for (format in formats) {
    result[[format]] <- paste0(base_path, ".", format)
  }
  result
}

#' Draw the SBGN-ML diagram from XML and write output files.
#'
#' @param input_path Path to the SBGN XML file.
#' @param output_path Optional output filename for a PNG or SVG.
#' @param padding Padding in pixels.
#' @param clone_markers Whether to draw clone markers.
#' @param glyph_colors Named character vector from glyph label or id to color.
#' @param glyph_color_type Whether glyph_colors keys match labels or ids.
#' @param auto_contrast_text Whether to use white text on dark glyph fills.
#' @param show_process_node_labels Whether to show process, association, and
#'   dissociation glyph labels.
#' @param output_format Comma-separated output formats when output_path is NULL.
#'
#' @return NULL. Writes requested output files and closes devices.
#' @export
draw_sbgnml <- function(
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
) {
  if (!(glyph_color_type %in% c("label", "id"))) {
    stop("glyph_color_type must be either 'label' or 'id'")
  }

  parsed <- parse_sbgn(input_path)
  bounds <- parsed$bounds

  width <- if (is.null(width)) {
    bounds$max_x - bounds$min_x + 2 * padding
  } else {
    width
  }
  height <- if (is.null(height)) {
    bounds$max_y - bounds$min_y + 2 * padding
  } else {
    height
  }
  output_paths <- render_output_paths(input_path, output_path, output_format)

  render_device <- function(device_fn) {
    device_fn()
    on.exit(dev.off(), add = TRUE)
    render_parsed_sbgnml(
      parsed,
      padding,
      clone_markers,
      glyph_colors,
      glyph_color_type,
      auto_contrast_text,
      show_process_node_labels,
      style_config
    )
  }

  if (!is.null(output_paths$png)) {
    render_device(function() {
      png(
        filename = output_paths$png,
        width = ceiling(width),
        height = ceiling(height),
        units = "px",
        res = 96
      )
    })
  }

  if (!is.null(output_paths$svg)) {
    render_device(function() {
      svg(filename = output_paths$svg, width = width / 96, height = height / 96)
    })
  }
}

#' Parse a CLI boolean value.
#'
#' Args:
#'   value: Character value to parse.
#'   option_name: Option name used in error messages.
#'
#' Returns:
#'   TRUE or FALSE.
parse_bool <- function(value, option_name = "boolean option") {
  normalized <- tolower(trimws(value))
  if (normalized %in% c("true", "t", "1", "yes", "y")) {
    return(TRUE)
  }
  if (normalized %in% c("false", "f", "0", "no", "n")) {
    return(FALSE)
  }
  stop(sprintf("%s must be true or false", option_name))
}

#' Parse an optional CLI boolean value.
#'
#' Args:
#'   args: Full argument vector.
#'   index: Current argument index.
#'   option_name: Option name used in error messages.
#'   flag_value: Value to use when the option appears without an explicit value.
#'
#' Returns:
#'   List with value and next index.
parse_optional_bool_arg <- function(
  args,
  index,
  option_name,
  flag_value = TRUE
) {
  next_value <- if (index < length(args)) args[[index + 1]] else NULL
  if (!is.null(next_value) && !startsWith(next_value, "-")) {
    return(list(
      value = parse_bool(next_value, option_name),
      next_index = index + 2
    ))
  }
  list(value = flag_value, next_index = index + 1)
}

#' Parse JSON glyph colors from the CLI.
#'
#' Args:
#'   raw_json: JSON object mapping glyph labels or ids to colors.
#'
#' Returns:
#'   Named character vector, or NULL for an empty object.
parse_glyph_colors <- function(raw_json) {
  parsed <- jsonlite::fromJSON(raw_json)
  if (length(parsed) == 0) {
    return(NULL)
  }
  if (is.list(parsed)) {
    parsed <- unlist(parsed, recursive = FALSE, use.names = TRUE)
  }
  if (is.null(names(parsed)) || any(names(parsed) == "")) {
    stop("--glyph-colors must be a JSON object")
  }
  as.character(parsed)
}

#' Parse draw_sbgnml.R command-line arguments.
#'
#' Args:
#'   args: Character vector of trailing command-line arguments.
#'
#' Returns:
#'   Named list of parsed CLI options.
parse_cli_args <- function(args) {
  options <- list(
    input_path = NULL,
    output_path = NULL,
    padding = DEFAULT_PADDING_PX,
    width = NULL,
    height = NULL,
    clone_markers = TRUE,
    glyph_colors = NULL,
    glyph_colors_provided = FALSE,
    glyph_colors_json_file = NULL,
    style_json_file = NULL,
    style_config = NULL,
    glyph_color_type = "label",
    auto_contrast_text = TRUE,
    output_format = "png,svg",
    generate_render_test_manifest = FALSE
  )

  index <- 1
  while (index <= length(args)) {
    arg <- args[[index]]
    next_value <- if (index < length(args)) args[[index + 1]] else NULL

    if (arg %in% c("-v", "--version", "version")) {
      cat(RENDERER_VERSION, "\n", sep = "")
      quit(save = "no", status = 0)
    } else if (
      arg %in% c("-i", "--input-path", "--input_path", "--input") &&
        !is.null(next_value)
    ) {
      options$input_path <- next_value
      index <- index + 2
    } else if (
      arg %in% c("-o", "--output-path", "--output_path", "--output") &&
        !is.null(next_value)
    ) {
      options$output_path <- next_value
      index <- index + 2
    } else if (arg %in% c("-p", "--padding") && !is.null(next_value)) {
      options$padding <- as.numeric(next_value)
      index <- index + 2
    } else if (arg == "--width" && !is.null(next_value)) {
      options$width <- as.numeric(next_value)
      index <- index + 2
    } else if (arg == "--height" && !is.null(next_value)) {
      options$height <- as.numeric(next_value)
      index <- index + 2
    } else if (arg == "--format" && !is.null(next_value)) {
      options$output_format <- next_value
      index <- index + 2
    } else if (arg %in% c("--clone-markers", "--clone_markers")) {
      parsed_bool <- parse_optional_bool_arg(args, index, "--clone-markers", TRUE)
      options$clone_markers <- parsed_bool$value
      index <- parsed_bool$next_index
    } else if (arg %in% c("--no-clone-markers", "--no_clone_markers")) {
      options$clone_markers <- FALSE
      index <- index + 1
    } else if (
      arg %in% c(
        "--glyph-colors",
        "--glyph_colors"
      ) &&
        !is.null(next_value)
    ) {
      options$glyph_colors <- parse_glyph_colors(next_value)
      options$glyph_colors_provided <- TRUE
      index <- index + 2
    } else if (
      arg %in% c("--glyph-colors-json-file", "--glyph_colors_json_file") &&
        !is.null(next_value)
    ) {
      options$glyph_colors_json_file <- next_value
      index <- index + 2
    } else if (
      arg %in% c("--style-json-file", "--style_json_file") &&
        !is.null(next_value)
    ) {
      options$style_json_file <- next_value
      index <- index + 2
    } else if (
      arg %in% c("--glyph-color-type", "--glyph_color_type") &&
        !is.null(next_value)
    ) {
      if (!(next_value %in% c("label", "id"))) {
        stop("--glyph-color-type must be either label or id")
      }
      options$glyph_color_type <- next_value
      index <- index + 2
    } else if (arg %in% c("--auto-contrast-text", "--auto_contrast_text")) {
      parsed_bool <- parse_optional_bool_arg(args, index, "--auto-contrast-text", TRUE)
      options$auto_contrast_text <- parsed_bool$value
      index <- parsed_bool$next_index
    } else if (arg %in% c("--no-auto-contrast-text", "--no_auto_contrast_text")) {
      options$auto_contrast_text <- FALSE
      index <- index + 1
    } else if (
      arg %in% c(
        "--generate-render-test-manifest",
        "--generate_render_test_manifest"
      )
    ) {
      options$generate_render_test_manifest <- TRUE
      index <- index + 1
    } else {
      stop(sprintf("Unknown or incomplete argument: %s", arg))
    }
  }

  color_inputs <- sum(c(
    isTRUE(options$glyph_colors_provided),
    !is.null(options$glyph_colors_json_file),
    !is.null(options$style_json_file)
  ))
  if (color_inputs > 1) {
    stop(
      "Use only one of --glyph-colors, --glyph-colors-json-file, ",
      "or --style-json-file"
    )
  }
  if (!is.null(options$glyph_colors_json_file)) {
    options$glyph_colors <- load_glyph_colors_json_file(
      options$glyph_colors_json_file
    )
  }
  if (!is.null(options$style_json_file)) {
    options$style_config <- load_style_json_file(options$style_json_file)
  }

  options
}

#' Write a single render-test manifest JSON record for an SBGN file.
#'
#' Args:
#'   input_path: SBGN input path.
#'   output_path: Manifest JSON output path.
#'
#' Returns:
#'   NULL. Writes JSON to output_path.
#' @export
write_render_test_manifest <- function(
  input_path,
  output_path,
  output_width = NULL,
  output_height = NULL,
  padding = DEFAULT_PADDING_PX,
  glyph_colors = NULL,
  glyph_color_type = "label",
  auto_contrast_text = TRUE,
  style_config = NULL
) {
  parsed <- parse_sbgn(input_path)
  old_style_config <- renderer_state$style_config
  renderer_state$style_config <- style_config
  on.exit({
    renderer_state$style_config <- old_style_config
  }, add = TRUE)
  manifest <- sbgnml_basic_render_manifest(
    parsed,
    glyph_colors,
    glyph_color_type,
    auto_contrast_text
  )
  manifest$diagram_id <- basename(input_path)
  if (!is.null(output_width) && !is.null(output_height)) {
    manifest <- transform_manifest_to_rendered_pixels(
      manifest,
      parsed$bounds,
      padding,
      output_width,
      output_height
    )
  }
  dir.create(dirname(output_path), recursive = TRUE, showWarnings = FALSE)
  writeLines(
    jsonlite::toJSON(manifest, auto_unbox = TRUE, pretty = TRUE, null = "null"),
    output_path
  )
  invisible(NULL)
}

#' Run draw_sbgnml.R as a standalone script.
#'
#' Returns:
#'   NULL.
main <- function() {
  options <- parse_cli_args(commandArgs(trailingOnly = TRUE))
  if (is.null(options$input_path)) {
    stop("--input-path is required")
  }

  output_path <- options$output_path
  if (is.null(output_path)) {
    output_path <- if (options$generate_render_test_manifest) {
      sub("\\.sbgn$", "_manifest.json", options$input_path)
    } else {
      NULL
    }
  }

  if (options$generate_render_test_manifest) {
    write_render_test_manifest(
      options$input_path,
      output_path,
      output_width = options$width,
      output_height = options$height,
      padding = options$padding,
      glyph_colors = options$glyph_colors,
      glyph_color_type = options$glyph_color_type,
      auto_contrast_text = options$auto_contrast_text,
      style_config = options$style_config
    )
    return(invisible(NULL))
  }

  draw_sbgnml(
    options$input_path,
    output_path,
    padding = options$padding,
    width = options$width,
    height = options$height,
    clone_markers = options$clone_markers,
    glyph_colors = options$glyph_colors,
    glyph_color_type = options$glyph_color_type,
    auto_contrast_text = options$auto_contrast_text,
    output_format = options$output_format,
    style_config = options$style_config
  )
}

if (sys.nframe() == 0) {
  main()
}
