# Render SBGN-ML diagrams using base R graphics and xml2.
# This script mirrors the sbgn-rust renderer using only base R + xml2.

suppressPackageStartupMessages(library(xml2))

# Configuration constants for layout and styling.
DEFAULT_PADDING_PX <- 10
DEFAULT_LINE_WIDTH <- 1.5
FONT_MAIN_PX <- 20
FONT_SMALL_PX <- 12
FONT_BASE_PX <- 12
FONT_FAMILY <- "Liberation Sans"
ARROW_SIZE <- 8
ARROW_SCALE <- 1.75
BAR_LENGTH <- 12
BAR_OFFSET <- 14
CATALYSIS_OVERLAP_RATIO <- 0.5
PORT_CONNECTOR_LEN_PX <- 11
LOGICAL_PORT_CONNECTOR_LEN_PX <- 20

BORDER_COLOR <- rgb(0x55, 0x55, 0x55, maxColorValue = 255)
DEFAULT_FILL_COLOR <- rgb(0xF6, 0xF6, 0xF6, maxColorValue = 255)
AUX_LINE_COLOR <- rgb(0x6A, 0x6A, 0x6A, maxColorValue = 255)
ASSOCIATION_FILL_COLOR <- rgb(0x6B, 0x6B, 0x6B, maxColorValue = 255)
CLONE_FILL_COLOR <- rgb(0xD1, 0xD1, 0xD1, maxColorValue = 255)
CLONE_MARKER_HEIGHT_RATIO <- 0.30
CLONE_MARKER_STROKE_WIDTH <- 1.5

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
  font_px / FONT_BASE_PX
}

#' Build a state variable label in value@variable format.
#'
#' @param value State value.
#' @param variable State variable name.
#'
#' @return Combined label string.
state_var_label <- function(value, variable) {
  if (!is.null(value) && !is.null(variable) && value != "" && variable != "") {
    return(sprintf("%s@%s", value, variable))
  }
  if (!is.null(value) && value != "") {
    return(value)
  }
  if (!is.null(variable) && variable != "") {
    return(variable)
  }
  ""
}

