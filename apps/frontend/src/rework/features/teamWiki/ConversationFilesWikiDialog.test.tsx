// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { createHash, randomUUID } from "node:crypto";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { WikiShareFile } from "./wikiFileShare";

const state = vi.hoisted(() => ({
  propose: vi.fn(),
  close: vi.fn(),
  editor: true,
  pages: [{ page_id: "page", slug: "recipes", title: "Recipes", parent_page_id: null, kind: "page" }],
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useWikiAvailabilityQuery: () => ({ currentData: { enabled: true, can_publish: state.editor }, refetch: vi.fn() }),
  useWikiPagesQuery: () => ({ currentData: { pages: state.pages }, refetch: vi.fn() }),
  useProposeWikiFileMutation: () => [state.propose],
}));
import { ConversationFilesWikiDialog } from "./ConversationFilesWikiDialog";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: ReturnType<typeof createRoot>;
let container: HTMLDivElement;
let files: WikiShareFile[];
const prefix = "chatbot.sessionAttachments.share.";
async function render(session = "session") {
  await act(async () =>
    root.render(
      <MemoryRouter>
        <ConversationFilesWikiDialog
          key={session}
          sessionId={session}
          spaceId="space"
          spaceName="Cooking"
          wikiUrl="/team/space/wiki"
          files={files}
          onClose={state.close}
        />
      </MemoryRouter>,
    ),
  );
}
function button(key: string) {
  const found = [...document.querySelectorAll("button")].find((b) => b.textContent?.endsWith(key));
  if (!found) throw new Error(`Missing ${key}: ${document.body.textContent}`);
  return found;
}
async function click(element: HTMLElement) {
  await act(async () => element.click());
}
async function choose() {
  await click(document.querySelector<HTMLInputElement>('input[aria-label="Recipes"]')!);
}
beforeEach(() => {
  vi.clearAllMocks();
  sessionStorage.clear();
  state.editor = true;
  state.pages = [{ page_id: "page", slug: "recipes", title: "Recipes", parent_page_id: null, kind: "page" }];
  state.propose.mockImplementation(({ proposeWikiFileRequest: body }) => ({
    unwrap: async () => ({
      status: state.editor ? "published" : "pending",
      slug: "copy",
      proposal_id: body.document_id,
    }),
  }));
  files = ["one.pdf", "two.docx"].map((name) => ({
    key: name,
    name,
    prepareWikiShare: vi.fn(async () => ({ document_id: name })),
  }));
  vi.stubGlobal("crypto", {
    randomUUID,
    subtle: {
      digest: async (_: string, data: Uint8Array) => new Uint8Array(createHash("sha256").update(data).digest()).buffer,
    },
  });
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.unstubAllGlobals();
});

