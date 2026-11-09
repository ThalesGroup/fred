// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { ChatMessage, LinkPart } from "../../../../../slices/runtime/runtimeOpenApi";
import { toThreadMessages } from "@rework/components/pages/ManagedChatPage/toThreadMessages";
import { AssistantTurn } from "./AssistantTurn";

const { showError, getToken } = vi.hoisted(() => ({ showError: vi.fn(), getToken: vi.fn(() => "fred-test-token") }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("../../../../../security/KeycloakService", () => ({ KeyCloakService: { GetToken: getToken } }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError }) }));
vi.mock("@shared/atoms/Icon/Icon", () => ({ default: () => null }));
vi.mock("@shared/molecules/ThoughtTrace/ThoughtTrace", () => ({ ThoughtTrace: () => null }));
vi.mock("@shared/molecules/ActionBar/ActionBar", () => ({ ActionBar: () => null }));
vi.mock("@shared/molecules/TokenUsageBadge/TokenUsageBadge", () => ({ TokenUsageBadge: () => null }));
vi.mock("@shared/molecules/MermaidBlock/MermaidBlock", () => ({ MermaidBlock: () => null }));
vi.mock("@shared/molecules/MindMapBlock", () => ({ MindMapBlock: () => null }));

// Disposable fixture identities, unrelated to the user's audit conversation.
const documentId = "33333333-3333-4333-8333-333333333333";
const path = `/control-plane/v1/spaces/11111111-1111-4111-8111-111111111111/sessions/22222222-2222-4222-8222-222222222222/files/${documentId}/content`;
const artifact: LinkPart = {
  type: "link",
  kind: "download",
  href: path,
  document_uid: documentId,
  file_name: "audit-conversation.md",
};
let container: HTMLDivElement;
let root: Root;
let fetchMock: ReturnType<typeof vi.spyOn>;
let save: ReturnType<typeof vi.spyOn>;

beforeEach(() => {
  vi.clearAllMocks();
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  fetchMock = vi.spyOn(globalThis, "fetch").mockImplementation(async () => new Response("Three decisions"));
  vi.spyOn(URL, "createObjectURL").mockReturnValue("blob:artifact");
  vi.spyOn(URL, "revokeObjectURL").mockImplementation(() => {});
  save = vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

function render(
  href = path,
  parts: LinkPart[] = [artifact],
  carrier: "stream" | "history" | "tool_result" = "stream",
  streaming = false,
) {
  // The live SSE adapter adds UI parts to the core message union at runtime.
  const message: Omit<ChatMessage, "parts"> & { parts: (ChatMessage["parts"][number] | LinkPart)[] } = {
    session_id: "22222222-2222-4222-8222-222222222222",
    exchange_id: "exchange",
    rank: 1,
    timestamp: "2026-11-09T05:00:00Z",
    role: "assistant",
    channel: "final",
    parts: [
      { type: "text", text: `[Download **the file**](${href} "Deliverable")` },
      ...(carrier === "stream" ? parts : []),
    ],
    metadata: carrier === "history" ? { ui_parts: parts } : undefined,
  };
  // Exercise the real history/stream fold, then the real Markdown and chip renderers.
  const toolResult = {
    ...message,
    rank: 0,
    role: "tool",
    channel: "tool_result",
    parts: [{ type: "tool_result", call_id: "publish", ok: true, content: "Published" }, ...parts],
  };
  const messages = carrier === "tool_result" ? [toolResult, message] : [message];
  const [turn] = toThreadMessages(JSON.parse(JSON.stringify(messages)), streaming);
  act(() => root.render(<AssistantTurn {...turn} />));
}

async function click(element: HTMLElement): Promise<boolean> {
  let intercepted = false;
  document.addEventListener(
    "click",
    (event) => {
      intercepted = event.defaultPrevented;
      event.preventDefault(); // Keep ordinary navigation out of this DOM test.
    },
    { once: true },
  );
  await act(async () => element.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true })));
  return intercepted;
}
const anchor = () => container.querySelector("a")!;
const chip = () =>
  container.querySelector<HTMLButtonElement>('button[aria-label="chatbot.artifactLinks.downloadAria"]')!;

