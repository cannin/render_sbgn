test_that("bundled font and fallback order are available", {
  expect_identical(
    renderSbgnR:::FONT_FAMILIES,
    c("Liberation Sans", "Arial", "DejaVu Sans", "Helvetica", "sans-serif")
  )
  font_path <- system.file(
    "fonts",
    "LiberationSans-Regular.ttf",
    package = "renderSbgnR"
  )
  expect_true(nzchar(font_path))
  expect_gt(file.info(font_path)$size, 0)
})
