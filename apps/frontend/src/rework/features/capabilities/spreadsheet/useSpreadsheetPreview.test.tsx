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

// A slow preview of the previous file must never show once the pane switched to
// another file, and the pane only shows the file of the conversation it belongs to.

import { act } from "react";
import { createRoot } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { SpreadsheetPreview } from "./types";

const state = vi.hoisted(() => ({
  pending: new Map<string, (body: string) => void>(),
  session: "s-1",
  slice: { sessionId: "s-1", current: null as unknown },
}));

vi.mock("../../../../utils/downloadUtils", () => ({
  fetchAuthedBlob: (url: string) =>
    new Promise((resolve) => state.pending.set(url, (body: string) => resolve(new Blob([body])))),
}));
vi.mock("../useOpenSessionId", () => ({ useOpenSessionId: () => state.session }));
vi.mock("react-redux", () => ({
  useSelector: (selector: (s: unknown) => unknown) => selector({ spreadsheetPreview: state.slice }),
}));

const { useSessionSpreadsheet, useSpreadsheetPreview } = await import("./useSpreadsheetPreview");

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let container: HTMLDivElement;
let root: ReturnType<typeof createRoot>;
let seen: ReturnType<typeof useSpreadsheetPreview> = { status: "loading" };

function Probe({ url }: { url: string }) {
  seen = useSpreadsheetPreview(url);
  return null;
}

const body = (name: string) => JSON.stringify({ version: 1, sheets: [{ name }] } as Partial<SpreadsheetPreview>);

beforeEach(() => {
  state.pending.clear();
  container = document.createElement("div");
  root = createRoot(container);
});

afterEach(async () => {
  await act(async () => root.unmount());
});

describe("useSpreadsheetPreview", () => {
  it("never shows the previous file's preview after a switch", async () => {
    await act(async () => root.render(<Probe url="/a.json" />));
    await act(async () => root.render(<Probe url="/b.json" />));
    expect(seen.status).toBe("loading");

    await act(async () => state.pending.get("/a.json")!(body("A")));
    expect(seen.status).toBe("loading");

    await act(async () => state.pending.get("/b.json")!(body("B")));
    expect(seen.status === "ready" && seen.preview.sheets[0].name).toBe("B");
  });

  it("reports an error for a body that is not a preview", async () => {
    await act(async () => root.render(<Probe url="/bad.json" />));
    await act(async () => state.pending.get("/bad.json")!('{"nope":1}'));
    expect(seen.status).toBe("error");
  });
});

describe("useSessionSpreadsheet", () => {
  it("returns the file only for the conversation that registered it", async () => {
    let current: unknown = "unset";
    function Session() {
      current = useSessionSpreadsheet();
      return null;
    }
    state.slice = { sessionId: "s-1", current: { preview_id: "a" } };
    state.session = "s-2";
    await act(async () => root.render(<Session />));
    expect(current).toBeNull();
    state.session = "s-1";
    await act(async () => root.render(<Session />));
    expect(current).toEqual({ preview_id: "a" });
  });
});
