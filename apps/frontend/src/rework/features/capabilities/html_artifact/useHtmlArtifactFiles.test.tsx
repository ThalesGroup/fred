// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { afterEach, expect, it, vi } from "vitest";
import reducer from "./htmlArtifactSlice";
import { HtmlArtifactCardRenderer } from "./HtmlArtifactCardRenderer";
import { useHtmlArtifactFiles } from "./useHtmlArtifactFiles";
import type { CapabilityConversationFiles } from "../types";
vi.mock("../useOpenSessionId", () => ({ useMountSessionId: () => "session" }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("./HtmlArtifactDownloadButton", () => ({ default: () => <button>Download</button> }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
const container = document.createElement("div");
let root: ReturnType<typeof createRoot>;
afterEach(() => act(() => root.unmount()));
it("hydrates one drawer entry without a chat card and excludes another conversation", async () => {
  const store = configureStore({ reducer: { htmlArtifact: reducer } });
  let files!: CapabilityConversationFiles;
  function Probe({ session }: { session: string }) {
    files = useHtmlArtifactFiles(session);
    return null;
  }
  const part = {
    type: "html_artifact",
    artifact_id: "one",
    version: "v1",
    title: "Result",
    html: "<p>Hello</p>",
    css: "",
  };
  root = createRoot(container);
  await act(async () =>
    root.render(
      <Provider store={store}>
        <HtmlArtifactCardRenderer part={part as never} />
        <Probe session="session" />
      </Provider>,
    ),
  );
  expect(container.textContent).toBe("");
  expect(files.items.map((item) => item.name)).toEqual(["result.html"]);
  await act(async () =>
    root.render(
      <Provider store={store}>
        <Probe session="other" />
      </Provider>,
    ),
  );
  expect(files.items).toEqual([]);
});
