#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

for tool in jq docker trivy; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    echo "ERROR: $tool is required to generate image SBOMs." >&2
    exit 1
  fi
done

image_rows=$(jq -er '
  [.images[] | select(.publish == true) |
    [.name, (.dockerfile | split("/")[0:2] | join("/"))] | @tsv]
  | if length > 0 then .[] else error("No published images in manifest") end
' .github/docker-images.json)

names=()
references=()
while IFS=$'\t' read -r name app_dir; do
  if [[ ! "$name" =~ ^[a-zA-Z0-9_-]+$ || ! -f "$app_dir/Makefile" ]]; then
    echo "ERROR: invalid published image entry: $name ($app_dir)." >&2
    exit 1
  fi

  reference=$(make -s -C "$app_dir" \
    --eval='sbom-image-reference:; @printf "%s\n" "$(IMAGE_FULL)"' \
    sbom-image-reference)
  if [[ -z "$reference" ]] || ! docker image inspect "$reference" >/dev/null 2>&1; then
    echo "ERROR: local image $reference ($name) is missing. Run 'make docker-build' first." >&2
    exit 1
  fi

  names+=("$name")
  references+=("$reference")
done <<< "$image_rows"

output_dir=target/sbom
mkdir -p "$output_dir"
tmp=
trap 'if [[ -n "$tmp" ]]; then rm -f -- "$tmp"; fi' EXIT

for i in "${!names[@]}"; do
  name=${names[$i]}
  reference=${references[$i]}
  output="$output_dir/$name.cdx.json"
  tmp=$(mktemp "$output_dir/.$name.XXXXXX")
  echo "Generating $output from $reference"
  trivy image --image-src docker --format cyclonedx --output "$tmp" "$reference"
  if ! jq -e '.bomFormat == "CycloneDX" and ((.components // []) | length > 0)' "$tmp" >/dev/null; then
    echo "ERROR: $reference produced no valid CycloneDX components." >&2
    exit 1
  fi
  mv -f -- "$tmp" "$output"
  tmp=
done

echo "Generated ${#names[@]} SBOMs in $output_dir/."
