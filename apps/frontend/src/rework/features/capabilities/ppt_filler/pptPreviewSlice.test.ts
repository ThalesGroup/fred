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

// pptPreviewSlice: the latest-deck fold + once-per-session-view auto-open
// budget behind the chat cards (Kea `usePptPreview` parity, reviewed flow:
// live fill, history replay, user-closed panel, session switch).

import { describe, expect, it } from "vitest";
import { chatSessionScopeChanged } from "../sessionScope";
import reducer, { previewSeen, selectPreview, type PptPreviewState } from "./pptPreviewSlice";
import type { PptPreviewPartData } from "./types";

function deck(id: string, version = "v1"): PptPreviewPartData {
  return {
    type: "ppt_preview",
    preview_id: id,
    title: `${id}.pptx`,
    pdf_download_url: `/knowledge-flow/v1/fs/download/${id}.preview.pdf`,
    version,
  };
}

const initial = (): PptPreviewState => reducer(undefined, { type: "@@init" });

describe("pptPreviewSlice", () => {
  it("makes the first seen deck current and consumes the auto-open budget", () => {
    const s1 = reducer(initial(), previewSeen(deck("a")));
    expect(s1.current?.preview_id).toBe("a");
    expect(s1.autoOpened).toBe(true);
  });

  it("later decks become current WITHOUT re-arming auto-open (history replay: latest wins)", () => {
    let s = initial();
    s = reducer(s, previewSeen(deck("a")));
    s = reducer(s, previewSeen(deck("b")));
    expect(s.current?.preview_id).toBe("b");
    expect(s.autoOpened).toBe(true);
  });

  it("re-seeing a deck (card remount) never overwrites an explicit selection", () => {
    let s = initial();
    s = reducer(s, previewSeen(deck("a")));
    s = reducer(s, previewSeen(deck("b")));
    s = reducer(s, selectPreview(deck("a"))); // user picked the older deck
    s = reducer(s, previewSeen(deck("b"))); // remount of deck b's card
    expect(s.current?.preview_id).toBe("a");
  });

  it("a re-fill (same preview_id, new version) is a NEW key and becomes current", () => {
    let s = initial();
    s = reducer(s, previewSeen(deck("a", "v1")));
    s = reducer(s, selectPreview(deck("a", "v1")));
    s = reducer(s, previewSeen(deck("a", "v2")));
    expect(s.current?.version).toBe("v2");
  });

  it("session scope change resets everything (deck never leaks across sessions, auto-open re-arms)", () => {
    let s = initial();
    s = reducer(s, previewSeen(deck("a")));
    s = reducer(s, chatSessionScopeChanged("other-session"));
    expect(s.current).toBeNull();
    expect(s.autoOpened).toBe(false);
    expect(s.seen).toEqual({});
  });
});
