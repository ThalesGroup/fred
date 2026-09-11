#!/bin/sh
# Copyright Thales 2026
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# Package a directory laid out like apps/frontend/public/ into the zip a
# deployment uploads to its object storage. See the frontend README,
# "Theme overlay", for what the container does with it.
set -eu

source_directory=${1:-}
output=${2:-}
if [ -z "${source_directory}" ] || [ -z "${output}" ]; then
    echo "Usage: build-theme-archive.sh <source directory> <output .zip>" >&2
    exit 2
fi
if [ ! -d "${source_directory}" ]; then
    cat >&2 <<EOF
No such directory: ${source_directory}

A theme directory mirrors apps/frontend/public/, and only these are served:

  images/<file>          logos, favicons, avatars, icons/<name>.svg
  contrib/<brand>/<file> per-brand markdown
  <name>.md              gcu, gcu.fr, gdpr, gdpr.fr, release

apps/frontend/theme/ is a working example to copy and edit.
EOF
    exit 2
fi
if ! command -v zip >/dev/null 2>&1; then
    echo "zip is required to build a theme archive" >&2
    exit 2
fi

# The container installs these three surfaces and logs everything else as
# ignored; say so here instead, while the author can still fix the layout.
ignored=$(find "${source_directory}" -mindepth 1 -maxdepth 1 \
    ! -name images ! -name contrib ! -name '*.md' -printf '%f\n' 2>/dev/null || true)
if [ -n "${ignored}" ]; then
    echo "Ignored, outside images/, contrib/ and root *.md:" >&2
    printf '  %s\n' ${ignored} >&2
fi

# The app tries <name>.<lang>.md before <name>.md, and the stock image ships
# French variants: an English-only override never reaches a French browser.
for document in gcu gdpr; do
    if [ -f "${source_directory}/${document}.md" ] && [ ! -f "${source_directory}/${document}.fr.md" ]; then
        echo "Warning: ${document}.md without ${document}.fr.md - French users keep the stock text" >&2
    fi
done

output_path=$(cd "$(dirname "${output}")" && pwd)/$(basename "${output}")
rm -f "${output_path}"
(cd "${source_directory}" && zip -qr "${output_path}" .)
echo "Theme archive: ${output_path} ($(find "${source_directory}" -type f | wc -l | tr -d ' ') files)"
