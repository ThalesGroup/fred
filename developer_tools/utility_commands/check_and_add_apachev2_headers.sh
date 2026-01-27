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

# Use find with multiple -prune rules to exclude dirs named .venv, .git, etc., anywhere
FILES=$(find "$ROOT_PATH" \
  \( -type d \( -name ".venv" -o -name ".git" -o -name "__pycache__" -o -name "htmlcov" \) -prune \) -o \
  -type f -name "*.py" -print)

for file in $FILES; do
  # Check it's a real Python script (avoid .pyc or bad encoding files)
  if file "$file" | grep -q "Python script"; then
    if ! grep -q "Copyright Thales 2025" "$file"; then
      echo "📄 Updating: $file"
      tmp_file=$(mktemp)
      echo "$HEADER" > "$tmp_file"
      cat "$file" >> "$tmp_file"
      mv "$tmp_file" "$file"
    fi
  fi
done

echo "✅ Headers prepended where missing."
