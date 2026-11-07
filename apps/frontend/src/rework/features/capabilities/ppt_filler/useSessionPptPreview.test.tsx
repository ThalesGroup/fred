// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it, vi } from "vitest";
import type { ConversationFile } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { openPreview, pptPreviewSlice, registerPreview, type PptPreviewState } from "./pptPreviewSlice";
import { useHasPptPreview, useSessionPptPreview } from "./useSessionPptPreview";
import type { PptPreviewPartData } from "./types";

const fixture = vi.hoisted(() => ({
  session: "s1",
  state: {} as { pptPreview: PptPreviewState },
  files: [] as ConversationFile[],
}));
vi.mock("react-redux", () => ({
  useSelector: (select: (state: typeof fixture.state) => unknown) => select(fixture.state),
}));
vi.mock("../useOpenSessionId", () => ({ useOpenSessionId: () => fixture.session }));
vi.mock("../../conversationFiles", async (original) => ({
  ...(await original<typeof import("../../conversationFiles")>()),
  useConversationFiles: () => ({
    files: fixture.session === "s1" ? fixture.files : [],
    spaceId: "space",
    sessionId: fixture.session,
  }),
}));
const deck: PptPreviewPartData = {
  type: "ppt_preview",
  preview_id: "deck",
  title: "Deck",
  pdf_download_url: "/old",
  version: "v1",
};
function file(id = "deck", preview: string | null = "v1"): ConversationFile {
  return {
    document_id: id,
    content_id: `${id}-content`,
    name: `${id}.pptx`,
    path: `${id}.pptx`,
    mime: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    size: 10,
    sha256: "a".repeat(64),
    updated_at: "2026-11-07T00:00:00Z",
    preview_content_id: preview,
  };
}
function read(session: string, state: PptPreviewState, files: ConversationFile[]) {
  fixture.session = session;
  fixture.state = { pptPreview: state };
  fixture.files = files;
  let result: PptPreviewPartData | null = null;
  let available = false;
  function Probe() {
    result = useSessionPptPreview();
    available = useHasPptPreview();
    return null;
  }
  renderToStaticMarkup(<Probe />);
  return { preview: result as PptPreviewPartData | null, available };
}
const empty = () => pptPreviewSlice.reducer(undefined, { type: "init" });
const selected = () => pptPreviewSlice.reducer(empty(), registerPreview({ sessionId: "s1", preview: deck }));

describe("catalogue-backed PowerPoint preview", () => {
  it("restores the latest saved preview without replaying message cards", () => {
    const result = read("s1", empty(), [file()]);
    expect(result.available).toBe(true);
    expect(result.preview?.preview_id).toBe("deck");
    expect(result.preview?.pdf_download_url).toBe("/control-plane/v1/spaces/space/sessions/s1/files/deck/preview");
  });
  it("uses the current content even when the message describes an older render", () => {
    expect(read("s1", selected(), [file("deck", "v2")]).preview?.version).toBe("v2");
  });
  it("does not revive an old preview while a replacement has none", () => {
    expect(read("s1", selected(), [file("deck", null)])).toEqual({ preview: null, available: false });
  });
  it("never carries another conversation's files into an empty or different conversation", () => {
    for (const session of ["s2", ""])
      expect(read(session, selected(), [file()])).toEqual({ preview: null, available: false });
  });
  it("keeps the selected deck when another card registers and moves only on explicit open", () => {
    const other = { ...deck, preview_id: "other" };
    const registered = pptPreviewSlice.reducer(selected(), registerPreview({ sessionId: "s1", preview: other }));
    expect(read("s1", registered, [file("other"), file()]).preview?.preview_id).toBe("deck");
    const opened = pptPreviewSlice.reducer(registered, openPreview({ sessionId: "s1", preview: other }));
    expect(read("s1", opened, [file("other"), file()]).preview?.preview_id).toBe("other");
  });
});
