// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import type { CreationAssistantSettings } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
const h = vi.hoisted(() => ({
  data: undefined as CreationAssistantSettings | undefined,
  save: vi.fn(),
  reset: vi.fn(),
  query: vi.fn(),
  confirm: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialogProvider", () => ({
  useConfirmationDialog: () => ({ showConfirmationDialog: h.confirm }),
}));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useGetCreationAssistantSettingsQuery: (args: unknown) => {
    h.query(args);
    return { currentData: h.data, isFetching: false, isError: false };
  },
  usePatchCreationAssistantSettingsMutation: () => [h.save, { isLoading: false }],
  useResetCreationAssistantPromptMutation: () => [h.reset, { isLoading: false }],
}));
vi.mock("@shared/molecules/PromptEditor/PromptEditor", () => ({
  PromptEditor: ({ value, onChange, error }: { value: string; onChange: (v: string) => void; error?: string }) => (
    <>
      <textarea value={value} onChange={(e) => onChange(e.target.value)} />
      {error && <p role="alert">{error}</p>}
    </>
  ),
}));
vi.mock("@shared/molecules/Select/Select", () => ({
  default: ({
    value,
    options,
    onChange,
  }: {
    value: string;
    options: { value: string; label: string; disabled?: boolean }[];
    onChange: (v: string) => void;
  }) => (
    <select value={value} onChange={(e) => onChange(e.target.value)}>
      {options.map((o) => (
        <option key={o.value} value={o.value} disabled={o.disabled}>
          {o.label}
        </option>
      ))}
    </select>
  ),
}));
import CreationAssistantPane from "./CreationAssistantPane";
globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let host: HTMLDivElement;
const key = { source_id: "source", upstream_model_id: "model" };
function render(org = "org-1") {
  act(() => root.render(<CreationAssistantPane key={org} organizationId={org} />));
}
function button(suffix: string) {
  return [...host.querySelectorAll("button")].find((b) => b.textContent?.includes(`rework.platformPrompt.${suffix}`))!;
}
function type(value: string) {
  act(() => {
    const el = host.querySelector("textarea")!;
    Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(el, value);
    el.dispatchEvent(new Event("input", { bubbles: true }));
  });
}
function select(index: number, value: string) {
  act(() => {
    const el = host.querySelectorAll("select")[index];
    el.value = value;
    el.dispatchEvent(new Event("change", { bubbles: true }));
  });
}
beforeEach(() => {
  vi.clearAllMocks();
  h.save.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.reset.mockReturnValue({ unwrap: () => Promise.resolve() });
  h.data = {
    text: "Custom {language}",
    model: null,
    reasoning: false,
    missing_language_placeholder: false,
    text_updated_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
    defaults: [
      {
        runtime_id: "pod-a",
        platform_prompt: null,
        platform_instructions: null,
        creation_assistant_prompt: "A {language}",
        creation_assistant_prompt_revised_at: "2026-02-01",
        source_unavailable: false,
      },
      {
        runtime_id: "pod-b",
        platform_prompt: null,
        platform_instructions: null,
        creation_assistant_prompt: "B {language}",
        creation_assistant_prompt_revised_at: null,
        source_unavailable: false,
      },
    ],
    models: {
      default: key,
      offers: [
        { key, selectable: true, permitted: true, candidate: true, diagnostics: [], metadata: { reasoning: true } },
      ],
      policy: {
        permitted: [key],
        organization_id: "org-1",
        revision: 1,
        embedding_locked: false,
      },
      reasoning_default_on: [],
      options: {},
    },
  };
  host = document.createElement("div");
  document.body.append(host);
  root = createRoot(host);
});
afterEach(() => {
  act(() => root.unmount());
  host.remove();
});
it("keeps model-only writes sparse even when a shipped prompt is newer", async () => {
  render();
  select(0, JSON.stringify(["source", "model"]));
  await act(async () => button("save").click());
  expect(h.save).toHaveBeenCalledWith({ organizationId: "org-1", patchCreationAssistant: { model: key } });
});
it("explicitly saves unchanged text to acknowledge a newer default", async () => {
  render();
  await act(async () => button("save").click());
  expect(h.save).toHaveBeenCalledWith({
    organizationId: "org-1",
    patchCreationAssistant: { text: "Custom {language}" },
  });
});
it("previews each source without changing the organization override", () => {
  render();
  act(() => button("creationAssistant.viewDefault").click());
  select(1, "pod-b");
  expect(host.querySelector("pre")?.textContent).toBe("B {language}");
  expect(host.querySelector("textarea")?.value).toBe("Custom {language}");
  expect(h.save).not.toHaveBeenCalled();
});
it("does not promote a runtime default when only reasoning is saved", async () => {
  h.data!.text = null;
  render();
  act(() => host.querySelector<HTMLInputElement>('input[type="checkbox"]')!.click());
  await act(async () => button("save").click());
  expect(h.save).toHaveBeenCalledWith({ organizationId: "org-1", patchCreationAssistant: { reasoning: true } });
});
it("uses the dedicated creation model's reasoning support unless explicitly overridden", () => {
  const dedicated = { source_id: "source", upstream_model_id: "dedicated" };
  h.data!.models.policy.creation_assistant = dedicated;
  h.data!.models.offers.push({
    key: dedicated,
    selectable: true,
    permitted: true,
    candidate: true,
    diagnostics: [],
    metadata: { reasoning: false },
  });
  render();
  expect(host.querySelector<HTMLInputElement>('input[type="checkbox"]')!.disabled).toBe(true);
  select(0, JSON.stringify(["source", "model"]));
  expect(host.querySelector<HTMLInputElement>('input[type="checkbox"]')!.disabled).toBe(false);
});
it("resets only the text through the organization endpoint", async () => {
  render();
  act(() => button("creationAssistant.reset").click());
  await act(async () => h.confirm.mock.lastCall![0].onConfirm());
  expect(h.reset).toHaveBeenCalledWith({ organizationId: "org-1" });
  expect(h.save).not.toHaveBeenCalled();
});
it("preserves entered text after save errors", async () => {
  h.save.mockReturnValue({ unwrap: () => Promise.reject({ status: 422, data: { detail: "Invalid" } }) });
  render();
  type("Edited {language}");
  await act(async () => button("save").click());
  expect(host.querySelector("textarea")?.value).toBe("Edited {language}");
});
it("rejects blanks, reserved tags and overlong Unicode text", () => {
  render();
  for (const text of ["   ", "<platform_prompt>bad</platform_prompt>", "😀".repeat(20001)]) {
    type(text);
    expect((button("save") as HTMLButtonElement).disabled).toBe(true);
  }
  type("😀".repeat(20000));
  expect((button("save") as HTMLButtonElement).disabled).toBe(false);
});
it("does not reuse the previous organization's edited text", () => {
  render();
  type("Private draft");
  h.data = { ...h.data!, text: "Other org" };
  render("org-2");
  expect(host.querySelector("textarea")?.value).toBe("Other org");
  expect(h.query).toHaveBeenLastCalledWith({ organizationId: "org-2" });
});
it("shows unavailable sources distinctly and preserves a saved unavailable model", () => {
  h.data!.defaults[0].source_unavailable = true;
  h.data!.text = null;
  h.data!.model = { source_id: "withdrawn", upstream_model_id: "old" };
  render();
  expect(host.textContent).toContain("rework.platformPrompt.sourceUnavailable");
  expect(host.querySelector("option[disabled]")).not.toBeNull();
});
