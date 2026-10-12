#!/bin/sh
# Copyright Thales 2026
# SPDX-License-Identifier: Apache-2.0
# Shared by the nginx entrypoint and the local Vite server.
set -eu
: "${FRONTEND_THEME_URL:=}"
: "${FRONTEND_THEME_S3_ACCESS_KEY:=}"
: "${FRONTEND_THEME_S3_SECRET_KEY:=}"
: "${FRONTEND_THEME_S3_REGION:=us-east-1}"
: "${FRONTEND_THEME_REQUIRED:=false}"
FRONTEND_THEME_DIR=${1:?Usage: theme-overlay.sh <overlay directory>}
case "$FRONTEND_THEME_REQUIRED" in
    true | false) ;;
    *) echo "Invalid configuration: FRONTEND_THEME_REQUIRED must be either true or false" >&2; exit 1 ;;
esac
if [ -n "${FRONTEND_THEME_S3_ACCESS_KEY}${FRONTEND_THEME_S3_SECRET_KEY}" ] &&
    { [ -z "${FRONTEND_THEME_S3_ACCESS_KEY}" ] || [ -z "${FRONTEND_THEME_S3_SECRET_KEY}" ]; }; then
    echo "Invalid configuration: FRONTEND_THEME_S3_ACCESS_KEY and FRONTEND_THEME_S3_SECRET_KEY must be set together" >&2
    exit 1
fi
mkdir -p "$FRONTEND_THEME_DIR"
# A half-extracted archive can leave a directory rm cannot enter, and cleanup
# that fails must never be what takes the container down.
discard_work() {
    [ -n "${work:-}" ] || return 0
    chmod -R u+rwX "${work}" 2>/dev/null || true
    rm -rf "${work}" 2>/dev/null || true
    work=
}

theme_failure() {
    discard_work
    # An emptyDir outlives container restarts: drop a previous theme so the
    # message below stays true instead of serving a stale brand.
    find "${FRONTEND_THEME_DIR}" -mindepth 1 -delete 2>/dev/null || true
    if [ "${FRONTEND_THEME_REQUIRED}" = "true" ]; then
        echo "Theme installation failed: $1" >&2
        exit 1
    fi
    echo "Theme skipped, serving the stock assets: $1" >&2
}

# curl's config parser reads \ and " as escapes inside a quoted value.
curl_config_value() {
    printf '%s' "$1" | sed 's/[\\"]/\\&/g'
}