#' Compute bounds from glyphs and arcs.
#'
#' @param glyphs List of glyph data.
#' @param arcs List of arc data.
#'
#' @return Named list with min_x, max_x, min_y, max_y.
compute_bounds <- function(glyphs, arcs) {
  x_values <- numeric(0)
  y_values <- numeric(0)

  for (glyph in glyphs) {
    bbox <- glyph$bbox
    if (!is.null(bbox) && !is.na(bbox$x)) {
      x_values <- c(x_values, bbox$x, bbox$x + bbox$w)
      y_values <- c(y_values, bbox$y, bbox$y + bbox$h)
    }
    if (!is.null(glyph$ports) && nrow(glyph$ports) > 0) {
      x_values <- c(x_values, glyph$ports$x)
      y_values <- c(y_values, glyph$ports$y)
    }
  }

  for (arc in arcs) {
    x_values <- c(x_values, arc$points$x)
    y_values <- c(y_values, arc$points$y)
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
    return(data.frame(x = numeric(0), y = numeric(0)))
  }
  data.frame(
    x = as.numeric(xml_attr(ports, "x")),
    y = as.numeric(xml_attr(ports, "y"))
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
  ports <- extract_ports(glyph, ns)
  has_clone <- length(xml_find_all(glyph, "./sbgn:clone", ns)) > 0
  state_node <- xml_find_first(glyph, "./sbgn:state", ns)
  state_value <- xml_attr(state_node, "value")
  state_variable <- xml_attr(state_node, "variable")
  orientation <- xml_attr(glyph, "orientation")

  record <- list(
    id = id,
    parent_id = parent_id,
    class = class_name,
    bbox = bbox,
    label = label,
    ports = ports,
    has_clone = has_clone,
    state_value = if (is.na(state_value)) NULL else state_value,
    state_variable = if (is.na(state_variable)) NULL else state_variable,
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

  map_node <- xml_find_first(doc, ".//sbgn:map", ns)
  if (length(map_node) == 0) {
    stop("SBGN file missing map element")
  }

  glyph_nodes <- xml_find_all(map_node, "./sbgn:glyph", ns)
  arc_nodes <- xml_find_all(doc, ".//sbgn:arc", ns)

  glyphs <- list()
  for (glyph in glyph_nodes) {
    glyphs <- c(glyphs, parse_glyph_node(glyph, ns, parent_id = NULL))
  }

  arcs <- list()
  for (arc in arc_nodes) {
    arcs <- c(arcs, list(list(
      id = xml_attr(arc, "id"),
      class = xml_attr(arc, "class"),
      points = extract_arc_points(arc, ns)
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
quad_curve_points <- function(p0, p1, p2, n = 12) {
  t <- seq(0, 1, length.out = n)
  data.frame(
    x = (1 - t)^2 * p0$x + 2 * (1 - t) * t * p1$x + t^2 * p2$x,
    y = (1 - t)^2 * p0$y + 2 * (1 - t) * t * p1$y + t^2 * p2$y
  )
}

#' Arc points for a rounded corner.
#'
#' @param cx Center x.
#' @param cy Center y.
#' @param r Radius.
#' @param start_angle Start angle in radians.
#' @param end_angle End angle in radians.
#' @param n Points to sample.
#'
#' @return Data frame with x and y.
arc_points <- function(cx, cy, r, start_angle, end_angle, n = 12) {
  theta <- seq(start_angle, end_angle, length.out = n)
  data.frame(x = cx + r * cos(theta), y = cy + r * sin(theta))
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
round_bottom_rect_points <- function(x0, y0, x1, y1, radius) {
  r <- min(radius, (x1 - x0) / 2, (y1 - y0) / 2)
  rbind(
    data.frame(x = x0, y = y0),
    data.frame(x = x1, y = y0),
    data.frame(x = x1, y = y1 - r),
    arc_points(x1 - r, y1 - r, r, 0, pi / 2, 12),
    data.frame(x = x0 + r, y = y1),
    arc_points(x0 + r, y1 - r, r, pi / 2, pi, 12),
    data.frame(x = x0, y = y0)
  )
}

#' Cut corner rectangle polygon points.
#'
#' @param rect Pixel rect list.
#' @param corner Corner size.
#'
#' @return Data frame with x and y.
cut_rect_points <- function(rect, corner) {
  x0 <- rect$x0
  y0 <- rect$y0
  x1 <- rect$x0 + rect$width
  y1 <- rect$y0 + rect$height
  data.frame(
    x = c(x0, x0 + corner, x1 - corner, x1, x1, x1 - corner, x0 + corner, x0),
    y = c(y0 + corner, y0, y0, y0 + corner, y1 - corner, y1, y1, y1 - corner)
  )
}

#' Hexagon polygon points.
#'
#' @param rect Pixel rect list.
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

#' Concave hexagon polygon points.
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
concave_hexagon_points <- function(rect) {
  x0 <- rect$x0
  y0 <- rect$y0
  w <- rect$width
  h <- rect$height
  data.frame(
    x = c(x0, x0 + w, x0 + 0.85 * w, x0 + w, x0, x0 + 0.15 * w),
    y = c(y0, y0, y0 + 0.5 * h, y0 + h, y0 + h, y0 + 0.5 * h)
  )
}

#' Barrel polygon points (approximate SBGN compartment).
#'
#' @param rect Pixel rect list.
#'
#' @return Data frame with x and y.
barrel_points <- function(rect) {
  x <- rect$x0
  y <- rect$y0
  w <- rect$width
  h <- rect$height
  top_y <- y + 0.03 * h
  bottom_y <- y + 0.97 * h

  points <- data.frame(x = numeric(0), y = numeric(0))
  p0 <- list(x = x, y = top_y)
  points <- rbind(points, data.frame(x = p0$x, y = p0$y))

  p1 <- list(x = x, y = bottom_y)
  points <- rbind(points, data.frame(x = p1$x, y = p1$y))

  curve1 <- quad_curve_points(
    p1,
    list(x = x + 0.06 * w, y = y + h),
    list(x = x + 0.25 * w, y = y + h)
  )
  points <- rbind(points, curve1[-1, ])

  p2 <- list(x = x + 0.75 * w, y = y + h)
  points <- rbind(points, data.frame(x = p2$x, y = p2$y))

  curve2 <- quad_curve_points(
    p2,
    list(x = x + 0.95 * w, y = y + h),
    list(x = x + w, y = y + 0.95 * h)
  )
  points <- rbind(points, curve2[-1, ])

  p3 <- list(x = x + w, y = y + 0.05 * h)
  points <- rbind(points, data.frame(x = p3$x, y = p3$y))

  curve3 <- quad_curve_points(
    p3,
    list(x = x + w, y = y),
    list(x = x + 0.75 * w, y = y)
  )
  points <- rbind(points, curve3[-1, ])

  p4 <- list(x = x + 0.25 * w, y = y)
  points <- rbind(points, data.frame(x = p4$x, y = p4$y))

  curve4 <- quad_curve_points(
    p4,
    list(x = x + 0.06 * w, y = y),
    list(x = x, y = top_y)
  )
  points <- rbind(points, curve4[-1, ])
  points
}

#' Tag polygon points.
#'
#' @param rect Pixel rect list.
#' @param notch Notch size.
#'
#' @return Data frame with x and y.
tag_points <- function(rect, notch) {
  x0 <- rect$x0
  y0 <- rect$y0
  x1 <- rect$x0 + rect$width
  y1 <- rect$y0 + rect$height
  mid_y <- (y0 + y1) / 2
  data.frame(
    x = c(x0 + notch, x1, x1, x0 + notch, x0),
    y = c(y0, y0, y1, y1, mid_y)
  )
}

#' Clip polygon points to a horizontal line y >= y_cut.
#'
#' @param points Data frame with x and y.
#' @param y_cut Cutoff y value.
#'
#' @return Data frame of clipped points (possibly empty).
clip_polygon_y <- function(points, y_cut) {
  if (nrow(points) == 0) {
    return(points)
  }
  output <- data.frame(x = numeric(0), y = numeric(0))
  n <- nrow(points)
  for (idx in seq_len(n)) {
    p1 <- points[idx, ]
    p2 <- points[ifelse(idx == n, 1, idx + 1), ]
    inside1 <- p1$y >= y_cut
    inside2 <- p2$y >= y_cut

    if (inside1 && inside2) {
      output <- rbind(output, p2)
    } else if (inside1 && !inside2) {
      if (p2$y != p1$y) {
        t <- (y_cut - p1$y) / (p2$y - p1$y)
        x_int <- p1$x + t * (p2$x - p1$x)
        output <- rbind(output, data.frame(x = x_int, y = y_cut))
      }
    } else if (!inside1 && inside2) {
      if (p2$y != p1$y) {
        t <- (y_cut - p1$y) / (p2$y - p1$y)
        x_int <- p1$x + t * (p2$x - p1$x)
        output <- rbind(output, data.frame(x = x_int, y = y_cut))
      }
      output <- rbind(output, p2)
    }
  }
  output
}

#' Draw centered text.
#'
#' @param x Center x.
#' @param y Center y.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_text_centered <- function(x, y, label, font_px) {
  if (is.null(label) || trimws(label) == "") {
    return(invisible(NULL))
  }
  text(x, y, labels = label, cex = font_px_to_cex(font_px))
}

#' Draw text aligned to the bottom center of a rectangle.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_text_bottom_centered <- function(rect, label, font_px) {
  if (is.null(label) || trimws(label) == "") {
    return(invisible(NULL))
  }
  label_height <- strheight(label, units = "user", cex = font_px_to_cex(font_px))
  x <- rect$center$x
  y <- rect$y0 + rect$height - label_height / 2 - 2
  text(x, y, labels = label, cex = font_px_to_cex(font_px))
}

#' Draw a polygon shape with fill and border.
#'
#' @param points Data frame with x and y.
#' @param fill Fill color.
#' @param border Border color.
#' @param lwd Line width.
#'
#' @return NULL.
draw_polygon_shape <- function(points, fill, border, lwd) {
  polygon(points$x, points$y, col = fill, border = border, lwd = lwd)
}

#' Draw clone marker overlay inside a polygon.
#'
#' @param points Polygon points.
#' @param band_fraction Fractional height for clone band.
#'
#' @return NULL.
draw_clone_marker <- function(points, band_fraction = CLONE_MARKER_HEIGHT_RATIO) {
  y_cut <- max(points$y) - (max(points$y) - min(points$y)) * band_fraction
  clipped <- clip_polygon_y(points, y_cut)
  if (nrow(clipped) > 2) {
    polygon(
      clipped$x,
      clipped$y,
      col = CLONE_FILL_COLOR,
      border = AUX_LINE_COLOR,
      lwd = max(CLONE_MARKER_STROKE_WIDTH, 1)
    )
  }
}

#' Draw a generic shape with optional clone marker and centered label.
#'
#' @param points Polygon points.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param has_clone Whether to draw clone marker.
#' @param fill_color Fill color.
#' @param border_width Border line width.
#'
#' @return NULL.
draw_shape_with_clone <- function(points, label, font_px, has_clone, fill_color, border_width) {
  draw_polygon_shape(points, fill_color, BORDER_COLOR, border_width)
  if (has_clone) {
    draw_clone_marker(points)
    draw_polygon_shape(points, NA, BORDER_COLOR, border_width)
  }
  center_x <- mean(range(points$x))
  center_y <- mean(range(points$y))
  draw_text_centered(center_x, center_y, label, font_px)
}

#' Draw an ellipse with fill and border.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param fill_color Fill color.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_ellipse_bbox <- function(rect, label, font_px, fill_color, border_width, has_clone) {
  points <- ellipse_points(rect$center$x, rect$center$y, rect$width / 2, rect$height / 2, 80)
  draw_shape_with_clone(points, label, font_px, has_clone, fill_color, border_width)
}

#' Draw a rectangle bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_rect_bbox <- function(rect, label, font_px, border_width, has_clone) {
  points <- data.frame(
    x = c(rect$x0, rect$x0 + rect$width, rect$x0 + rect$width, rect$x0),
    y = c(rect$y0, rect$y0, rect$y0 + rect$height, rect$y0 + rect$height)
  )
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a rounded rectangle bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_round_rect_bbox <- function(rect, label, font_px, border_width, has_clone) {
  radius <- max(1, min(rect$width, rect$height) * 0.1)
  points <- round_rect_points(rect$x0, rect$y0, rect$x0 + rect$width, rect$y0 + rect$height, radius)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a stadium (capsule) bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_stadium_bbox <- function(rect, label, font_px, border_width, has_clone) {
  radius <- 0.24 * max(rect$width, rect$height)
  points <- round_rect_points(rect$x0, rect$y0, rect$x0 + rect$width, rect$y0 + rect$height, radius)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a hexagon bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_hexagon_bbox <- function(rect, label, font_px, border_width, has_clone) {
  points <- hexagon_points(rect)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a concave hexagon bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_concave_hexagon_bbox <- function(rect, label, font_px, border_width, has_clone) {
  points <- concave_hexagon_points(rect)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a cut-corner rectangle bbox (complex).
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_cut_rect_bbox <- function(rect, label, font_px, border_width, has_clone) {
  corner <- max(1, min(rect$width, rect$height) * 0.2)
  points <- cut_rect_points(rect, corner)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a barrel bbox (compartment).
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_barrel_bbox <- function(rect, label, font_px, border_width, has_clone) {
  points <- barrel_points(rect)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a tag bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_tag_bbox <- function(rect, label, font_px, border_width, has_clone) {
  notch <- max(2, rect$height * 0.3)
  points <- tag_points(rect, notch)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a round-bottom rectangle bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param border_width Border line width.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_round_bottom_rect_bbox <- function(rect, label, font_px, border_width, has_clone) {
  radius <- max(1, rect$height * 0.3)
  points <- round_bottom_rect_points(rect$x0, rect$y0, rect$x0 + rect$width, rect$y0 + rect$height, radius)
  draw_shape_with_clone(points, label, font_px, has_clone, DEFAULT_FILL_COLOR, border_width)
}

#' Draw a circle bbox.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_circle_bbox <- function(rect, label, font_px) {
  radius <- min(rect$width, rect$height) / 2
  points <- ellipse_points(rect$center$x, rect$center$y, radius, radius, 80)
  draw_shape_with_clone(points, label, font_px, FALSE, DEFAULT_FILL_COLOR, DEFAULT_LINE_WIDTH)
}

#' Draw a source/sink glyph.
#'
#' @param rect Pixel rect list.
#' @param has_clone Whether to draw clone marker.
#'
#' @return NULL.
draw_source_sink_bbox <- function(rect, has_clone) {
  points <- ellipse_points(rect$center$x, rect$center$y, rect$width / 2, rect$height / 2, 80)
  draw_shape_with_clone(points, "", FONT_SMALL_PX, has_clone, DEFAULT_FILL_COLOR, DEFAULT_LINE_WIDTH)
  segments(rect$x0, rect$y0 + rect$height, rect$x0 + rect$width, rect$y0, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
}

#' Draw a dissociation glyph (double circle).
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_double_circle_bbox <- function(rect, label, font_px) {
  radius <- min(rect$width, rect$height) / 2
  points <- ellipse_points(rect$center$x, rect$center$y, radius, radius, 80)
  draw_shape_with_clone(points, "", FONT_SMALL_PX, FALSE, DEFAULT_FILL_COLOR, DEFAULT_LINE_WIDTH)
  inner_radius <- radius * 0.6
  symbols(rect$center$x, rect$center$y, circles = inner_radius, inches = FALSE,
          add = TRUE, fg = BORDER_COLOR, bg = NA, lwd = DEFAULT_LINE_WIDTH)
  draw_text_centered(rect$center$x, rect$center$y, label, font_px)
}

#' Draw an association glyph (filled circle).
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_association_bbox <- function(rect, label, font_px) {
  symbols(rect$center$x, rect$center$y, circles = min(rect$width, rect$height) / 2, inches = FALSE,
          add = TRUE, fg = BORDER_COLOR, bg = ASSOCIATION_FILL_COLOR, lwd = DEFAULT_LINE_WIDTH)
  draw_text_centered(rect$center$x, rect$center$y, label, font_px)
}

#' Draw a square bbox for process nodes.
#'
#' @param bbox Bounding box list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return NULL.
draw_square_bbox <- function(bbox, label, font_px) {
  side <- min(bbox$w, bbox$h)
  x0 <- bbox$x + bbox$w / 2 - side / 2
  y0 <- bbox$y + bbox$h / 2 - side / 2
  rect(x0, y0, x0 + side, y0 + side, col = DEFAULT_FILL_COLOR, border = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  draw_text_centered(x0 + side / 2, y0 + side / 2, label, font_px)
}

#' Draw orientation marker lines for certain glyphs.
#'
#' @param rect Pixel rect list.
#' @param orientation Orientation string.
#' @param connector_len_px Connector length in pixels.
#'
#' @return NULL.
draw_orientation_marker <- function(rect, orientation, connector_len_px = PORT_CONNECTOR_LEN_PX) {
  if (is.null(orientation)) {
    return(invisible(NULL))
  }
  if (orientation == "vertical") {
    segments(rect$center$x, rect$y0 - connector_len_px, rect$center$x, rect$y0, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
    segments(rect$center$x, rect$y0 + rect$height, rect$center$x, rect$y0 + rect$height + connector_len_px, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  } else if (orientation == "horizontal") {
    segments(rect$x0 - connector_len_px, rect$center$y, rect$x0, rect$center$y, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
    segments(rect$x0 + rect$width, rect$center$y, rect$x0 + rect$width + connector_len_px, rect$center$y, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  } else if (orientation == "left") {
    segments(rect$x0 - connector_len_px, rect$center$y, rect$x0, rect$center$y, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  } else if (orientation == "right") {
    segments(rect$x0 + rect$width, rect$center$y, rect$x0 + rect$width + connector_len_px, rect$center$y, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  } else if (orientation == "up") {
    segments(rect$center$x, rect$y0 - connector_len_px, rect$center$x, rect$y0, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  } else if (orientation == "down") {
    segments(rect$center$x, rect$y0 + rect$height, rect$center$x, rect$y0 + rect$height + connector_len_px, col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  }
}

#' Draw a horizontal overlay line at a specific y offset.
#'
#' @param rect Pixel rect list.
#' @param y Y coordinate.
#' @param line_width Line width.
#' @param color Line color.
#'
#' @return NULL.
draw_overlay_line <- function(rect, y, line_width, color) {
  segments(rect$x0, y, rect$x0 + rect$width, y, col = color, lwd = line_width)
}

#' Measure label width in user units.
#'
#' @param label Text label.
#' @param font_px Font size in pixels.
#'
#' @return Width in user units.
measure_text_width <- function(label, font_px) {
  strwidth(label, units = "user", cex = font_px_to_cex(font_px))
}

#' Draw a unit of information box.
#'
#' @param x X coordinate.
#' @param y Y coordinate.
#' @param height Height in user units.
#' @param label Text label.
#' @param border_width Border width.
#' @param font_px Font size in pixels.
#' @param padding_px Padding in user units.
#'
#' @return NULL.
draw_unit_info <- function(x, y, height, label, border_width, font_px, padding_px) {
  text_width <- measure_text_width(label, font_px)
  width <- max(text_width + padding_px, 10)
  rect_obj <- list(x0 = x, y0 = y, width = width, height = height, center = list(x = x + width / 2, y = y + height / 2))
  points <- round_rect_points(x, y, x + width, y + height, width * 0.04)
  draw_polygon_shape(points, "white", BORDER_COLOR, border_width)
  draw_text_centered(rect_obj$center$x, rect_obj$center$y, label, font_px)
}

#' Draw a state variable box.
#'
#' @param x X coordinate.
#' @param y Y coordinate.
#' @param height Height in user units.
#' @param label Text label.
#' @param border_width Border width.
#' @param font_px Font size in pixels.
#' @param padding_px Padding in user units.
#' @param min_width Minimum width.
#'
#' @return NULL.
draw_state_var <- function(x, y, height, label, border_width, font_px, padding_px, min_width) {
  text_width <- measure_text_width(label, font_px)
  width <- max(text_width + padding_px, min_width)
  rect_obj <- list(x0 = x, y0 = y, width = width, height = height, center = list(x = x + width / 2, y = y + height / 2))
  radius <- 0.24 * max(width, height)
  points <- round_rect_points(x, y, x + width, y + height, radius)
  draw_polygon_shape(points, "white", BORDER_COLOR, border_width)
  draw_text_centered(rect_obj$center$x, rect_obj$center$y, label, font_px)
}

#' Convert an x offset in px units to the node's pixel space.
#'
#' @param rect Pixel rect list.
#' @param value Offset value.
#' @param scale_x Scale factor.
#'
#' @return X coordinate.
px_x <- function(rect, value, scale_x) {
  rect$x0 + value * scale_x
}

#' Convert a y offset in px units to the node's pixel space.
#'
#' @param rect Pixel rect list.
#' @param value Offset value.
#' @param scale_y Scale factor.
#'
#' @return Y coordinate.
px_y <- function(rect, value, scale_y) {
  rect$y0 + value * scale_y
}

#' Return default widths/heights from sbgnStyle for scale reference.
#'
#' @param class_name Glyph class name.
#'
#' @return Numeric vector of width/height or NULL.
default_dimensions <- function(class_name) {
  if (class_name == "unspecified entity") {
    return(c(32, 32))
  }
  if (class_name %in% c("simple chemical", "simple chemical multimer")) {
    return(c(48, 48))
  }
  if (class_name %in% c("macromolecule", "macromolecule multimer")) {
    return(c(96, 48))
  }
  if (class_name == "nucleic acid feature") {
    return(c(88, 56))
  }
  if (class_name == "nucleic acid feature multimer") {
    return(c(88, 52))
  }
  if (class_name %in% c("complex", "complex multimer")) {
    return(c(10, 10))
  }
  if (class_name == "source and sink") {
    return(c(60, 60))
  }
  if (class_name == "perturbing agent") {
    return(c(140, 60))
  }
  if (class_name == "phenotype") {
    return(c(140, 60))
  }
  if (class_name %in% c("process", "uncertain process", "omitted process")) {
    return(c(25, 25))
  }
  if (class_name %in% c("association", "dissociation")) {
    return(c(25, 25))
  }
  if (class_name == "compartment") {
    return(c(50, 50))
  }
  if (class_name == "tag") {
    return(c(100, 65))
  }
  if (class_name %in% c("and", "or", "not")) {
    return(c(40, 40))
  }
  NULL
}

#' Return ghost offsets for multimer nodes.
#'
#' @param class_name Glyph base class name.
#'
#' @return Numeric vector of dx, dy or NULL.
ghost_offset_for <- function(class_name) {
  if (class_name == "simple chemical") {
    return(c(5, 5))
  }
  if (class_name %in% c("macromolecule", "nucleic acid feature")) {
    return(c(12, 12))
  }
  if (class_name == "complex") {
    return(c(16, 16))
  }
  NULL
}

#' Return border widths for entity pool nodes.
#'
#' @param class_name Glyph class name.
#'
#' @return Border width.
entity_pool_border_width <- function(class_name) {
  if (class_name == "complex") {
    return(4)
  }
  2
}

#' Draw auxiliary overlays (unit info, state vars) for entity pool nodes.
#'
#' @param rect Pixel rect list.
#' @param class_name Glyph class name.
#' @param u_info_label Unit of information label.
#' @param s_var_label State variable label.
#'
#' @return NULL.
draw_entity_pool_aux_items <- function(rect, class_name, u_info_label, s_var_label) {
  ref_dims <- default_dimensions(class_name)
  if (is.null(ref_dims)) {
    ref_dims <- c(rect$width, rect$height)
  }
  scale_x <- rect$width / ref_dims[1]
  scale_y <- rect$height / ref_dims[2]
  scale <- (scale_x + scale_y) / 2

  aux_item_height <- 20 * scale_y
  border_width <- 2 * scale
  font_px <- 10 * scale
  clone_shrink_y <- 3 * scale_y
  u_info_height <- aux_item_height - clone_shrink_y

  if (class_name == "simple chemical") {
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 8, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 52, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(px_x(rect, 12, scale_x), px_y(rect, 0, scale_y), u_info_height, u_info_label, border_width, font_px, 5 * scale)
    }
  } else if (class_name == "unspecified entity") {
    if (!is.null(u_info_label) || !is.null(s_var_label)) {
      draw_overlay_line(rect, px_y(rect, 8, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 52, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(px_x(rect, 20, scale_x), px_y(rect, 44, scale_y), u_info_height, u_info_label, border_width, font_px, 5 * scale)
    }
    if (!is.null(s_var_label)) {
      draw_state_var(px_x(rect, 40, scale_x), rect$y0, u_info_height, s_var_label, border_width, font_px, 10 * scale, 30 * scale)
    }
  } else if (class_name == "macromolecule") {
    if (!is.null(u_info_label) || !is.null(s_var_label)) {
      draw_overlay_line(rect, px_y(rect, 8, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 52, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(px_x(rect, 20, scale_x), px_y(rect, 44, scale_y), u_info_height, u_info_label, border_width, font_px, 5 * scale)
    }
    if (!is.null(s_var_label)) {
      draw_state_var(px_x(rect, 40, scale_x), rect$y0, u_info_height, s_var_label, border_width, font_px, 10 * scale, 30 * scale)
    }
  } else if (class_name == "nucleic acid feature") {
    if (!is.null(s_var_label)) {
      draw_overlay_line(rect, px_y(rect, 8, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 52, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(px_x(rect, 20, scale_x), px_y(rect, 44, scale_y), u_info_height, u_info_label, border_width, font_px, 5 * scale)
    }
    if (!is.null(s_var_label)) {
      draw_state_var(px_x(rect, 40, scale_x), rect$y0, u_info_height, s_var_label, border_width, font_px, 10 * scale, 30 * scale)
    }
  } else if (class_name == "complex") {
    if (!is.null(u_info_label) || !is.null(s_var_label)) {
      draw_overlay_line(rect, px_y(rect, 11, scale_y), 6 * scale, BORDER_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(rect$x0 + rect$width * 0.25, rect$y0, 24 * scale_y - clone_shrink_y, u_info_label, border_width, font_px, 5 * scale)
    }
    if (!is.null(s_var_label)) {
      draw_state_var(rect$x0 + rect$width * 0.88, rect$y0, 24 * scale_y - clone_shrink_y, s_var_label, border_width, font_px, 10 * scale, 30 * scale)
    }
  } else if (class_name == "perturbing agent") {
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 8, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_overlay_line(rect, px_y(rect, 56, scale_y), 1 * scale, AUX_LINE_COLOR)
    }
    if (!is.null(u_info_label)) {
      draw_unit_info(px_x(rect, 20, scale_x), rect$y0, u_info_height, u_info_label, border_width, font_px, 5 * scale)
    }
  }
}

#' Draw an entity pool node (with optional multimer ghost and overlays).
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param class_name Base class name.
#' @param has_clone Whether glyph has clone marker.
#' @param is_multimer Whether glyph is a multimer.
#' @param has_clone Whether glyph has clone marker.
#' @param u_info_label Unit of information label.
#' @param s_var_label State variable label.
#'
#' @return NULL.
draw_entity_pool_node <- function(rect, label, font_px, class_name, is_multimer, has_clone, u_info_label, s_var_label) {
  ref_dims <- default_dimensions(class_name)
  if (is.null(ref_dims)) {
    ref_dims <- c(rect$width, rect$height)
  }
  scale_x <- rect$width / ref_dims[1]
  scale_y <- rect$height / ref_dims[2]

  if (is_multimer) {
    ghost_offset <- ghost_offset_for(class_name)
    if (!is.null(ghost_offset)) {
      ghost_rect <- list(
        x0 = rect$x0 + ghost_offset[1] * scale_x,
        y0 = rect$y0 + ghost_offset[2] * scale_y,
        width = rect$width,
        height = rect$height,
        center = list(x = rect$center$x + ghost_offset[1] * scale_x, y = rect$center$y + ghost_offset[2] * scale_y)
      )
      draw_entity_pool_base_shape(ghost_rect, "", FONT_SMALL_PX, class_name, FALSE)
    }
  }

  draw_entity_pool_base_shape(rect, label, font_px, class_name, has_clone)
  draw_entity_pool_aux_items(rect, class_name, u_info_label, s_var_label)
}

#' Draw the base shape for an entity pool node.
#'
#' @param rect Pixel rect list.
#' @param label Text label.
#' @param font_px Font size in pixels.
#' @param class_name Base class name.
#'
#' @return NULL.
draw_entity_pool_base_shape <- function(rect, label, font_px, class_name, has_clone) {
  border_width <- entity_pool_border_width(class_name)
  if (class_name %in% c("simple chemical", "unspecified entity")) {
    draw_ellipse_bbox(rect, label, font_px, DEFAULT_FILL_COLOR, border_width, has_clone)
  } else if (class_name == "macromolecule") {
    draw_round_rect_bbox(rect, label, font_px, border_width, has_clone)
  } else if (class_name == "nucleic acid feature") {
    draw_round_bottom_rect_bbox(rect, label, font_px, border_width, has_clone)
  } else if (class_name == "complex") {
    draw_cut_rect_bbox(rect, label, font_px, border_width, has_clone)
  } else if (class_name == "perturbing agent") {
    draw_concave_hexagon_bbox(rect, label, font_px, border_width, has_clone)
  } else {
    draw_rect_bbox(rect, label, font_px, border_width, has_clone)
  }
}

#' Determine font size for a glyph class.
#'
#' @param class_name Glyph class name.
#'
#' @return Font size in pixels.
glyph_font_px <- function(class_name) {
  if (class_name %in% c("state variable", "unit of information", "cardinality", "variable value", "tag", "terminal")) {
    return(FONT_SMALL_PX)
  }
  FONT_MAIN_PX
}

#' Get the first child label of a class.
#'
#' @param children Child glyph list.
#' @param class_name Child class name.
#'
#' @return Label string or NULL.
first_child_label <- function(children, class_name) {
  for (child in children) {
    if (child$class == class_name && trimws(child$label) != "") {
      return(child$label)
    }
  }
  NULL
}

#' Get the first child state label of a class.
#'
#' @param children Child glyph list.
#' @param class_name Child class name.
#'
#' @return Label string or NULL.
first_child_state_label <- function(children, class_name) {
  for (child in children) {
    if (child$class == class_name) {
      if (trimws(child$label) != "") {
        return(child$label)
      }
      label <- state_var_label(child$state_value, child$state_variable)
      if (trimws(label) != "") {
        return(label)
      }
    }
  }
  NULL
}

#' Draw a glyph and its children.
#'
#' @param glyph Glyph record.
#' @param child_map Named list of child glyphs.
#' @param show_clone_markers Whether to show clone markers.
#'
#' @return NULL.
render_glyph_tree <- function(glyph, child_map, show_clone_markers) {
  if (is.null(glyph$bbox)) {
    return(invisible(NULL))
  }
  rect <- bbox_pixel_rect(glyph$bbox)
  class_name <- glyph$class
  class_base <- sub(" multimer$", "", class_name)
  is_multimer <- grepl(" multimer$", class_name)

  label_override <- NULL
  if (class_name == "and") {
    label_override <- "AND"
  } else if (class_name == "or") {
    label_override <- "OR"
  } else if (class_name == "not") {
    label_override <- "NOT"
  } else if (class_name == "omitted process") {
    label_override <- "\\\\"
  } else if (class_name == "uncertain process") {
    label_override <- "?"
  }

  label <- if (!is.null(label_override)) label_override else glyph$label
  if (class_name == "state variable" && trimws(label) == "") {
    label <- state_var_label(glyph$state_value, glyph$state_variable)
  }

  font_px <- glyph_font_px(class_name)
  has_clone <- show_clone_markers && isTRUE(glyph$has_clone)

  children <- child_map[[glyph$id]]
  if (is.null(children)) {
    children <- list()
  }

  has_u_info_bbox <- any(vapply(children, function(child) {
    child$class == "unit of information" && !is.null(child$bbox)
  }, logical(1)))
  has_s_var_bbox <- any(vapply(children, function(child) {
    child$class == "state variable" && !is.null(child$bbox)
  }, logical(1)))

  u_info_label <- if (has_u_info_bbox) NULL else first_child_label(children, "unit of information")
  s_var_label <- if (has_s_var_bbox) NULL else first_child_state_label(children, "state variable")

  place_label_bottom <- class_base %in% c("complex", "compartment")
  shape_label <- if (place_label_bottom) "" else label

  if (class_name %in% c("phenotype", "outcome")) {
    draw_hexagon_bbox(rect, shape_label, font_px, DEFAULT_LINE_WIDTH, FALSE)
  } else if (class_name == "perturbing agent") {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, NULL)
  } else if (class_name %in% c("simple chemical", "simple chemical multimer")) {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, NULL)
  } else if (class_name == "unspecified entity") {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, s_var_label)
  } else if (class_name %in% c("macromolecule", "macromolecule multimer")) {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, s_var_label)
  } else if (class_name %in% c("nucleic acid feature", "nucleic acid feature multimer")) {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, s_var_label)
  } else if (class_name %in% c("complex", "complex multimer")) {
    draw_entity_pool_node(rect, shape_label, font_px, class_base, is_multimer, has_clone, u_info_label, s_var_label)
  } else if (class_name == "source and sink") {
    draw_source_sink_bbox(rect, has_clone)
  } else if (class_name == "compartment") {
    draw_barrel_bbox(rect, shape_label, font_px, 4, has_clone)
  } else if (class_name == "tag") {
    draw_tag_bbox(rect, shape_label, font_px, DEFAULT_LINE_WIDTH, has_clone)
  } else if (class_name == "association") {
    draw_association_bbox(rect, shape_label, font_px)
  } else if (class_name == "dissociation") {
    draw_double_circle_bbox(rect, shape_label, font_px)
  } else if (class_name %in% c("process", "omitted process", "uncertain process")) {
    draw_square_bbox(glyph$bbox, shape_label, font_px)
  } else if (class_name == "unit of information") {
    draw_round_rect_bbox(rect, shape_label, font_px, DEFAULT_LINE_WIDTH, FALSE)
  } else if (class_name == "state variable") {
    draw_stadium_bbox(rect, shape_label, font_px, DEFAULT_LINE_WIDTH, FALSE)
  } else if (class_name %in% c("and", "or", "not")) {
    draw_circle_bbox(rect, shape_label, font_px)
  } else {
    draw_rect_bbox(rect, shape_label, font_px, DEFAULT_LINE_WIDTH, FALSE)
  }

  orientation <- glyph$orientation
  if (is.null(orientation) && class_name %in% c("process", "omitted process", "uncertain process", "association", "dissociation")) {
    orientation <- "horizontal"
  }
  if (!is.null(orientation)) {
    connector_len_px <- if (class_name %in% c("and", "or", "not")) {
      LOGICAL_PORT_CONNECTOR_LEN_PX
    } else {
      PORT_CONNECTOR_LEN_PX
    }
    draw_orientation_marker(rect, orientation, connector_len_px = connector_len_px)
  }

  if (place_label_bottom) {
    draw_text_bottom_centered(rect, label, font_px)
  }

  for (child in children) {
    if (child$class %in% c("unit of information", "state variable")) {
      next
    }
    render_glyph_tree(child, child_map, show_clone_markers)
  }
}

#' Draw a line segment arc with decorations.
#'
#' @param points Data frame of arc points.
#' @param arc_class Arc class name.
#'
#' @return NULL.
draw_arc <- function(points, arc_class) {
  if (nrow(points) < 2) {
    return(invisible(NULL))
  }
  for (idx in seq_len(nrow(points) - 1)) {
    segments(points$x[idx], points$y[idx], points$x[idx + 1], points$y[idx + 1], col = BORDER_COLOR, lwd = DEFAULT_LINE_WIDTH)
  }

  x_end <- points$x[nrow(points)]
  y_end <- points$y[nrow(points)]
  x_prev <- points$x[nrow(points) - 1]
  y_prev <- points$y[nrow(points) - 1]

  arrow_size <- ARROW_SIZE * ARROW_SCALE
  bar_length <- BAR_LENGTH * ARROW_SCALE
  bar_offset <- BAR_OFFSET * ARROW_SCALE

  if (arc_class %in% c("assignment", "unknown influence")) {
    draw_open_triangle(x_end, y_end, x_prev, y_prev, arrow_size, fill = NA)
  } else if (arc_class %in% c("positive influence", "stimulation")) {
    draw_open_triangle(x_end, y_end, x_prev, y_prev, arrow_size, fill = "white")
  } else if (arc_class == "production") {
    draw_open_triangle(x_end, y_end, x_prev, y_prev, arrow_size, fill = BORDER_COLOR)
  } else if (arc_class %in% c("negative influence", "inhibition")) {
    draw_inhibition_bar(x_end, y_end, x_prev, y_prev, bar_length, 0)
  } else if (arc_class == "absolute inhibition") {
    draw_inhibition_bar(x_end, y_end, x_prev, y_prev, bar_length, 0)
    draw_inhibition_bar(x_end, y_end, x_prev, y_prev, bar_length, bar_offset)
  } else if (arc_class == "necessary stimulation") {
    draw_inhibition_bar(x_end, y_end, x_prev, y_prev, bar_length, bar_offset)
    draw_open_triangle(x_end, y_end, x_prev, y_prev, arrow_size, fill = "white")
  } else if (arc_class == "catalysis") {
    draw_catalysis_circle(x_end, y_end, x_prev, y_prev, arrow_size * 0.4)
  } else if (arc_class == "equivalence arc") {
    symbols(x_end, y_end, circles = arrow_size * 0.4, inches = FALSE, add = TRUE, fg = BORDER_COLOR, bg = NA, lwd = DEFAULT_LINE_WIDTH)
  }
}

#' Draw an open triangle arrowhead.
#'
#' @param x_end Arrow tip x coordinate.
#' @param y_end Arrow tip y coordinate.
#' @param x_prev Previous point x coordinate.
#' @param y_prev Previous point y coordinate.
#' @param size Arrow size.
#' @param fill Fill color (NA for open).
#'
#' @return NULL.
draw_open_triangle <- function(x_end, y_end, x_prev, y_prev, size, fill = NA) {
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
  x_points <- c(
    base_x + perp_x * half_width,
    base_x - perp_x * half_width,
    x_end
  )
  y_points <- c(
    base_y + perp_y * half_width,
    base_y - perp_y * half_width,
    y_end
  )
  polygon(x_points, y_points, border = BORDER_COLOR, col = fill, lwd = DEFAULT_LINE_WIDTH)
}

#' Draw an inhibition bar at the end of a segment.
#'
#' @param x_end End x coordinate.
#' @param y_end End y coordinate.
#' @param x_prev Previous point x coordinate.
#' @param y_prev Previous point y coordinate.
#' @param length Bar length.
#' @param offset Distance to shift the bar back from the end.
#'
#' @return NULL.
draw_inhibition_bar <- function(x_end, y_end, x_prev, y_prev, length, offset) {
  dx <- x_end - x_prev
  dy <- y_end - y_prev
  seg_len <- sqrt(dx^2 + dy^2)
  if (seg_len == 0) {
    return(invisible(NULL))
  }
  ux <- dx / seg_len
  uy <- dy / seg_len
  center_x <- x_end - ux * offset
  center_y <- y_end - uy * offset
  perp_x <- -uy
  perp_y <- ux
  half_len <- length / 2
  segments(
    center_x - perp_x * half_len,
    center_y - perp_y * half_len,
    center_x + perp_x * half_len,
    center_y + perp_y * half_len,
    col = BORDER_COLOR,
    lwd = DEFAULT_LINE_WIDTH
  )
}

#' Draw a catalysis circle tangent to the arc end.
#'
#' @param x_end End x coordinate.
#' @param y_end End y coordinate.
#' @param x_prev Previous point x coordinate.
#' @param y_prev Previous point y coordinate.
#' @param radius Circle radius.
#'
#' @return NULL.
draw_catalysis_circle <- function(x_end, y_end, x_prev, y_prev, radius) {
  dx <- x_end - x_prev
  dy <- y_end - y_prev
  len <- sqrt(dx^2 + dy^2)
  if (len == 0) {
    symbols(x_end, y_end, circles = radius, inches = FALSE, add = TRUE, fg = BORDER_COLOR, bg = "white", lwd = DEFAULT_LINE_WIDTH)
    return(invisible(NULL))
  }
  ux <- dx / len
  uy <- dy / len
  overlap <- radius * CATALYSIS_OVERLAP_RATIO
  offset <- max(0, radius - overlap)
  center_x <- x_end - ux * offset
  center_y <- y_end - uy * offset
  symbols(center_x, center_y, circles = radius, inches = FALSE, add = TRUE, fg = BORDER_COLOR, bg = "white", lwd = DEFAULT_LINE_WIDTH)
}

#' Render the parsed diagram to the active device.
#'
#' @param glyphs List of glyphs.
#' @param arcs List of arcs.
#' @param show_clone_markers Whether to draw clone markers.
#'
#' @return NULL.
render_diagram <- function(glyphs, arcs, show_clone_markers) {
  child_map <- list()
  for (glyph in glyphs) {
    if (!is.null(glyph$parent_id)) {
      existing <- child_map[[glyph$parent_id]]
      if (is.null(existing)) {
        child_map[[glyph$parent_id]] <- list(glyph)
      } else {
        child_map[[glyph$parent_id]] <- c(existing, list(glyph))
      }
    }
  }

  aux_glyphs <- list()
  for (glyph in glyphs) {
    if (!is.null(glyph$parent_id) && glyph$class %in% c("unit of information", "state variable")) {
      aux_glyphs <- c(aux_glyphs, list(glyph))
    }
  }

  for (glyph in glyphs) {
    if (is.null(glyph$parent_id)) {
      render_glyph_tree(glyph, child_map, show_clone_markers)
    }
  }

  for (glyph in aux_glyphs) {
    if (is.null(glyph$bbox)) {
      next
    }
    rect <- bbox_pixel_rect(glyph$bbox)
    label <- glyph$label
    if (glyph$class == "state variable" && trimws(label) == "") {
      label <- state_var_label(glyph$state_value, glyph$state_variable)
    }
    font_px <- glyph_font_px(glyph$class)
    has_clone <- show_clone_markers && isTRUE(glyph$has_clone)

    if (glyph$class == "unit of information") {
      draw_round_rect_bbox(rect, label, font_px, DEFAULT_LINE_WIDTH, has_clone)
    } else if (glyph$class == "state variable") {
      draw_stadium_bbox(rect, label, font_px, DEFAULT_LINE_WIDTH, has_clone)
    }
  }

  for (arc in arcs) {
    draw_arc(arc$points, arc$class)
  }
}

#' Draw the SBGN-ML diagram from XML and write output files (PNG + SVG).
#'
#' @param input_path Path to the SBGN XML file.
#' @param png_output_path Output filename for the PNG.
#' @param padding Padding in pixels.
#' @param clone_markers Whether to draw clone markers.
#'
#' @return NULL. Writes PNG and SVG output files and closes devices.
draw_sbgnml <- function(
  input_path,
  png_output_path,
  padding = DEFAULT_PADDING_PX,
  clone_markers = FALSE
) {
  parsed <- parse_sbgn(input_path)
  glyphs <- parsed$glyphs
  arcs <- parsed$arcs
  bounds <- parsed$bounds

  width <- (bounds$max_x - bounds$min_x + 2 * padding)
  height <- (bounds$max_y - bounds$min_y + 2 * padding)

  render_device <- function(device_fn) {
    device_fn()
    on.exit(dev.off(), add = TRUE)
    par(mar = c(0, 0, 0, 0), xaxs = "i", yaxs = "i", family = FONT_FAMILY)
    plot.new()
    plot.window(
      xlim = c(bounds$min_x - padding, bounds$max_x + padding),
      ylim = c(bounds$max_y + padding, bounds$min_y - padding)
    )
    render_diagram(glyphs, arcs, clone_markers)
  }

  render_device(function() {
    png(filename = png_output_path, width = ceiling(width), height = ceiling(height), units = "px", res = 96)
  })

  svg_output_path <- sub("\\.png$", ".svg", png_output_path)

  render_device(function() {
    svg(filename = svg_output_path, width = width / 96, height = height / 96)
  })
}
