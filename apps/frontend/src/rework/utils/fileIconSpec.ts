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

import type { IconType } from "@shared/utils/Type.ts";

export interface RowIconSpec {
  type: IconType;
  color: string;
  filled?: boolean;
}

export const FOLDER_ICON: RowIconSpec = { type: "folder", color: "var(--folder)", filled: true };

// Mirrors fred-core's FileTypeBucket grouping (PDF / Texte / PPT / Excel /
// Autres), including the legacy/OpenDocument extensions that bucket covers
// (doc/odt alongside docx; odp alongside ppt/pptx; xls/ods alongside xlsx).
// PPT uses --warning (mustard/orange) since that's the closest existing
// semantic token to PowerPoint's own brand color and no other bucket claims
// it yet — pdf=error, word/texte=tertiary, excel/csv=success.
const ICON_BY_EXTENSION: Record<string, RowIconSpec> = {
  pdf: { type: "picture_as_pdf", color: "var(--error)" },
  docx: { type: "article", color: "var(--tertiary)" },
  doc: { type: "article", color: "var(--tertiary)" },
  odt: { type: "article", color: "var(--tertiary)" },
  md: { type: "article", color: "var(--tertiary)" },
  html: { type: "article", color: "var(--tertiary)" },
  txt: { type: "article", color: "var(--tertiary)" },
  xlsx: { type: "table", color: "var(--success)" },
  xls: { type: "table", color: "var(--success)" },
  ods: { type: "table", color: "var(--success)" },
  csv: { type: "table", color: "var(--success)" },
  ppt: { type: "slideshow", color: "var(--warning)" },
  pptx: { type: "slideshow", color: "var(--warning)" },
  odp: { type: "slideshow", color: "var(--warning)" },
};
const IMAGE_FILE_ICON: RowIconSpec = { type: "image", color: "var(--on-surface-muted)" };
const OTHER_FILE_ICON: RowIconSpec = { type: "draft", color: "var(--on-surface-muted)" };

/** How a file is pictured wherever it is listed: resources, library pickers,
 *  chat attachments.
 *
 *  The file name is the one fact every source carries. The media type is
 *  supplied by the uploading browser — often empty or `application/octet-stream`
 *  for Markdown or CSV — so it only tells an image apart. */
export function fileIconSpec(name: string, mime?: string | null): RowIconSpec {
  const dot = name.lastIndexOf(".");
  const extension = dot > 0 ? name.slice(dot + 1).toLowerCase() : "";
  return ICON_BY_EXTENSION[extension] ?? (mime?.startsWith("image/") ? IMAGE_FILE_ICON : OTHER_FILE_ICON);
}