# Fetch FRONTEND_THEME_URL and copy its served surfaces into the overlay
# directory. nginx only starts once this returns, so the fetch is bounded to
# stay inside the default liveness window. Symlinks are dropped: unzip
# recreates them and nginx would follow one out of the overlay.
install_theme() {
    [ -n "${FRONTEND_THEME_URL}" ] || return 0
    if [ -n "$FRONTEND_THEME_URL" ]; then
        for dependency in curl unzip jq; do
            if ! command -v "$dependency" >/dev/null 2>&1; then
                theme_failure "$dependency is required; install it before starting the frontend"
                return 0
            fi
        done
    fi

    # A presigned URL carries its credential in the query string: never log it.
    theme_source=$(printf '%s' "${FRONTEND_THEME_URL%%\?*}" | sed 's#://[^/@]*@#://[redacted]@#')
    work=$(mktemp -d /tmp/fred-theme.XXXXXX) || { theme_failure "cannot create a temporary directory"; return 0; }
    archive="${work}/theme.zip"
    if [ -n "${FRONTEND_THEME_S3_ACCESS_KEY}" ] && [ -n "${FRONTEND_THEME_S3_SECRET_KEY}" ]; then
        # The credential goes through a private config file, never the command line.
        printf 'user = "%s:%s"\n' \
            "$(curl_config_value "${FRONTEND_THEME_S3_ACCESS_KEY}")" \
            "$(curl_config_value "${FRONTEND_THEME_S3_SECRET_KEY}")" > "${work}/curl.conf"
        set -- -K "${work}/curl.conf" --aws-sigv4 "aws:amz:${FRONTEND_THEME_S3_REGION}:s3"
    else
        set --
    fi
    # nginx does not listen until this returns, and the chart's liveness probe
    # starts at once (3 failures x 10s), so the whole chain stays under ~16s and
    # a stalling store boots the stock assets instead of crashlooping. Anything
    # slower than that needs the startupProbe from the example values.
    if ! curl "$@" -fsSL --connect-timeout 3 --max-time 6 --retry 2 --retry-connrefused --retry-max-time 10 \
        --max-filesize 64m -o "${archive}" "${FRONTEND_THEME_URL}" 2>/dev/null; then
        theme_failure "cannot download ${theme_source}"
        return 0
    fi
    # unzip relocates entries with .. or absolute paths and says so (busybox or
    # Info-ZIP wording). Refuse such an archive instead of guessing.
    if unzip -l "${archive}" 2>&1 | grep -qE 'removing leading|path component|(^|[ /])\.\.(/|$)'; then
        theme_failure "archive contains entries with '..' or absolute paths"
        return 0
    fi
    if ! mkdir "${work}/unpacked" || ! unzip -oq "${archive}" -d "${work}/unpacked" >/dev/null 2>&1; then
        theme_failure "cannot unpack the archive"
        return 0
    fi
    # A zip stores each entry's mode, and 0000 is a valid one for a directory
    # too. Widen first: every walk below, symlink sweep included, needs to
    # enter every directory, and one it cannot enter would abort the script.
    if ! chmod -R u+rwX "${work}/unpacked"; then
        theme_failure "cannot make the archive contents readable"
        return 0
    fi
    # unzip recreates symlinks and nginx would follow one out of the overlay.
    if ! find "${work}/unpacked" -type l -delete; then
        theme_failure "cannot drop the symlinks the archive carries"
        return 0
    fi
    # Finder's "Compress" adds this folder next to the real one.
    rm -rf "${work}/unpacked/__MACOSX" || true
    root="${work}/unpacked"
    # zip -r acme-theme/ wraps everything in one folder: look inside it.
    set -- "${root}"/*
    if [ $# -eq 1 ] && [ -d "$1" ]; then
        case "$(basename "$1")" in
            images | contrib | theme-translations) ;;
            *) root=$1 ;;
        esac
    fi
    # Assembled aside, then swapped in one go: a copy that fails halfway would
    # otherwise leave the overlay mixing two brands.
    staging="${work}/staging"
    if ! mkdir "${staging}"; then
        theme_failure "cannot stage the archive contents"
        return 0
    fi
    for entry in "${root}"/*; do
        [ -e "${entry}" ] || continue
        name=$(basename "${entry}")
        if [ -d "${entry}" ] && { [ "${name}" = images ] || [ "${name}" = contrib ]; }; then
            cp -R "${entry}" "${staging}/" || { theme_failure "cannot read ${name} from the archive"; return 0; }
        elif [ -d "${entry}" ] && [ "${name}" = theme-translations ]; then
            mkdir "${staging}/theme-translations" || { theme_failure "cannot stage translations"; return 0; }
            for language in en fr; do
                source_file="${entry}/${language}.json"
                [ -f "${source_file}" ] || continue
                if ! jq -es '
                    def safe: type == "string" or (type == "object" and all(to_entries[];
                        (.key | test("^[A-Za-z0-9_-]+$")) and
                        (.key != "__proto__" and .key != "constructor" and .key != "prototype") and
                        (.value | safe)));
                    length == 1 and (.[0] | type == "object" and safe)
                ' "${source_file}" >/dev/null 2>&1; then
                    theme_failure "invalid ${name}/${language}.json"
                    return 0
                fi
                cp "${source_file}" "${staging}/theme-translations/" || { theme_failure "cannot read translation"; return 0; }
            done
        elif [ -f "${entry}" ] && { [ "${name%.md}" != "${name}" ] || [ "${name}" = theme-custom.css ] || [ "${name}" = theme-properties.json ] || [ "${name}" = theme-catalog.json ]; }; then
            if [ "${name}" = theme-catalog.json ] && ! jq -es '
                length == 1 and (.[0] | type == "object" and (keys == ["themes"]) and
                (.themes | type == "array" and length <= 16 and
                    all(.[]; type == "object" and (keys - ["base", "id", "label", "tabTitle", "faviconName", "faviconNameDark"] | length == 0) and
                        (if has("tabTitle") then (.tabTitle | type == "string" and length <= 200 and test("[^\\s\uFEFF]")) else true end) and
                        (if has("faviconName") then (.faviconName | type == "string" and test("^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")) else true end) and
                        (if has("faviconNameDark") then (.faviconNameDark | type == "string" and test("^[a-zA-Z0-9][a-zA-Z0-9_-]{0,127}$")) else true end) and
                        (.id | type == "string" and test("^[a-z][a-z0-9-]{0,31}$") and
                            . != "pebble" and . != "cobalt" and . != "cloud") and
                        (.label | type == "string" and length > 0 and length <= 80 and test("[^\\s\uFEFF]")) and
                        (.base | IN("pebble", "cobalt", "cloud")))) and
                ((.themes | map(.id) | unique | length) == (.themes | length)))
            ' "${entry}" >/dev/null 2>&1; then
                theme_failure "invalid theme-catalog.json"
                return 0
            fi
            if [ "${name}" = theme-properties.json ] && ! jq -es '
                length == 1 and (.[0] |
                    type == "object" and
                    (keys - ["agentIconName", "agentsNicknamePlural", "agentsNicknameSingular", "contactSupportLink", "defaultPersonalAvatarFile", "defaultTeamAvatarFile", "faviconName", "faviconNameDark", "logoName", "logoNameDark", "releaseBrand", "siteDisplayName", "siteSubtitle", "siteTitle"] | length == 0) and
                    all(.[]; type == "string" and length <= 200))
            ' "${entry}" >/dev/null 2>&1; then
                theme_failure "invalid theme-properties.json"
                return 0
            fi
            cp "${entry}" "${staging}/" || { theme_failure "cannot read ${name} from the archive"; return 0; }
        else
            echo "Theme entry ignored, not a served surface: ${name}" >&2
        fi
    done
    installed=$(find "${staging}" -type f | wc -l)
    if [ "${installed}" -eq 0 ]; then
        theme_failure "archive holds no supported theme files"
        return 0
    fi
    if ! find "${FRONTEND_THEME_DIR}" -mindepth 1 -delete ||
        ! cp -R "${staging}/." "${FRONTEND_THEME_DIR}/"; then
        theme_failure "cannot write ${FRONTEND_THEME_DIR}"
        return 0
    fi
    discard_work
    echo "Theme installed from ${theme_source}: ${installed} files"
}

trap discard_work EXIT HUP INT TERM
install_theme
