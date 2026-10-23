// @vitest-environment jsdom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { MermaidBlock } from "./MermaidBlock";
import { MarkdownRenderer } from "../MarkdownRenderer/MarkdownRenderer";
import { renderMermaid } from "./mermaidRenderer";

const clipboard = vi.hoisted(() => vi.fn());
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard: clipboard }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("./mermaidRenderer", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./mermaidRenderer")>()),
  renderMermaid: vi.fn(),
}));

const svg = (label: string) =>
  `<svg><style>text{fill:var(--on-surface)}</style><defs><marker id="arrow"><path d="M0,0 L4,2"/></marker></defs><text>${label}</text><path marker-end="url(#arrow)"/></svg>`;
const renderMock = vi.mocked(renderMermaid);
let host: HTMLDivElement;
let root: Root;

beforeEach(() => {
  vi.stubGlobal("IS_REACT_ACT_ENVIRONMENT", true);
  document.documentElement.dataset.theme = "light";
  document.documentElement.dataset.uiTheme = "pebble";
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
  clipboard.mockReset().mockResolvedValue(true);
  renderMock.mockReset().mockImplementation(async (code) => svg(code));
});

afterEach(async () => {
  await act(async () => root.unmount());
  host.remove();
  vi.unstubAllGlobals();
});

async function render(code: string) {
  await act(async () => root.render(<MermaidBlock code={code} />));
}

function button(label: string, scope: ParentNode = host): HTMLButtonElement {
  return scope.querySelector<HTMLButtonElement>(`button[aria-label="${label}"]`)!;
}

describe("MermaidBlock interactions", () => {
  it("copies the original source without submitting a surrounding form", async () => {
    const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
    await act(async () =>
      root.render(
        <form onSubmit={submit}>
          <MermaidBlock code="original source" />
        </form>,
      ),
    );
    const copy = button("mermaid.copySource");
    expect(copy.type).toBe("button");
    await act(async () => copy.click());
    expect(clipboard).toHaveBeenCalledWith("", "original source");
    expect(button("common.copied")).not.toBeNull();
    expect(submit).not.toHaveBeenCalled();
  });

  it("keeps multiple diagrams and their enlarged copy isolated, then restores focus on Escape", async () => {
    await act(async () =>
      root.render(
        <>
          <MermaidBlock code="First" />
          <MermaidBlock code="Second" />
        </>,
      ),
    );
    const enlarge = button("mermaid.enlarge");
    await act(async () => enlarge.dispatchEvent(new MouseEvent("mouseover", { bubbles: true })));
    await act(async () => enlarge.click());
    const dialog = document.querySelector('[role="dialog"]')!;
    expect(dialog).not.toBeNull();
    const close = button("mermaid.close", dialog);
    expect(document.activeElement).toBe(close);
    expect(dialog.closest('[aria-hidden="true"]')).toBeNull();
    const allIds = [...document.querySelectorAll("[id]")].map((node) => node.id);
    expect(new Set(allIds).size).toBe(allIds.length);
    expect(document.querySelectorAll('[role="img"]')).toHaveLength(3);
    for (const view of document.querySelectorAll('[role="img"]')) {
      const reference = view
        .querySelector("path[marker-end]")!
        .getAttribute("marker-end")!
        .match(/#([^)'"\s]+)/)![1];
      expect(view.querySelector(`[id="${reference}"]`)).not.toBeNull();
    }
    await act(async () => close.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true })));
    expect(document.querySelector('[role="dialog"]')).toBeNull();
    expect(document.activeElement).toBe(enlarge);
  });

  it("refreshes a mounted diagram on a palette change as well as a mode change", async () => {
    await render("Question");
    await act(async () => {
      document.documentElement.dataset.uiTheme = "cloud";
    });
    await vi.waitFor(() => expect(renderMock).toHaveBeenCalledTimes(2));
    await act(async () => {
      document.documentElement.dataset.theme = "dark";
    });
    await vi.waitFor(() => expect(renderMock).toHaveBeenCalledTimes(3));
    expect(renderMock.mock.calls[2][2].dark).toBe(true);
  });

  it("ignores stale results when source changes while layout is pending", async () => {
    const pending = new Map<string, (value: string) => void>();
    renderMock.mockImplementation((code) => new Promise((resolve) => pending.set(code, resolve)));
    await render("Old");
    expect(host.querySelector('[role="status"]')).not.toBeNull();
    await render("New");
    await act(async () => pending.get("New")!(svg("Latest")));
    await act(async () => pending.get("Old")!(svg("Stale")));
    expect(host.querySelector('[role="img"]')!.textContent).toContain("Latest");
    expect(host.textContent).not.toContain("Stale");
  });

  it("keeps an enlarged view mounted while a new theme render is pending", async () => {
    await render("Question");
    await act(async () => button("mermaid.enlarge").click());
    const dialog = document.querySelector('[role="dialog"]');
    let finish!: (value: string) => void;
    renderMock.mockImplementationOnce(
      () =>
        new Promise((resolve) => {
          finish = resolve;
        }),
    );
    await act(async () => {
      document.documentElement.dataset.uiTheme = "cobalt";
    });
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
    await act(async () => finish(svg("Question")));
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
  });

  it("keeps errors readable and leaves source copy available", async () => {
    renderMock.mockRejectedValueOnce(new Error("Invalid diagram source"));
    await render("invalid source");
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("Invalid diagram source");
    expect(host.querySelector("svg")).toBeNull();
    await act(async () => button("mermaid.copySource").click());
    expect(clipboard).toHaveBeenCalledWith("", "invalid source");
  });

  it("keeps open Mermaid fences as source and renders only when the fence completes", async () => {
    const source = "```mermaid\nflowchart LR\n A --> B\n";
    await act(async () => root.render(<MarkdownRenderer text={source} streaming />));
    expect(renderMock).not.toHaveBeenCalled();
    expect(host.textContent).toContain("A --> B");
    await act(async () => root.render(<MarkdownRenderer text={`${source}\`\`\``} streaming />));
    expect(renderMock).toHaveBeenCalledTimes(1);
    expect(host.querySelector('[role="img"]')).not.toBeNull();
  });
});
