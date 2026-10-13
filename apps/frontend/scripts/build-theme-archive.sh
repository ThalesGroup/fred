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

# Package a structured or legacy flat theme directory into the zip a
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

A theme directory has theme-catalog.json at its root. New archives use:

  themes/<id>/theme-custom.css  CSS for one catalog theme
  themes/<id>/images/           images for that theme
  shared/                       global images, properties, translations and markdown

Legacy flat archives are also supported. Their served entries are:

  images/<file>          logos, favicons, avatars, icons/<name>.svg
  contrib/<brand>/<file> per-brand markdown
  <name>.md              gcu, gcu.fr, gdpr, gdpr.fr, team-admin-charter,
                         team-admin-charter.fr, release
  theme-custom.css        CSS variables and additional theme rules
  theme-catalog.json       additional selectable themes
  theme-properties.json   branding labels and image file names
  theme-translations/    en.json and fr.json UI label overrides

apps/frontend/theme/ is a working example to copy and edit.
EOF
    exit 2
fi
if ! command -v zip >/dev/null 2>&1; then
    echo "zip is required to build a theme archive" >&2
    exit 2
fi

if [ -d "${source_directory}/themes" ] || [ -d "${source_directory}/shared" ]; then
    document_directory="${source_directory}/shared"
else
    document_directory="${source_directory}"
fi

# The app tries <name>.<lang>.md before <name>.md, and the stock image ships
# both: an override missing either one leaves those users on the stock text.
for document in gcu gdpr team-admin-charter; do
    if [ -f "${document_directory}/${document}.md" ] && [ ! -f "${document_directory}/${document}.fr.md" ]; then
        echo "Warning: ${document}.md without ${document}.fr.md - French users keep the stock text" >&2
    fi
    if [ -f "${document_directory}/${document}.fr.md" ] && [ ! -f "${document_directory}/${document}.md" ]; then
        echo "Warning: ${document}.fr.md without ${document}.md - other languages keep the stock text" >&2
    fi
done

output_path=$(cd "$(dirname "${output}")" && pwd)/$(basename "${output}")
rm -f "${output_path}"
(cd "${source_directory}" && zip -qr "${output_path}" .)
# Validate with the installer the container runs, so both can never disagree.
check_directory=$(mktemp -d)
if ! FRONTEND_THEME_URL="file://${output_path}" FRONTEND_THEME_REQUIRED=true FRONTEND_THEME_S3_ACCESS_KEY= \
    FRONTEND_THEME_S3_SECRET_KEY= sh "$(dirname "$0")/theme-overlay.sh" "${check_directory}" >/dev/null; then
    rm -rf "${check_directory}" "${output_path}"
    exit 2
fi
rm -rf "${check_directory}"
echo "Theme archive: ${output_path} ($(find "${source_directory}" -type f | wc -l | tr -d ' ') files)"
