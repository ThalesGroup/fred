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

# The container installs these surfaces and logs everything else as
# ignored; say so here instead, while the author can still fix the layout.
if [ -d "${source_directory}/themes" ] || [ -d "${source_directory}/shared" ]; then
    if ! command -v jq >/dev/null 2>&1 ||
        ! jq -e '.themes | type == "array"' "${source_directory}/theme-catalog.json" >/dev/null 2>&1; then
        echo "Structured themes need jq and a valid root theme-catalog.json" >&2
        exit 2
    fi
    for theme_dir in "${source_directory}/themes"/*; do
        [ -e "${theme_dir}" ] || continue
        theme_id=$(basename "${theme_dir}")
        if [ ! -d "${theme_dir}" ] ||
            ! jq -e --arg id "${theme_id}" '.themes | any(.id == $id)' "${source_directory}/theme-catalog.json" >/dev/null 2>&1; then
            echo "Undeclared theme directory: ${theme_id}" >&2
            exit 2
        fi
        theme_ignored=$(find "${theme_dir}" -mindepth 1 -maxdepth 1 \
            ! -name theme-custom.css ! -name images -printf '%f\n' 2>/dev/null || true)
        if [ -n "${theme_ignored}" ]; then
            echo "Unsupported entry in themes/${theme_id}: ${theme_ignored}" >&2
            exit 2
        fi
        if { [ -e "${theme_dir}/theme-custom.css" ] && [ ! -f "${theme_dir}/theme-custom.css" ]; } ||
            { [ -e "${theme_dir}/images" ] && [ ! -d "${theme_dir}/images" ]; }; then
            echo "Invalid CSS or images entry in themes/${theme_id}" >&2
            exit 2
        fi
    done
    if [ -d "${source_directory}/shared" ]; then
        for shared_entry in "${source_directory}/shared"/*; do
            [ -e "${shared_entry}" ] || continue
            shared_name=$(basename "${shared_entry}")
            case "${shared_name}" in
                images | contrib | theme-translations)
                    [ -d "${shared_entry}" ] || { echo "Invalid shared directory: ${shared_name}" >&2; exit 2; } ;;
                theme-properties.json | *.md)
                    [ -f "${shared_entry}" ] || { echo "Invalid shared file: ${shared_name}" >&2; exit 2; } ;;
                *) echo "Unsupported shared entry: ${shared_name}" >&2; exit 2 ;;
            esac
        done
    fi
    image_paths=$(find "${source_directory}/themes" "${source_directory}/shared/images" \
        -type f -path '*/images/*' -print 2>/dev/null | awk -F '/images/' '{print $NF}' | sort)
    image_conflicts=$(printf '%s\n' "${image_paths}" | awk '
        previous == $0 || (previous != "" && index($0, previous "/") == 1) { print $0 }
        { previous = $0 }
    ')
    if [ -n "${image_conflicts}" ]; then
        echo "Image path conflict across theme folders: ${image_conflicts}" >&2
        exit 2
    fi
    ignored=$(find "${source_directory}" -mindepth 1 -maxdepth 1 \
        ! -name themes ! -name shared ! -name theme-catalog.json -printf '%f\n' 2>/dev/null || true)
    document_directory="${source_directory}/shared"
else
    ignored=$(find "${source_directory}" -mindepth 1 -maxdepth 1 \
        ! -name images ! -name contrib ! -name theme-translations ! -name '*.md' ! -name theme-custom.css \
        ! -name theme-properties.json ! -name theme-catalog.json -printf '%f\n' 2>/dev/null || true)
    document_directory="${source_directory}"
fi
if [ -n "${ignored}" ]; then
    echo "Unsupported theme entries:" >&2
    printf '  %s\n' ${ignored} >&2
    exit 2
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
echo "Theme archive: ${output_path} ($(find "${source_directory}" -type f | wc -l | tr -d ' ') files)"
