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

import type { WikiConflictResponse } from "../../../slices/controlPlane/controlPlaneOpenApi";

export interface StaleWrite {
  currentContentMd: string;
  /** What the next save must use as its base, or the retry conflicts again. */
  currentRevisionId: string | null;
}

/** A stale-base write is the only 409 with a revision to rebase onto — a
 *  duplicate title or a has-children refusal reuses the same status code but
 *  carries `detail` only, so the shape (not the status) is what tells them
 *  apart. */
export function isWikiConflictResponse(data: unknown): data is WikiConflictResponse {
  const body = data as Partial<WikiConflictResponse> | undefined;
  return typeof body?.current_revision_id === "string" && typeof body?.current_content_md === "string";
}

export function conflictFrom(error: unknown): StaleWrite | null {
  const status = (error as { status?: number } | undefined)?.status;
  if (status !== 409) return null;
  const data = (error as { data?: unknown } | undefined)?.data;
  if (!isWikiConflictResponse(data)) return null;
  return {
    currentContentMd: data.current_content_md,
    currentRevisionId: data.current_revision_id,
  };
}

export function errorText(error: unknown): string {
  const detail = (error as { data?: { detail?: string } } | undefined)?.data?.detail;
  return detail ?? (error as { message?: string } | undefined)?.message ?? String(error);
}
