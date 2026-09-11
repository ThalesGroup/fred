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

// A duplicate-title 409 (e.g. the first-ever rules page racing a root page
// already titled "Rules") reuses the same HTTP status as a stale-base write's
// 409 — only the body shape tells them apart. conflictFrom must not read a
// revision to rebase onto out of a body that never carried one.

import { describe, expect, it } from "vitest";
import { conflictFrom, isWikiConflictResponse } from "./TeamWikiPage";

describe("isWikiConflictResponse", () => {
  it("accepts the canonical revision-conflict body", () => {
    expect(
      isWikiConflictResponse({
        detail: "This page has changed since your edit was prepared.",
        current_revision_id: "rev-1",
        current_content_md: "current text",
      }),
    ).toBe(true);
  });

  it("rejects a detail-only body (duplicate title, has-children, ...)", () => {
    expect(isWikiConflictResponse({ detail: "A page with this title already exists at the same level." })).toBe(false);
  });

  it("rejects undefined and non-object bodies", () => {
    expect(isWikiConflictResponse(undefined)).toBe(false);
    expect(isWikiConflictResponse("A page with this title already exists at the same level.")).toBe(false);
  });
});

describe("conflictFrom", () => {
  it("extracts the revision to rebase onto from a stale-base write's 409", () => {
    const error = {
      status: 409,
      data: {
        detail: "This page has changed since your edit was prepared.",
        current_revision_id: "rev-current",
        current_content_md: "someone else's text",
      },
    };

    expect(conflictFrom(error)).toEqual({
      currentContentMd: "someone else's text",
      currentRevisionId: "rev-current",
    });
  });

  it("returns null for a duplicate-title 409, rather than a fake empty revision", () => {
    const error = {
      status: 409,
      data: { detail: 'A page at the top level is already called "Rules". Rename it, then save the rules page again.' },
    };

    expect(conflictFrom(error)).toBeNull();
  });

  it("returns null for a non-409 error", () => {
    expect(conflictFrom({ status: 404, data: { detail: "This wiki page does not exist." } })).toBeNull();
  });
});
