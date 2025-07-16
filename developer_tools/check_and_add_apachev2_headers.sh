#!/bin/bash

ROOT_PATH="${1:-.}"

HEADER='# Copyright Thales 2025
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
'

FILES=$(find "$ROOT_PATH" \
  -type d \( -path "$ROOT_PATH/.venv" -o -path "$ROOT_PATH/.git" -o -path "$ROOT_PATH/__pycache__" -o -path "$ROOT_PATH/htmlcov" \) -prune -false \
  -o -name "*.py" -type f)

for file in $FILES; do
  if ! grep -q "Copyright Thales 2025" "$file"; then
    echo "📄 Updating: $file"
    tmp_file=$(mktemp)
    echo "$HEADER" > "$tmp_file"
    cat "$file" >> "$tmp_file"
    mv "$tmp_file" "$file"
  fi
done

echo "✅ Headers prepended where missing."
