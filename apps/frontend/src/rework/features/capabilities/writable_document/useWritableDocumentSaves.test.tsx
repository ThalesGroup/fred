// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createHash, randomUUID } from "node:crypto";
import { useWritableDocumentFiles } from "./useWritableDocumentFiles";
import type { CapabilityConversationFiles } from "../types";
import { createRoot } from "react-dom/client";
import { configureStore } from "@reduxjs/toolkit";
import { Provider } from "react-redux";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import reducer from "./writableDocumentSlice";
import { useWritableDocuments, type UseWritableDocuments } from "./useWritableDocuments";
const state = vi.hoisted(() => ({
  update: vi.fn(),
  read: vi.fn(),
  remove: vi.fn(),
  refetch: vi.fn(),
  docs: [{ document_id: "recipe", title: "Recipe", content_md: "Original", updated_at: "2026-11-21T10:00:00Z" }],
}));
vi.mock("./api/writableDocumentCapabilityOpenApi", () => ({
  writableDocumentCapabilityApi: { enhanceEndpoints: () => undefined },
  useListWritableDocumentsQuery: () => ({ currentData: state.docs, refetch: state.refetch }),
  useUpdateWritableDocumentMutation: () => [state.update],
  useLazyGetWritableDocumentQuery: () => [state.read],
  useDeleteWritableDocumentMutation: () => [state.remove],
}));
vi.mock("./WritableDocumentDownloadButton", () => ({ default: () => null }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../useCapabilityRouted", () => ({ useCapabilityRouted: () => true }));
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let store: ReturnType<typeof makeStore>;
const makeStore = () => configureStore({ reducer: { writableDocument: reducer } });
let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;
let editor: UseWritableDocuments;
let files: CapabilityConversationFiles;
function Probe({ session }: { session: string }) {
  editor = useWritableDocuments(session);
  files = useWritableDocumentFiles(session);
  return <div>{editor.documents[0]?.content_md}</div>;
}
async function render(session = "session") {
  await act(async () =>
    root.render(
      <Provider store={store}>
        <Probe session={session} />
      </Provider>,
    ),
  );
}
async function edit(text: string) {
  await act(async () => editor.onEditDocument("recipe", text));
}
async function tick() {
  await act(async () => vi.advanceTimersByTimeAsync(800));
}
beforeEach(() => {
  vi.useFakeTimers();
  vi.clearAllMocks();
  store = makeStore();
  state.read.mockImplementation(() => ({
    unwrap: async () => ({ ...state.docs[0], content_md: "Saved human correction" }),
  }));
  vi.stubGlobal("crypto", {
    randomUUID,
    subtle: {
      digest: async (_: string, data: Uint8Array) => new Uint8Array(createHash("sha256").update(data).digest()).buffer,
    },
  });
  state.update.mockImplementation(() => ({
    unwrap: async () => ({ ...state.docs[0], updated_at: "2026-11-21T10:01:00Z" }),
  }));
  container = document.createElement("div");
  root = createRoot(container);
});
afterEach(async () => {
  await act(async () => root.unmount());
  vi.useRealTimers();
  vi.unstubAllGlobals();
});
describe("editor saves before Wiki sharing", () => {
  it("blocks sharing immediately during debounce, then clears only on acknowledgement", async () => {
    await render();
    await edit("Human correction");
    expect(store.getState().writableDocument.saves["session/recipe"].status).toBe("saving");
    expect(state.update).not.toHaveBeenCalled();
    await tick();
    expect(store.getState().writableDocument.saves["session/recipe"]).toBeUndefined();
  });
  it("retains a failed correction across pane reopening and supports explicit retry", async () => {
    state.update.mockImplementationOnce(() => ({
      unwrap: async () => {
        throw new Error("network");
      },
    }));
    await render();
    await edit("Human correction");
    await tick();
    expect(editor.saveFailed).toBe(true);
    await act(async () => root.render(<div />));
    await render();
    expect(editor.documents[0].content_md).toBe("Human correction");
    await act(async () => editor.retrySave());
    await tick();
    expect(state.update.mock.calls[1][0].writableDocumentUpdate.content_md).toBe("Human correction");
    expect(editor.saveFailed).toBe(false);
  });
  it("serializes newer typing and does not let an earlier response unblock sharing", async () => {
    let finish!: (value: unknown) => void;
    state.update.mockImplementationOnce(() => ({
      unwrap: () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    }));
    await render();
    await edit("First");
    await tick();
    await edit("Second");
    await tick();
    expect(state.update).toHaveBeenCalledTimes(1);
    await act(async () => finish({ ...state.docs[0], content_md: "First" }));
    expect(state.update).toHaveBeenCalledTimes(2);
    expect(state.update.mock.calls[1][0].writableDocumentUpdate.content_md).toBe("Second");
    expect(editor.documents[0].content_md).toBe("Second");
  });
  it("prepares the saved human correction through the owner, never the stale row snapshot", async () => {
    await render();
    const body = await files.items[0].prepareWikiShare!();
    expect(body.writable_document).toEqual({
      document_id: "recipe",
      format: "md",
      sha256: createHash("sha256").update("Saved human correction").digest("hex"),
    });
    expect(state.read).toHaveBeenCalledWith({ sessionId: "session", documentId: "recipe" }, false);
  });
  it("refuses sharing during a failed save and when editing starts during source preparation", async () => {
    await render();
    let finish!: (value: unknown) => void;
    state.read.mockReturnValueOnce({
      unwrap: () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    });
    const preparation = files.items[0].prepareWikiShare!();
    await edit("New correction");
    finish(state.docs[0]);
    await expect(preparation).rejects.toMatchObject({ data: { code: "save_pending" } });
    state.update.mockReturnValueOnce({
      unwrap: async () => {
        throw new Error("network");
      },
    });
    await tick();
    await expect(files.items[0].prepareWikiShare!()).rejects.toMatchObject({ data: { code: "save_failed" } });
    expect(state.read).toHaveBeenCalledTimes(1);
  });
  it("flushes the old session on navigation without contaminating the new editor", async () => {
    await render();
    await edit("Old session correction");
    await render("other");
    expect(state.update.mock.calls[0][0].sessionId).toBe("session");
    expect(editor.documents[0].content_md).toBe("Original");
    expect(store.getState().writableDocument.saves["other/recipe"]).toBeUndefined();
  });
});