describe("conversation files to Wiki", () => {
  it.each([true, false])("shares one or many real files to one page; editor=%s", async (editor) => {
    state.editor = editor;
    await render();
    await choose();
    expect(state.propose).not.toHaveBeenCalled();
    await click(button(prefix + (editor ? "publish" : "submit")));
    expect(state.propose).toHaveBeenCalledTimes(2);
    expect(
      state.propose.mock.calls.every(([request]) => request.proposeWikiFileRequest.parent_slug === "recipes"),
    ).toBe(true);
    expect(document.querySelectorAll('a[href="/team/space/wiki/copy"]')).toHaveLength(editor ? 2 : 0);
    expect(button("common.close")).toBeTruthy();
  });
  it("does not prepare or publish before confirmation, and cancellation is inert", async () => {
    await render();
    await choose();
    await click(button("common.cancel"));
    expect(state.close).toHaveBeenCalled();
    expect(state.propose).not.toHaveBeenCalled();
    expect(files[0].prepareWikiShare).not.toHaveBeenCalled();
    expect(document.querySelector("pre")).toBeNull();
  });
  it("creates a destination as part of publishing, not while typing or cancelling", async () => {
    state.pages = [];
    await render();
    const input = document.querySelector<HTMLInputElement>('input:not([type="checkbox"])')!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "New recipes");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    expect(state.propose).not.toHaveBeenCalled();
    await click(button(prefix + "publish"));
    expect(state.propose.mock.calls[0][0].proposeWikiFileRequest).toMatchObject({ destination_title: "New recipes" });
  });
  it("does not offer page creation to a proposer without publication rights", async () => {
    state.editor = false;
    state.pages = [];
    await render();
    expect(document.body.textContent).toContain(prefix + "noPages");
    expect(document.body.textContent).not.toContain(prefix + "newPage");
    expect(button(prefix + "submit").disabled).toBe(true);
  });
  it("keeps successes and retries only the failure with the same uncertain request", async () => {
    let fail = true;
    state.propose.mockImplementation(({ proposeWikiFileRequest: body }) => ({
      unwrap: async () => {
        if (body.document_id === "two.docx" && fail) throw { status: "FETCH_ERROR" };
        return { status: "published", slug: "copy" };
      },
    }));
    await render();
    await choose();
    await click(button(prefix + "publish"));
    const first = state.propose.mock.calls[1][0];
    fail = false;
    await click(button("common.retry"));
    expect(state.propose).toHaveBeenCalledTimes(3);
    expect(state.propose.mock.calls[2][0]).toEqual(first);
    expect(files[1].prepareWikiShare).toHaveBeenCalledTimes(1);
  });
  it("reopens after a lost response with the exact saved request, despite a changed source", async () => {
    files = [files[0]];
    state.propose.mockReturnValue({
      unwrap: async () => {
        throw { status: "FETCH_ERROR" };
      },
    });
    await render();
    await choose();
    await click(button(prefix + "publish"));
    const first = state.propose.mock.calls[0][0];
    act(() => root.unmount());
    root = createRoot(container);
    files[0].prepareWikiShare = vi.fn(async () => ({ document_id: "changed" }));
    await render();
    await choose();
    await click(button(prefix + "publish"));
    expect(state.propose.mock.calls[1][0]).toEqual(first);
    expect(files[0].prepareWikiShare).not.toHaveBeenCalled();
  });
  it("replays a lost creation response when the now-existing destination is selected", async () => {
    files = [files[0]];
    state.pages = [];
    state.propose.mockReturnValue({
      unwrap: async () => {
        throw { status: "FETCH_ERROR" };
      },
    });
    await render();
    const input = document.querySelector<HTMLInputElement>('input:not([type="checkbox"])')!;
    await act(async () => {
      Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, "value")!.set!.call(input, "Recipes");
      input.dispatchEvent(new Event("input", { bubbles: true }));
    });
    await click(button(prefix + "publish"));
    const first = state.propose.mock.calls[0][0];
    act(() => root.unmount());
    root = createRoot(container);
    state.pages = [{ page_id: "page", slug: "recipes", title: "Recipes", parent_page_id: null, kind: "page" }];
    await render();
    await choose();
    await click(button(prefix + "publish"));
    expect(state.propose.mock.calls[1][0]).toEqual(first);
    expect(files[0].prepareWikiShare).toHaveBeenCalledTimes(1);
  });
  it.each(["save_failed", "save_pending"])("refuses an unsaved source: %s", async (code) => {
    files = [
      {
        ...files[0],
        prepareWikiShare: async () => {
          throw { data: { code } };
        },
      },
    ];
    await render();
    await choose();
    await click(button(prefix + "publish"));
    expect(state.propose).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alert"]')).not.toBeNull();
  });
  it("refreshes a changed source only on explicit retry after a definite refusal", async () => {
    files = [files[0]];
    state.propose.mockReturnValueOnce({
      unwrap: async () => {
        throw { status: 409, data: { code: "content_changed" } };
      },
    });
    await render();
    await choose();
    await click(button(prefix + "publish"));
    expect(document.body.textContent).toContain(prefix + "changed");
    await click(button("common.retry"));
    expect(files[0].prepareWikiShare).toHaveBeenCalledTimes(2);
    expect(state.propose.mock.calls[0][0]["Idempotency-Key"]).not.toBe(
      state.propose.mock.calls[1][0]["Idempotency-Key"],
    );
  });
  it("suppresses double clicks and stops the remaining batch after a conversation change", async () => {
    let release!: (value: unknown) => void;
    state.propose.mockReturnValue({
      unwrap: () =>
        new Promise((resolve) => {
          release = resolve;
        }),
    });
    await render();
    await choose();
    await act(async () => {
      button(prefix + "publish").click();
      button(prefix + "publish").click();
    });
    expect(state.propose).toHaveBeenCalledTimes(1);
    await render("another");
    await act(async () => release({ status: "published", slug: "copy" }));
    expect(state.propose).toHaveBeenCalledTimes(1);
    expect(document.querySelector('a[href="/team/space/wiki/copy"]')).toBeNull();
  });
});
