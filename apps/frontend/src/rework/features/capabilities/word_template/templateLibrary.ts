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

// Template-library editing logic for the word_template config widget,
// owned by this capability.
//
// The capability config is an untyped `Record<string, unknown>` on the
// agent-save contract (no generated type exists for it), so this narrows the
// `template_library` value. The invariant: the NEW (keyless) entries, in list
// order, line up one-to-one with the staged files of the
// `word_template_library` slot - the backend pairs them by position and
// rejects any count mismatch (422).

/** The manifest's multi-file library slot (`AssetSlot.key` on the backend). */
export const TEMPLATE_LIBRARY_SLOT = "word_template_library";

/**
 * One `template_library` entry as round-tripped through the form. Stored
 * entries carry `template_key` plus backend-computed fields (`parts_summary`,
 * `analysis`) the form never reads but must send back unchanged - hence the
 * open index signature. The form only edits `label`.
 */
export interface TemplateLibraryEntryDraft {
  template_key?: string | null;
  label: string;
  [field: string]: unknown;
}

export interface TemplateLibraryState {
  entries: TemplateLibraryEntryDraft[];
  /** Staged files, aligned with the keyless entries of `entries`, in order. */
  files: File[];
}

export type TemplateLibraryProblem = "missingLabel" | "duplicateLabel";

const isNew = (entry: TemplateLibraryEntryDraft): boolean => !entry.template_key;

/** Narrow the stored config value; anything malformed reads as no library. */
export function readTemplateLibrary(value: unknown): TemplateLibraryEntryDraft[] {
  if (!Array.isArray(value)) return [];
  return value
    .filter((e): e is Record<string, unknown> => typeof e === "object" && e !== null)
    .map((e) => ({ ...e, label: typeof e.label === "string" ? e.label : "" }));
}

/** "Rapport_annuel v2.docx" -> "Rapport annuel v2" - a starting name the admin edits. */
export function labelFromFilename(filename: string): string {
  return filename
    .replace(/\.docx$/i, "")
    .replace(/_+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

export function addTemplateFiles(state: TemplateLibraryState, added: File[]): TemplateLibraryState {
  return {
    entries: [...state.entries, ...added.map((file) => ({ label: labelFromFilename(file.name) }))],
    files: [...state.files, ...added],
  };
}

export function removeTemplateEntry(state: TemplateLibraryState, index: number): TemplateLibraryState {
  const target = state.entries[index];
  if (!target) return state;
  const entries = state.entries.filter((_, i) => i !== index);
  if (!isNew(target)) return { entries, files: state.files };
  const fileIndex = state.entries.slice(0, index).filter(isNew).length;
  return { entries, files: state.files.filter((_, i) => i !== fileIndex) };
}

export function updateTemplateLabel(
  entries: TemplateLibraryEntryDraft[],
  index: number,
  label: string,
): TemplateLibraryEntryDraft[] {
  return entries.map((entry, i) => (i === index ? { ...entry, label } : entry));
}

/** Same folding as the backend's `_normalized` (accents dropped, case and
 *  whitespace ignored), which decides when two names collide. */
export const normalizeLabel = (label: string): string =>
  label.normalize("NFKD").replace(/[̀-ͯ]/g, "").replace(/\s+/g, " ").trim().toLowerCase();

/** Per-row problem the backend would reject with a 422 (null = row is fine).
 *  Every row sharing a duplicated name is flagged, not just the later ones. */
export function templateLibraryRowProblems(entries: TemplateLibraryEntryDraft[]): (TemplateLibraryProblem | null)[] {
  const labels = entries.map((e) => normalizeLabel(e.label));
  const counts = new Map<string, number>();
  for (const label of labels) counts.set(label, (counts.get(label) ?? 0) + 1);
  return labels.map((label) => {
    if (!label) return "missingLabel";
    return (counts.get(label) ?? 0) > 1 ? "duplicateLabel" : null;
  });
}

/** The library slot's staged files, whatever shape the host holds them in. */
export function stagedLibraryFiles(staged: File | File[] | undefined): File[] {
  if (!staged) return [];
  return Array.isArray(staged) ? staged : [staged];
}
