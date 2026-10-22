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
  refetch: vi.fn(),
  rerun: vi.fn(),
  reset: vi.fn(),
  saveOverrides: vi.fn(),
  upload: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  review: undefined as
    | undefined
    | { readOnly: boolean; onOverride: (id: string, patch: object) => void; onClose: () => void },
}));

const ok = (fn: (arg?: unknown) => void) =>
  vi.fn((arg?: unknown) => {
    fn(arg);
    return { unwrap: () => Promise.resolve({}) };
  });

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
vi.mock("react-redux", () => ({ useSelector: () => "/pod/capabilities/ppt_builder" }));
vi.mock("../useCapabilityRouted", () => ({ useCapabilityRouted: () => true }));
vi.mock("./api/pptBuilderCapabilityApi", () => ({ CAPABILITY_ID: "ppt_builder" }));
vi.mock("./api/pptBuilderCapabilityOpenApi", () => ({
  useGetPptBuilderPlatformQuery: () => ({ data: h.platform, isError: false, refetch: h.refetch }),
  useRerunPptBuilderPlatformAnalysisMutation: () => [ok(h.rerun), { isLoading: false }],
  useDeletePptBuilderPlatformTemplateMutation: () => [ok(h.reset), { isLoading: false }],
  usePutPptBuilderPlatformOverridesMutation: () => [ok(h.saveOverrides)],
}));
vi.mock("./uploadPlatformTemplate", () => ({ uploadPlatformTemplate: h.upload }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: h.showSuccess, showError: h.showError }),
}));
vi.mock("@shared/molecules/Select/Select.tsx", () => ({ default: () => null }));
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

import { platformVisionProfiles, PptBuilderPlatformPanel } from "./PptBuilderPlatformPanel";

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
        <PptBuilderPlatformPanel
          capability={CAPABILITY as CapabilityEnablementItem}
          allCapabilities={[]}
          canManage={canManage}
        />
      </MemoryRouter>,
    ),
  );
}

const text = () => container.textContent ?? "";
const button = (label: string) =>
  [...container.querySelectorAll("button")].find((b) => b.textContent?.includes(label)) as HTMLButtonElement;

beforeEach(() => {
  for (const fn of [h.refetch, h.rerun, h.reset, h.saveOverrides, h.upload, h.showSuccess, h.showError]) fn.mockReset();
  h.review = undefined;
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PptBuilderPlatformPanel", () => {
  it("shows the Fred template, and no write action to someone who is not a capability manager", () => {
    show({ analysis: null }, false);
    expect(text()).toContain(`${K}.fredTemplate`);
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

  it("says a failed first replacement leaves the Fred template in use", () => {
    show({ analysis: null, replacement: analysis({ status: "failed", error: "Broken file.", inventory: null }) });
    expect(text()).toContain(`${K}.failed.keepFred`);
    expect(text()).toContain("Broken file.");
    expect(button(`${K}.rerun`).disabled).toBe(false);
  });

  it("resets to the Fred template only once confirmed", async () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" });
    act(() => button(`${K}.reset`).click());
    expect(h.reset).not.toHaveBeenCalled();
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain(`${K}.resetConfirm.title`);
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
      vision_profile_id: null,
    });
    expect(h.showError).toHaveBeenCalledWith({
      summary: `${K}.uploadError`,
      detail: "The uploaded .pptx exceeds the 50 MB limit.",
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

  it("shows the review read only to someone who is not a capability manager", () => {
    show({ analysis: analysis(), template_filename: "brand.pptx" }, false);
    act(() => button("capability.ppt_builder.form.review").click());
    expect(h.review?.readOnly).toBe(true);
  });
});

describe("platformVisionProfiles", () => {
  it("offers each vision profile of the catalogue's model rows", () => {
    const rows = [
      { ...CAPABILITY, id: "m1", name: "M1", model_display_name: "Model one", vision_profile_ids: ["p1"] },
      { ...CAPABILITY, id: "m2", name: "M2", vision_profile_ids: [] },
    ] as CapabilityEnablementItem[];
    expect(platformVisionProfiles(rows)).toEqual([
      { profile_id: "p1", capability_id: "m1", name: "Model one", supports_vision: true },
    ]);
  });
});
