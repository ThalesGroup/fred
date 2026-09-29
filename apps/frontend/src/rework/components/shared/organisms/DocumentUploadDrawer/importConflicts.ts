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

import type {
  ImportDestinationNames,
  ImportNameConflicts,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { leafFileName } from "../../../../../slices/streamDocumentUpload";

/** Replace the document already there, or skip the file and import nothing. */
export type ConflictDecision = "overwrite" | "skip";

/** One batch of files sharing a destination — what the drawer sends per request. */
export interface UploadGroup {
  /** The folder the files land in. Null when the destination carries no tag
   * (the corpus root), where there is no folder to conflict with. */
  tagId: string | null;
  files: File[];
}

/** A name the destination folder already holds, awaiting the user's answer. */
export interface ImportConflict {
  tagId: string;
  /** The file's leaf name — what the folder holds and what the server keys on. */
  name: string;
  /** What to show the user: the path they dropped, folder included. */
  label: string;
}

/** Two files can carry the same leaf name in two different folders, so the
 * destination is part of the identity of a decision. */
export function conflictKey(tagId: string, name: string): string {
  return JSON.stringify([tagId, name]);
}

/** Leaf names a single destination would receive more than once.
 *
 * A folder cannot hold two documents under one name, and a decision about that
 * name cannot mean two things at once — replace would let one file silently
 * take the other's place. The user has to drop one of them first.
 */
export function namesArrivingTwice(groups: UploadGroup[]): string[] {
  const seenByTag = new Map<string, Set<string>>();
  const duplicates = new Set<string>();
  for (const group of groups) {
    const key = group.tagId ?? "";
    const seen = seenByTag.get(key) ?? new Set<string>();
    for (const file of group.files) {
      const name = leafFileName(file);
      if (seen.has(name)) duplicates.add(name);
      seen.add(name);
    }
    seenByTag.set(key, seen);
  }
  return [...duplicates];
}

/** What to ask the name-check route about: one entry per destination that has
 * a folder to conflict with. */
export function destinationsToCheck(groups: UploadGroup[]): ImportDestinationNames[] {
  const byTag = new Map<string, string[]>();
  for (const group of groups) {
    if (!group.tagId) continue;
    const names = byTag.get(group.tagId) ?? [];
    for (const file of group.files) names.push(leafFileName(file));
    byTag.set(group.tagId, names);
  }
  return Array.from(byTag, ([tag_id, names]) => ({ tag_id, names: Array.from(new Set(names)) }));
}

/** Pair the server's answer with the files it concerns, so the user is shown
 * the path they dropped rather than a bare leaf name. */
export function conflictsToAsk(
  groups: UploadGroup[],
  answer: ImportNameConflicts[],
  displayName: (file: File) => string,
): ImportConflict[] {
  const takenByTag = new Map(answer.map((entry) => [entry.tag_id, new Set(entry.names)]));
  const conflicts: ImportConflict[] = [];
  const seen = new Set<string>();
  for (const group of groups) {
    const tagId = group.tagId;
    const taken = tagId ? takenByTag.get(tagId) : undefined;
    if (!tagId || !taken) continue;
    for (const file of group.files) {
      const name = leafFileName(file);
      const key = conflictKey(tagId, name);
      if (!taken.has(name) || seen.has(key)) continue;
      seen.add(key);
      conflicts.push({ tagId, name, label: displayName(file) });
    }
  }
  return conflicts;
}

/** Split one group by what the user decided: what still goes up, and what they
 * chose to skip. A skipped file is never uploaded — sending its bytes for the
 * server to refuse is the transfer this whole check exists to avoid. */
export function splitByDecision(
  group: UploadGroup,
  decisions: Map<string, ConflictDecision>,
): { toUpload: File[]; skipped: File[] } {
  const toUpload: File[] = [];
  const skipped: File[] = [];
  for (const file of group.files) {
    const decision = group.tagId ? decisions.get(conflictKey(group.tagId, leafFileName(file))) : undefined;
    if (decision === "skip") skipped.push(file);
    else toUpload.push(file);
  }
  return { toUpload, skipped };
}

/** The decisions one request carries, keyed the way the server reads them: by
 * file name, within the single destination that request writes to. */
export function decisionsForGroup(
  group: UploadGroup,
  decisions: Map<string, ConflictDecision>,
): Record<string, ConflictDecision> {
  const forRequest: Record<string, ConflictDecision> = {};
  if (!group.tagId) return forRequest;
  for (const file of group.files) {
    const name = leafFileName(file);
    const decision = decisions.get(conflictKey(group.tagId, name));
    if (decision) forRequest[name] = decision;
  }
  return forRequest;
}
