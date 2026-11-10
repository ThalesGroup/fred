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

// The platform template drawer: what it says in each state (the previous
// template stays in use while a replacement is analysed or failed), which
// actions only capability managers get, the reset confirmation, the upload
// error, and the slide edits saved when the review closes.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import type { CapabilityEnablementItem } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { AnalysisStatusResponse, PlatformTemplateResponse } from "./api/pptBuilderCapabilityOpenApi";

const h = vi.hoisted(() => ({
  platform: undefined as PlatformTemplateResponse | undefined,
  routed: true,
  builtin: undefined as { inventory: AnalysisStatusResponse["inventory"] } | undefined,
  refetch: vi.fn(),
  rerun: vi.fn(),
  reset: vi.fn(),
  saveOverrides: vi.fn(),
  upload: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  translate: vi.fn((key: string) => key),
  visionAvailability: vi.fn(),
  review: undefined as
    | undefined
    | {
        readOnly: boolean;
        previewSource: unknown;
        onOverride: (id: string, patch: object) => void;
        onClose: () => void;
      },
}));

const ok = (fn: (arg?: unknown) => void) =>
  vi.fn((arg?: unknown) => {
    fn(arg);
    return { unwrap: () => Promise.resolve({}) };
  });

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: h.translate, i18n: { language: "fr" } }),
}));
vi.mock("../../../../hooks/useFrontendProperties", () => ({
  useFrontendProperties: () => ({ siteDisplayName: "Acme" }),
}));
vi.mock("react-redux", () => ({ useSelector: () => "/pod/capabilities/ppt_builder" }));
vi.mock("../useCapabilityRouted", () => ({ useCapabilityRouted: () => h.routed }));
vi.mock("./api/pptBuilderCapabilityApi", () => ({ CAPABILITY_ID: "ppt_builder" }));
vi.mock("./api/pptBuilderCapabilityOpenApi", () => ({
  useGetPptBuilderPlatformQuery: () => ({ data: h.platform, isError: false, refetch: h.refetch }),
  useGetPptBuilderBuiltinQuery: (_arg: unknown, options: { skip?: boolean }) => ({
    data: options.skip ? undefined : h.builtin,
  }),
  useRerunPptBuilderPlatformAnalysisMutation: () => [ok(h.rerun), { isLoading: false }],
  useDeletePptBuilderPlatformTemplateMutation: () => [ok(h.reset), { isLoading: false }],
  usePutPptBuilderPlatformOverridesMutation: () => [ok(h.saveOverrides)],
}));
vi.mock("./uploadPlatformTemplate", () => ({ uploadPlatformTemplate: h.upload }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.showSuccess, showError: h.showError }),
}));
vi.mock("./useVisionAvailability", () => ({ useVisionAvailability: h.visionAvailability }));
vi.mock("./PatternReviewDialog", () => ({
  PatternReviewDialog: (props: NonNullable<typeof h.review>) => {
    h.review = props;
    return <div data-testid="review" />;
  },
}));
vi.mock("@shared/molecules/ConfirmationDialog/ConfirmationDialog", () => ({
  ConfirmationDialog: ({ open, onConfirm, title }: { open: boolean; onConfirm: () => void; title: string }) =>
    open ? (
      <div role="dialog">
        {title}
        <button onClick={onConfirm}>confirm</button>
      </div>
    ) : null,
}));

import { PptBuilderPlatformPanel } from "./PptBuilderPlatformPanel";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const K = "capability.ppt_builder.platform";
const CAPABILITY = {
  id: "ppt_builder",
  name: "n",
  version: "1",
  icon: "x",
  team_scope: "admin_gated",
  default_on: true,
};

const analysis = (fields: Partial<AnalysisStatusResponse> = {}): AnalysisStatusResponse => ({
  status: "succeeded",
  template_sha256: "sha",
  labelling_key: "rules",
  analysis_version: 1,
  current: true,
  updated_at: "t",
  has_thumbnails: true,
  inventory: {
    slide_width: 1,
    slide_height: 1,
    patterns: [{ id: "slide:1", source: "slide", source_index: 1, name: "A", label: "A", kind: "cover" }],
  },
  ...fields,
});

let container: HTMLDivElement;
let root: Root;

function show(platform: PlatformTemplateResponse, canManage = true) {
  h.platform = platform;
  act(() =>
    root.render(
      <MemoryRouter>
        <PptBuilderPlatformPanel capability={CAPABILITY as CapabilityEnablementItem} canManage={canManage} />
      </MemoryRouter>,
    ),
  );
}

