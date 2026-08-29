#!/usr/bin/env bash

set -euo pipefail

repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
package_name="$(awk -F ': ' '$1 == "Package" { print $2 }' "$repository_root/r/DESCRIPTION")"
package_version="$(awk -F ': ' '$1 == "Version" { print $2 }' "$repository_root/r/DESCRIPTION")"
package_archive="$repository_root/${package_name}_${package_version}.tar.gz"

(
  cd "$repository_root"
  R CMD build --no-manual r
  _R_CHECK_FORCE_SUGGESTS_=false R CMD check \
    --no-manual --no-build-vignettes "$package_archive"
)
