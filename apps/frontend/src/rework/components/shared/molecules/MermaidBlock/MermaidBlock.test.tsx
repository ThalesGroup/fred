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
const download = vi.hoisted(() => vi.fn());
vi.mock("src/utils/downloadUtils", () => ({ downloadFile: download, downloadAuthed: vi.fn() }));
vi.mock("@rework/utils/clipboardUtils", () => ({ writeRichClipboard: clipboard }));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("./mermaidRenderer", async (importOriginal) => ({
  ...(await importOriginal<typeof import("./mermaidRenderer")>()),
  renderMermaid: vi.fn(),
}));

const svg = (label: string) =>
  `<svg viewBox="0 0 320 180"><style>text{fill:var(--on-surface)}</style><defs><marker id="arrow"><path d="M0,0 L4,2"/></marker></defs><text>${label}</text><path marker-end="url(#arrow)"/></svg>`;
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
  download.mockReset();
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
  it("downloads the current diagram from the second action with a white light-mode export", async () => {
    const submit = vi.fn((event: React.FormEvent) => event.preventDefault());
    document.documentElement.dataset.theme = "dark";
    await act(async () =>
      root.render(
        <form onSubmit={submit}>
          <MermaidBlock code="Generated graph" />
        </form>,
      ),
    );
    const source = host.querySelector("svg")!.outerHTML;
    expect([...host.querySelectorAll("button")].map((node) => node.getAttribute("aria-label"))).toEqual([
      "mermaid.enlarge",
      "mermaid.download",
      "mermaid.copySource",
    ]);
    const action = button("mermaid.download");
    expect(action.type).toBe("button");
    await act(async () => action.click());
    expect(download).toHaveBeenCalledWith(expect.any(Blob), "diagram.svg");
    expect(download.mock.calls[0][0].type).toBe("image/svg+xml;charset=utf-8");
    expect(renderMock.mock.lastCall![0]).toBe("Generated graph");
    expect(renderMock.mock.lastCall![2]).toMatchObject({ dark: false, colors: { bg: "#ffffff" } });
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(host.querySelector("svg")!.outerHTML).toBe(source);
    expect(document.querySelector('[id$="Export"]')).toBeNull();
    expect(submit).not.toHaveBeenCalled();
  });

  it("downloads from fullscreen and reports export failures without closing or replacing the graph", async () => {
    await render("Generated graph");
    await act(async () => button("mermaid.enlarge").click());
    const dialog = document.querySelector('[role="dialog"]')!;
    expect([...dialog.querySelectorAll("button")].map((node) => node.getAttribute("aria-label"))).toEqual([
      "mermaid.close",
      "mermaid.download",
    ]);
    await act(async () => button("mermaid.download", dialog).click());
    expect(download).toHaveBeenCalledTimes(1);
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
    download.mockImplementationOnce(() => {
      throw new Error("Download failed");
    });
    await act(async () => button("mermaid.download", dialog).click());
    expect(dialog.querySelector('[role="alert"]')?.textContent).toBe("mermaid.downloadError");
    expect(dialog.querySelector("svg")).not.toBeNull();
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
    expect(document.querySelector('[id$="Export"]')).toBeNull();
    await act(async () => button("mermaid.close", dialog).click());
    expect(document.activeElement).toBe(button("mermaid.enlarge"));
  });

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
    expect(button("mermaid.download")).toBeNull();
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
    expect(button("mermaid.download", dialog).disabled).toBe(true);
    await act(async () => finish(svg("Question")));
    expect(button("mermaid.download", dialog).disabled).toBe(false);
    expect(document.querySelector('[role="dialog"]')).toBe(dialog);
  });

  it("keeps errors readable and leaves source copy available", async () => {
    renderMock.mockRejectedValueOnce(new Error("Invalid diagram source"));
    await render("invalid source");
    expect(host.querySelector('[role="alert"]')?.textContent).toContain("Invalid diagram source");
    expect(host.querySelector("svg")).toBeNull();
    expect(button("mermaid.download")).toBeNull();
    await act(async () => button("mermaid.copySource").click());
    expect(clipboard).toHaveBeenCalledWith("", "invalid source");
  });

  it("shows a localized generating status without source until the Mermaid fence completes", async () => {
    const source = "```mermaid\nflowchart LR\n A --> B\n";
    await act(async () => root.render(<MarkdownRenderer text={source} streaming />));
    expect(renderMock).not.toHaveBeenCalled();
    expect(host.querySelector('[role="status"]')?.textContent).toBe("mermaid.generating");
    expect(host.textContent).not.toContain("A --> B");
    expect(host.textContent).not.toContain("flowchart LR");
    await act(async () => root.render(<MarkdownRenderer text={`${source}\`\`\``} streaming />));
    expect(renderMock).toHaveBeenCalledTimes(1);
    expect(host.querySelector('[role="img"]')).not.toBeNull();
  });
});
