test_that("package version matches the coordinated release", {
  expect_equal(as.character(packageVersion("renderSbgnR")), "0.0.7")
})