const text = () => container.textContent ?? "";
const button = (label: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;

beforeEach(() => {
  for (const fn of [h.refetch, h.rerun, h.reset, h.saveOverrides, h.upload, h.showSuccess, h.showError]) fn.mockReset();
  h.translate.mockClear();
  h.visionAvailability.mockReset().mockReturnValue({ available: true });
  h.review = undefined;
  h.routed = true;
  h.builtin = { inventory: analysis().inventory };
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PptBuilderPlatformPanel", () => {
  it("uses the configured site name for the built-in template", () => {
    show({ analysis: null }, false);
    expect(text()).toContain(`${K}.builtinTemplate`);
    expect(h.translate).toHaveBeenCalledWith(`${K}.builtinTemplate`, { siteDisplayName: "Acme" });
    for (const action of [`${K}.upload`, `${K}.rerun`, `${K}.reset`, "use_vision.title"]) {
      expect(text()).not.toContain(action);
    }
  });

  it("keeps the current template in use while a replacement is analysed", () => {
    show({
      analysis: analysis(),
      template_filename: "brand.pptx",
      replacement: analysis({ status: "pending", inventory: null }),
      replacement_filename: "next.pptx",
    });
    expect(text()).toContain(`${K}.current`);
    expect(text()).toContain(`${K}.analysing.keepCurrent`);
    expect(text()).toContain(`${K}.replace`);
    expect(button(`${K}.rerun`).disabled).toBe(true);
  });

  it("says a failed first replacement leaves the built-in template in use", () => {
    show({ analysis: null, replacement: analysis({ status: "failed", error: "Broken file.", inventory: null }) });
    expect(text()).toContain(`${K}.failed.keepBuiltin`);
    expect(h.translate).toHaveBeenCalledWith(`${K}.failed.keepBuiltin`, { name: "", siteDisplayName: "Acme" });
    expect(text()).toContain("Broken file.");
    expect(button(`${K}.rerun`).disabled).toBe(false);
  });

  it("resets to the built-in template only once confirmed", async () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" });
    act(() => button(`${K}.reset`).click());
    expect(h.reset).not.toHaveBeenCalled();
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain(`${K}.resetConfirm.title`);
    expect(h.translate).toHaveBeenCalledWith(`${K}.resetConfirm.title`, { siteDisplayName: "Acme" });
    expect(h.translate).toHaveBeenCalledWith(`${K}.resetConfirm.message`, { siteDisplayName: "Acme" });
    await act(async () => button("confirm").click());
    expect(h.reset).toHaveBeenCalledTimes(1);
    expect(h.showSuccess).toHaveBeenCalledWith({ summary: `${K}.resetDone` });
  });

  it("shows the backend's reason when an upload is refused", async () => {
    h.upload.mockRejectedValue(new Error("The uploaded .pptx exceeds the 50 MB limit."));
    show({ analysis: null });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["x"], "big.pptx")] });
    await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.upload).toHaveBeenCalledWith("/pod/capabilities/ppt_builder", expect.any(File), {
      use_vision: true,
    });
    expect(h.showError).toHaveBeenCalledWith({
      summary: `${K}.uploadError`,
      detail: "The uploaded .pptx exceeds the 50 MB limit.",
    });
  });

  it("says when the upload fails without a reason from the server", async () => {
    h.upload.mockRejectedValue(new Error(""));
    show({ analysis: null });
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["x"], "big.pptx")] });
    await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.showError).toHaveBeenCalledWith({ summary: `${K}.uploadError`, detail: `${K}.uploadFailed` });
  });

  it("says the settings are unavailable when the capability cannot be reached", () => {
    h.routed = false;
    show({ analysis: null });
    expect(text()).toContain(`${K}.unavailable`);
    expect(text()).not.toContain(`${K}.loading`);
  });

  it("offers vision without a model selector", () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" });
    expect(text()).toContain("capability.ppt_builder.fields.use_vision.title");
    expect(container.querySelector("select")).toBeNull();
  });

  it("uploads with rules when Knowledge Flow vision is unavailable", async () => {
    h.visionAvailability.mockReturnValue({ available: false });
    show({ analysis: null });
    const toggle = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(toggle.disabled).toBe(true);
    const input = container.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["x"], "brand.pptx")] });
    await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.upload).toHaveBeenCalledWith("/pod/capabilities/ppt_builder", expect.any(File), {
      use_vision: false,
    });
  });

  it("lets a manager edit the slides and saves the edits when the review closes", async () => {
    show({ analysis: analysis(), template_filename: "brand.pptx", overrides: [] });
    act(() => button("capability.ppt_builder.form.review").click());
    expect(h.review?.readOnly).toBe(false);
    act(() => h.review?.onOverride("slide:1", { included: false }));
    await act(async () => h.review?.onClose());
    expect(h.saveOverrides).toHaveBeenCalledWith({
      platformOverridesRequest: { overrides: [{ pattern_id: "slide:1", included: false }] },
    });
  });

  it("lets a manager correct the built-in template's slides, cleared by the reset", async () => {
    show({ analysis: null, overrides: [] });
    expect(text()).not.toContain(`${K}.reset`);
    act(() => button("capability.ppt_builder.form.review").click());
    expect(h.review?.readOnly).toBe(false);
    expect(h.review?.previewSource).toEqual({ kind: "builtin" });
    act(() => h.review?.onOverride("slide:1", { label: "Opening" }));
    await act(async () => h.review?.onClose());
    expect(h.saveOverrides).toHaveBeenCalledWith({
      platformOverridesRequest: { overrides: [{ pattern_id: "slide:1", label: "Opening" }] },
    });

    show({ analysis: null, overrides: [{ pattern_id: "slide:1", label: "Opening" }] });
    expect(text()).toContain(`${K}.reset`);
    expect(text()).not.toContain(`${K}.rerun`);
  });

  it("shows the review read only to someone who is not a capability manager", () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" }, false);
    act(() => button("capability.ppt_builder.form.review").click());
    expect(h.review?.readOnly).toBe(true);
  });
});

describe("vision availability", () => {
  it("reads Knowledge Flow availability for capability managers", () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" });
    expect(h.visionAvailability).toHaveBeenLastCalledWith(false);
  });

  it("skips availability without the capability-manager right", () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" }, false);
    expect(h.visionAvailability).toHaveBeenLastCalledWith(true);
  });
});
