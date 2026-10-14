// @vitest-environment happy-dom
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
// @vitest-environment happy-dom

// What these pin: the history keeps the administrator's order, resolves each
// note to the viewer's language, leaves out a note with nothing to show (so the
// position count matches what is readable), and reports the pending announcement.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

const queryMock = vi.fn();
let language = "fr";

vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  usePatchNoteHistoryQuery: () => queryMock(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language } }),
}));

import { usePatchNoteHistory } from "./usePatchNoteHistory";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

function read(): ReturnType<typeof usePatchNoteHistory> {
  let result!: ReturnType<typeof usePatchNoteHistory>;
  const Probe = () => {
    result = usePatchNoteHistory();
    return null;
  };
  const root = createRoot(document.createElement("div"));
  act(() => root.render(<Probe />));
  act(() => root.unmount());
  return result;
}

afterEach(() => {
  language = "fr";
  queryMock.mockReset();
});

describe("usePatchNoteHistory", () => {
  it("resolves the notes in the administrator's order", () => {
    queryMock.mockReturnValue({
      data: {
        patch_notes: [
          { id: "p2", title: { fr: "Version 3.4", en: "Release 3.4" }, description_long: { fr: "Corps", en: "Body" } },
          { id: "p1", title: { en: "Release 3.3" }, description_long: { en: "Older body" } },
        ],
        pending_announcement_id: "ann-1",
      },
    });

    expect(read()).toEqual({
      notes: [
        { id: "p2", title: "Version 3.4", markdown: "Corps" },
        // No French text: the English one is shown rather than nothing.
        { id: "p1", title: "Release 3.3", markdown: "Older body" },
      ],
      pendingAnnouncementId: "ann-1",
      loaded: true,
    });
  });

  it("leaves out a note with no text to show", () => {
    queryMock.mockReturnValue({
      data: {
        patch_notes: [
          { id: "p2", title: { fr: "Version 3.4" }, description_long: { fr: "  " } },
          { id: "p1", title: { fr: "Version 3.3" }, description_long: { fr: "Corps" } },
        ],
      },
    });

    expect(read().notes.map((note) => note.id)).toEqual(["p1"]);
    expect(read().pendingAnnouncementId).toBeNull();
  });

  it("is empty and not loaded before the first answer", () => {
    queryMock.mockReturnValue({ data: undefined });

    expect(read()).toEqual({ notes: [], pendingAnnouncementId: null, loaded: false });
  });
});
