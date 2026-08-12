// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

/**
 * Relative-path helpers for files that came out of a dropped or picked FOLDER.
 *
 * file-selector's `fromEvent` (drop) stamps each traversed file with a `path`
 * like "/batch/sub/a.pdf"; a `webkitdirectory` input stamps
 * `webkitRelativePath` like "batch/sub/a.pdf". A file dropped or picked on its
 * own carries "./a.pdf", "a.pdf", or nothing — no directory either way. These
 * helpers read whichever is present so callers can rebuild the folder chain
 * (nested corpus tags) a file belongs under.
 */

type FileWithOptionalPath = File & { path?: string; webkitRelativePath?: string };

/**
 * The directory chain a file sits in, relative to the drop/pick root —
 * `["batch", "sub"]` for "/batch/sub/a.pdf", `[]` for a file with no folder.
 */
export function relativeDirSegments(file: File): string[] {
  const { path, webkitRelativePath } = file as FileWithOptionalPath;
  const raw = path || webkitRelativePath || "";
  const segments = raw
    .split("/")
    .map((seg) => seg.trim())
    .filter((seg) => seg && seg !== ".");
  // Last segment is the file's own name, not a directory.
  return segments.slice(0, -1);
}

/** "batch/sub/a.pdf" for a file inside a dropped folder, plain name otherwise. */
export function displayPath(file: File): string {
  const dir = relativeDirSegments(file);
  return dir.length ? `${dir.join("/")}/${file.name}` : file.name;
}