it.each(["stream", "history"] as const)(
  "downloads a recognized artifact through the shared mechanism (%s)",
  async (carrier) => {
    render(path, [artifact], carrier);
    expect(anchor().querySelector("strong")?.textContent).toBe("the file");
    expect(anchor().title).toBe("Deliverable");
    expect(await click(anchor())).toBe(true);
    expect(fetchMock).toHaveBeenCalledWith(new URL(path, window.location.href).href, {
      headers: { Authorization: "Bearer fred-test-token" },
      redirect: "error",
    });
    expect(save).toHaveBeenCalledOnce();
    expect((save.mock.instances[0] as HTMLAnchorElement).download).toBe("audit-conversation.md");
    expect(chip()).not.toBeNull();
    await click(chip());
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenCalledTimes(2);
  },
);

it("activates the Markdown link only once structured parts arrive, including while streaming", async () => {
  render(path, [], "stream", true);
  expect(await click(anchor())).toBe(false);
  expect(fetchMock).not.toHaveBeenCalled();
  render(path, [artifact], "tool_result", true);
  expect(chip()).toBeNull();
  expect(await click(anchor())).toBe(true);
  expect(save).toHaveBeenCalledOnce();
  render();
  expect(chip()).not.toBeNull();
});

it.each(["relative", "absolute", "preview"])("matches the actual destination (%s)", async (form) => {
  const href = form === "preview" ? path.replace(/content$/, "preview") : path;
  const absolute = new URL(href, window.location.href).href;
  render(form === "relative" ? href : absolute, [{ ...artifact, href: form === "relative" ? absolute : href }]);
  expect(await click(anchor())).toBe(true);
  expect(fetchMock).toHaveBeenCalledWith(absolute, expect.objectContaining({ redirect: "error" }));
});

describe("untrusted Markdown destinations", () => {
  it.each([
    `https://external.example${path}`,
    `//external.example${path}`,
    `${path}/extra`,
    `${path}?redirect=https://external.example`,
    `${path}#fragment`,
    path.replace(documentId, "44444444-4444-4444-8444-444444444444"),
    path.replace("/sessions/", "/other/"),
    path.replace("/content", "/%63ontent"),
    "/control-plane/v1/me",
  ])("leaves an unrecognized URL as an ordinary link: %s", async (href) => {
    render(href);
    expect(await click(anchor())).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getToken).not.toHaveBeenCalled();
    expect(chip()).not.toBeNull();
  });

  it.each([
    `https://external.example${path}`,
    `//external.example${path}`,
    `http://localhost:9099${path}`,
    `http://localhost.evil.example${path}`,
    `http://user:password@localhost${path}`,
    "/control-plane/v1/me",
    `${path}?redirect=/other`,
  ])("does not trust an unsafe destination even when a structured download repeats it: %s", async (href) => {
    render(href, [{ ...artifact, href }]);
    expect(await click(anchor())).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getToken).not.toHaveBeenCalled();
  });

  it.each([
    { ...artifact, kind: "citation" as const },
    { ...artifact, kind: "external" as const },
    { ...artifact, document_uid: undefined },
    { ...artifact, document_uid: "other-document" },
  ])("requires a download reference with matching document identity: %j", async (part) => {
    render(path, [part]);
    expect(await click(anchor())).toBe(false);
    expect(fetchMock).not.toHaveBeenCalled();
  });

  it("preserves external citations as ordinary links in prose and structured parts", async () => {
    const href = "https://external.example/article";
    render(href, [{ type: "link", kind: "citation", href, title: "External citation" }]);
    const links = container.querySelectorAll("a");
    expect(links).toHaveLength(2);
    for (const link of links) {
      expect(link.href).toBe(href);
      expect(await click(link)).toBe(false);
    }
    expect(fetchMock).not.toHaveBeenCalled();
    expect(getToken).not.toHaveBeenCalled();
  });
});

it.each([401, 403, 404])("reports a rejected download (%s), keeps the chip and allows retry", async (status) => {
  fetchMock.mockResolvedValueOnce(new Response("Denied", { status }));
  render(path, [artifact], "history");
  expect(await click(anchor())).toBe(true);
  expect(save).not.toHaveBeenCalled();
  expect(showError).toHaveBeenCalledWith({ summary: "chatbot.artifactLinks.downloadFailed" });
  expect(chip()).not.toBeNull();
  await click(chip());
  expect(save).toHaveBeenCalledOnce();
});

it("reports a network or redirect failure without falling back to navigation", async () => {
  fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
  render();
  expect(await click(anchor())).toBe(true);
  expect(save).not.toHaveBeenCalled();
  expect(showError).toHaveBeenCalledOnce();
  expect(chip()).not.toBeNull();
});
