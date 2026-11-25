// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CommonPromptSettings } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

const h = vi.hoisted(() => ({
  data: undefined as CommonPromptSettings | undefined,
  staleData: undefined as CommonPromptSettings | undefined,
  error: undefined as unknown,
  query: vi.fn(),
  save: vi.fn(),
  success: vi.fn(),
  failure: vi.fn(),
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.success, showError: h.failure }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetCommonPromptSettingsQuery: (args: unknown) => {
    h.query(args);
    return {
      currentData: h.data,
      data: h.staleData,
      isFetching: false,
      isError: !!h.error,
      error: h.error,
      refetch: h.refetch,
    };
  },
  usePutCommonPromptSettingsMutation: () => [h.save, { isLoading: false }],
}));
// Page behavior is independent of CodeMirror and the Select portal.
vi.mock("@shared/molecules/PromptEditor/PromptEditor.tsx", () => ({
  PromptEditor: ({
    value,
    onChange,
    error,
    disabled,
  }: {
    value: string;
    onChange: (text: string) => void;
    error?: string;
    disabled?: boolean;
  }) => (
    <>
      <textarea value={value} disabled={disabled} onChange={(event) => onChange(event.target.value)} />
      {error && <p role="alert">{error}</p>}
    </>
  ),
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({
  default: ({
    options,
    value,
    onChange,
  }: {
    options: { value: string; label: string }[];
    value: string;
    onChange: (value: string) => void;
  }) => (
    <select value={value} onChange={(event) => onChange(event.target.value)}>
      {options.map((option) => (
        <option key={option.value} value={option.value}>
          {option.label}
        </option>
      ))}
    </select>
  ),
}));
vi.mock("./CreationAssistantPane", () => ({
  default: ({ organizationId }: { organizationId: string }) => <p data-testid="creation-pane">{organizationId}</p>,
}));
import PlatformPromptPage from "./PlatformPromptPage";

declare global {
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let host: HTMLDivElement;
let root: Root;
function render(organizationId = "org-1", url = "/admin/platform-prompt") {
  act(() =>
    root.render(
      <MemoryRouter initialEntries={[url]}>
        <PlatformPromptPage organizationId={organizationId} />
      </MemoryRouter>,
    ),
  );
}
const button = (key: string) =>
  [...host.querySelectorAll("button")].find((item) => item.textContent?.includes(`rework.platformPrompt.${key}`))!;
const editor = () => host.querySelector("textarea")!;
function type(text: string) {
  act(() => {
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(editor(), text);
    editor().dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function select(runtimeId: string) {
  act(() => {
    const input = host.querySelector("select")!;
    input.value = runtimeId;
    input.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
async function save(key = "save") {
  await act(async () => button(key).click());
}
beforeEach(() => {
  vi.clearAllMocks();
  h.data = {
    text: "Common text",
    updated_by: null,
    updated_at: null,
    defaults: [
      {
        runtime_id: "ralph",
        platform_prompt: "Ralph default",
        platform_instructions: "Ralph instructions",
        source_unavailable: false,
      },
      {
        runtime_id: "react",
        platform_prompt: "React default",
        platform_instructions: "React instructions",
        source_unavailable: false,
      },
    ],
  };
  h.staleData = undefined;
  h.error = undefined;
  h.save.mockReturnValue({ unwrap: () => Promise.resolve() });
  host = document.createElement("div");
  document.body.appendChild(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});

describe("organization common prompt", () => {
  it("reads and saves only the active organization's text", async () => {
    render();
    expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-1" });
    expect(host.textContent).toContain("Ralph instructions");
    type("New common text");
    await save();
    expect(h.save).toHaveBeenCalledWith({ organizationId: "org-1", setCommonPrompt: { text: "New common text" } });
    expect(h.success).toHaveBeenCalledOnce();
  });
  it("previews each runtime and explicitly adopts one default as organization text", async () => {
    h.data!.text = null;
    render();
    expect(editor().value).toBe("Ralph default");
    expect(host.textContent).toContain("rework.platformPrompt.usingDefault");
    select("react");
    expect(editor().value).toBe("React default");
    expect(host.textContent).toContain("React instructions");
    expect(h.save).not.toHaveBeenCalled();
    await save("adoptDefault");
    expect(h.save).toHaveBeenCalledWith({ organizationId: "org-1", setCommonPrompt: { text: "React default" } });
  });
  it("keeps an explicit empty override and can copy a runtime default into its editor", () => {
    h.data!.text = "";
    render();
    select("react");
    expect(editor().value).toBe("");
    expect(host.textContent).toContain("rework.platformPrompt.suppressed");
    expect(button("save").disabled).toBe(true);
    act(() => button("useDefault").click());
    expect(editor().value).toBe("React default");
    expect(button("save").disabled).toBe(false);
  });
  it("persists explicit suppression instead of converting empty to null", async () => {
    h.data!.text = null;
    render();
    type("");
    await save();
    expect(h.save).toHaveBeenCalledWith({ organizationId: "org-1", setCommonPrompt: { text: "" } });
  });
  it("distinguishes an inaccessible default from an empty default and accepts explicit text", async () => {
    h.data!.text = null;
    h.data!.defaults[0].source_unavailable = true;
    h.data!.defaults[0].platform_prompt = null;
    render();
    expect(button("adoptDefault").disabled).toBe(true);
    expect(host.textContent).toContain("rework.platformPrompt.sourceUnavailable");
    type("Authored text");
    await save();
    expect(h.save).toHaveBeenCalledOnce();
  });
  it("keeps an override editable when no runtime is reachable", () => {
    h.data!.defaults = [];
    render();
    type("Edited override");
    expect(button("save").disabled).toBe(false);
  });
  it("does not replace a dirty draft when inspecting another source", () => {
    h.data!.text = null;
    render();
    type("Draft");
    select("react");
    expect(editor().value).toBe("Draft");
    act(() => button("reset").click());
    expect(editor().value).toBe("React default");
  });
  it("refuses reserved tags and counts Unicode code points", () => {
    render();
    type("</tools>");
    expect(button("save").disabled).toBe(true);
    expect(host.textContent).toContain("rework.promptEditor.reservedTag");
    type("😀".repeat(20_000));
    expect(button("save").disabled).toBe(false);
    type("😀".repeat(20_001));
    expect(button("save").disabled).toBe(true);
    expect(host.textContent).toContain("rework.platformPrompt.field.tooLong");
  });
  it("discards the prior draft and ignores stale query data after an organization change", () => {
    render();
    type("Org 1 draft");
    h.staleData = h.data;
    h.data = undefined;
    render("org-2");
    expect(host.querySelector("textarea")).toBeNull();
    expect(host.textContent).not.toContain("Common text");
    h.data = { ...h.staleData!, text: "Org 2 text" };
    render("org-2");
    expect(editor().value).toBe("Org 2 text");
    expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-2" });
  });
  it("isolates a late save result after changing organization", async () => {
    let resolve!: () => void;
    h.save.mockReturnValue({
      unwrap: () =>
        new Promise<void>((done) => {
          resolve = done;
        }),
    });
    render();
    type("Org 1 draft");
    act(() => button("save").click());
    h.data = { ...h.data!, text: "Org 2 text" };
    render("org-2");
    await act(async () => resolve());
    expect(editor().value).toBe("Org 2 text");
    expect(h.success).not.toHaveBeenCalled();
  });
  it("reports a refused save and retains the draft", async () => {
    h.save.mockReturnValue({ unwrap: () => Promise.reject({ status: 403, data: { detail: "Forbidden" } }) });
    render();
    type("Draft");
    await save();
    expect(h.success).not.toHaveBeenCalled();
    expect(h.failure).toHaveBeenCalledOnce();
    expect(editor().value).toBe("Draft");
  });
  it("shows query errors with retry instead of a blank editable prompt", () => {
    h.error = { status: 403 };
    render();
    expect(host.querySelector("textarea")).toBeNull();
    expect(host.textContent).toContain("rework.platformPrompt.loadFailed");
    act(() => host.querySelector<HTMLButtonElement>('[role="alert"] button')!.click());
    expect(h.refetch).toHaveBeenCalledOnce();
  });
  it("does not mount the legacy creation assistant during the transition", () => {
    render("org-1", "/admin/platform-prompt?tab=creation-assistant");
    expect(host.querySelector('[data-testid="creation-pane"]')?.textContent).toBe("org-1");
    expect(h.query).not.toHaveBeenCalled();
    act(() => button("tabs.system").click());
    expect(editor().value).toBe("Common text");
  });
});
