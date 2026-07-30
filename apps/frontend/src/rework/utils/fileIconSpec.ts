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
// (doc/odt alongside docx; odp alongside ppt/pptx; xls/ods alongside xlsx) —
// Corpus documents' `file.file_type` is normalized to fred-core's `FileType`
// enum and never produces those, but the raw `/fs` tabs (Mon espace/Espace
// d'équipe/Agents) pass a real file extension straight from the file name,
// where they do occur. PPT uses --warning (mustard/orange) since that's the
// closest existing semantic token to PowerPoint's own brand color and no
// other bucket claims it yet — pdf=error, word/texte=tertiary, excel/csv=success.
// Shared across every Resources tab so a given file extension reads the same
// way everywhere.
const FILE_TYPE_ICON: Record<string, RowIconSpec> = {
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
const OTHER_FILE_ICON: RowIconSpec = { type: "draft", color: "var(--on-surface-muted)" };

export function fileIconSpec(fileType: string | null | undefined): RowIconSpec {
  return FILE_TYPE_ICON[fileType ?? ""] ?? OTHER_FILE_ICON;
}
