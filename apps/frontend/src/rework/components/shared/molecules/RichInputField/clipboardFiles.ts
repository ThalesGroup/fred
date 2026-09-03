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
// judgement calls below (text wins over files, screenshots need a name) are
// unit-testable without a DOM.

// Anchored on the prefix only: copied paths routinely contain spaces.
const PATH_LIKE = /^(?:file:\/\/|\/|~\/|\\\\|[A-Za-z]:[\\/])/;

// Browsers name every pasted screenshot "image.png", and document tools resolve
// session attachments by name — two pastes in one conversation would be
// indistinguishable.
const GENERIC_NAMES = new Set(["", "image", "image.png", "image.jpg", "image.jpeg", "image.webp", "image.gif"]);

// Only where the mime subtype is not the extension. Anything else unusual gets
// no extension rather than a made-up one ingestion would reject.
const CLIPBOARD_EXTENSIONS: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/svg+xml": ".svg",
  "text/plain": ".txt",
};

function extensionFor(mime: string): string {
  const known = CLIPBOARD_EXTENSIONS[mime];
  if (known) return known;
  const subtype = mime.split("/")[1] ?? "";
  return /^[a-z0-9]+$/.test(subtype) ? `.${subtype}` : "";
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
    .filter(Boolean);
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
