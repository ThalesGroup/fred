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

// Turns a paste into chat attachments. Kept out of the component so the two
// judgement calls below (text wins over files, clipboard files need a name) are
// unit-testable without a DOM. No format is filtered here: an attachment Fred
// cannot process must fail on ingestion, with the same error as a hand-picked
// file of that type.

// Anchored on the prefix only: copied paths routinely contain spaces.
const PATH_LIKE = /^(?:file:\/\/|\/|~\/|\\\\|[A-Za-z]:[\\/])/;

// Nautilus and friends prefix the copied paths with their own marker lines,
// which land in text/plain next to the file.
const CLIPBOARD_MARKERS = new Set(["copy", "cut", "x-special/nautilus-clipboard", "x-special/gnome-copied-files"]);

// Browsers name every pasted screenshot "image.png", and document tools resolve
// session attachments by name — two pastes in one conversation would be
// indistinguishable.
const GENERIC_NAMES = new Set(["", "image", "image.png", "image.jpg", "image.jpeg", "image.webp", "image.gif"]);

// Mime types whose extension is not simply the subtype. Ingestion dispatches on
// the extension alone, so a name-less clipboard file needs the right one or a
// perfectly supported format would 400.
const MIME_EXTENSIONS: Record<string, string> = {
  "application/msword": ".doc",
  "application/pdf": ".pdf",
  "application/vnd.ms-excel": ".xls",
  "application/vnd.ms-powerpoint": ".ppt",
  "application/vnd.oasis.opendocument.text": ".odt",
  "application/vnd.openxmlformats-officedocument.presentationml.presentation": ".pptx",
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": ".xlsx",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document": ".docx",
  "image/jpeg": ".jpg",
  "image/svg+xml": ".svg",
  "image/vnd.microsoft.icon": ".ico",
  "image/x-icon": ".ico",
  "text/markdown": ".md",
  "text/plain": ".txt",
};

function extensionFor(mime: string): string {
  const type = mime.split(";")[0].trim().toLowerCase();
  const known = MIME_EXTENSIONS[type];
  if (known) return known;
  // Everything else follows the subtype (image/png → .png, application/x-tar →
  // .tar). A format Fred has no processor for then fails on ingestion exactly
  // as the same file picked from disk would.
  const subtype =
    type
      .split("/")[1]
      ?.split("+")[0]
      ?.replace(/^(?:x-|vnd\.)/, "") ?? "";
  return /^[a-z0-9][a-z0-9.-]*$/.test(subtype) ? `.${subtype}` : "";
}

/**
 * Whether the files in the clipboard are what the user meant to paste.
 * Word and Excel put a rendered PNG next to the copied cells, so real text
 * always wins; the paths a file manager leaves behind are not real text.
 */
export function clipboardPrefersFiles(text: string): boolean {
  const lines = text
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter((line) => line && !CLIPBOARD_MARKERS.has(line.toLowerCase()));
  return lines.length === 0 || lines.every((line) => PATH_LIKE.test(line));
}

export function clipboardFileName(name: string, mime: string, at: Date, index: number): string {
  if (!GENERIC_NAMES.has(name.toLowerCase())) return name;
  // Milliseconds included: a second-precision stamp collides across two quick
  // pastes, which is the ambiguity this rename exists to remove.
  const iso = at.toISOString();
  const stamp = `${iso.slice(0, 10).replace(/-/g, "")}-${iso.slice(11, 19).replace(/:/g, "")}-${iso.slice(20, 23)}`;
  const extension = name.includes(".") ? name.slice(name.lastIndexOf(".")) : extensionFor(mime);
  return `pasted-${stamp}${index > 0 ? `-${index + 1}` : ""}${extension}`;
}

/** Files to attach for this paste — empty when the paste should stay a text paste. */
export function clipboardAttachments(data: DataTransfer | null, at: Date = new Date()): File[] {
  const files = Array.from(data?.files ?? []).filter((file) => file.size > 0);
  if (files.length === 0 || !clipboardPrefersFiles(data?.getData("text/plain") ?? "")) return [];
  return files.map((file, index) => {
    const name = clipboardFileName(file.name, file.type, at, index);
    return name === file.name ? file : new File([file], name, { type: file.type, lastModified: file.lastModified });
  });
}
