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

/**
 * file extension/type → icon + colour. Small lookup table, on the model of the
 * task feature's STATE_COLOR map. Colours are semantic tokens (no hardcoded hex):
 * the icon's colour identifies the family, it is NOT a status signal.
 */
interface FileTypeMeta {
  icon: IconType;
  color: string;
}

const FILE_TYPE_META: Record<string, FileTypeMeta> = {
  pdf: { icon: "picture_as_pdf", color: "var(--error)" },
  doc: { icon: "description", color: "var(--info)" },
  docx: { icon: "description", color: "var(--info)" },
  txt: { icon: "description", color: "var(--on-surface-retreat)" },
  md: { icon: "description", color: "var(--on-surface-retreat)" },
  csv: { icon: "table_chart", color: "var(--success)" },
  xls: { icon: "table_chart", color: "var(--success)" },
  xlsx: { icon: "table_chart", color: "var(--success)" },
  ppt: { icon: "slideshow", color: "var(--warning)" },
  pptx: { icon: "slideshow", color: "var(--warning)" },
  png: { icon: "image", color: "var(--info)" },
  jpg: { icon: "image", color: "var(--info)" },
  jpeg: { icon: "image", color: "var(--info)" },
  gif: { icon: "image", color: "var(--info)" },
  webp: { icon: "image", color: "var(--info)" },
  mp3: { icon: "audio_file", color: "var(--info)" },
  wav: { icon: "audio_file", color: "var(--info)" },
  mp4: { icon: "video_file", color: "var(--info)" },
  mov: { icon: "video_file", color: "var(--info)" },
};

const DEFAULT_META: FileTypeMeta = { icon: "description", color: "var(--on-surface-retreat)" };

export function fileTypeMeta(fileType: string): FileTypeMeta {
  return FILE_TYPE_META[fileType.trim().toLowerCase()] ?? DEFAULT_META;
}
