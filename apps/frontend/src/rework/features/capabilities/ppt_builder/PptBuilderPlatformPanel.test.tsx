// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { act, type ComponentProps } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, afterEach, describe, expect, it, vi } from "vitest";
import type { PowerPointSettings, PowerPointFile } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import type { PatternReviewDialog } from "./PatternReviewDialog";
import type { TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";

const h = vi.hoisted(() => ({
  settings: undefined as PowerPointSettings | undefined,
  inventory: { patterns: [] } as TemplateInventory,
  review: null as ComponentProps<typeof PatternReviewDialog> | null,
  calls: [] as { name: string; arg: unknown }[],
  queryArgs: [] as unknown[],
  fail: false,
  refetch: vi.fn(),
}));
vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }) }));
vi.mock("react-redux", () => ({ useSelector: () => "/pod-a/ppt_builder" }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));
vi.mock("./PatternReviewDialog", () => ({
  PatternReviewDialog: (props: ComponentProps<typeof PatternReviewDialog>) => {
    h.review = props;
    return <div role="dialog">slide-review</div>;
  },
}));
vi.mock("../../../../slices/controlPlane/controlPlaneOpenApi", () => {
  const mutation = (name: string) => () => [
    (arg: unknown) => ({
      unwrap: async () => {
        h.calls.push({ name, arg });
        if (h.fail) throw { status: 409, data: { detail: "changed" } };
      },
    }),
    { isLoading: false },
  ];
  return {
    useGetPowerpointSettingsQuery: (arg: unknown) => {
      h.queryArgs.push(arg);
      return { currentData: h.settings, refetch: h.refetch };
    },
    usePutPowerpointSettingsMutation: mutation("corrections"),
    useRerunPowerpointTemplateMutation: mutation("rerun"),
  };
});
vi.mock("../../../../slices/controlPlane/controlPlaneApiEnhancements", () => {
  const mutation = (name: string) => () => [
    (arg: unknown) => ({
      unwrap: async () => {
        h.calls.push({ name, arg });
      },
    }),
    { isLoading: false },
  ];
  return {
    useUploadPowerpointTemplateMutation: mutation("upload"),
    useRemovePowerpointTemplateMutation: mutation("reset"),
  };
});
vi.mock("./api/pptBuilderCapabilityOpenApi", () => ({
  useGetPptBuilderBuiltinQuery: (arg: unknown) => {
    h.queryArgs.push(arg);
    return { currentData: { inventory: h.inventory } };
  },
  useGetPptBuilderAnalysisQuery: (arg: unknown) => {
    h.queryArgs.push(arg);
    return { currentData: { inventory: h.inventory, has_thumbnails: true, current: true } };
  },
}));
import { PptBuilderPlatformPanel } from "./PptBuilderPlatformPanel";

globalThis.IS_REACT_ACT_ENVIRONMENT = true;
let root: Root;
let container: HTMLDivElement;
const K = "capability.ppt_builder.platform";
const file = (id: string) => ({ id, name: `${id}.pptx` }) as PowerPointFile;
beforeEach(() => {
  h.calls = [];
  h.queryArgs = [];
  h.review = null;
  h.fail = false;
  h.settings = {
    current: {
      source: "builtin",
      file: null,
      activation_ready: true,
      preparation_state: "ready",
      preparation_error: null,
      analysis_reference: null,
    },
    replacement: null,
    config: {},
  };
  container = document.createElement("div");
  document.body.append(container);
  root = createRoot(container);
});
afterEach(() => {
  act(() => root.unmount());
  container.remove();
});
const render = (organizationId = "org-a", runtimeId = "pod-a", canManage = true) =>
  act(async () =>
    root.render(
      <MemoryRouter>
        <PptBuilderPlatformPanel
          key={`${organizationId}/${runtimeId}`}
          capability={{ id: "ppt_builder", name: "Builder" }}
          organizationId={organizationId}
          runtimeId={runtimeId}
          baseUrl="/pod-a/ppt_builder"
          canManage={canManage}
        />
      </MemoryRouter>,
    ),
  );
const click = (label: string) =>
  act(async () => {
    const button = [...document.querySelectorAll("button")].find((b) => b.textContent?.includes(label));
    expect(button).toBeDefined();
    button!.click();
  });

describe("Swift common-template drawer on Weaver", () => {
  it("uploads immediately on selection, keeps the guide/review and locks unavailable vision", async () => {
    await render();
    expect(container.textContent).toContain(`${K}.fredTemplate`);
    expect(container.textContent).toContain("capability.ppt_builder.form.review");
    expect(container.querySelector('a[target="_blank"]')?.getAttribute("href")).toContain(
      "prepare-powerpoint-template",
    );
    const vision = container.querySelector<HTMLInputElement>('input[type="checkbox"]')!;
    expect(vision.disabled).toBe(true);
    expect(vision.checked).toBe(false);
    const input = container.querySelector<HTMLInputElement>('input[type="file"]')!;
    const selected = new File(["deck"], "new.pptx");
    Object.defineProperty(input, "files", { value: [selected] });
    await act(async () => input.dispatchEvent(new Event("change", { bubbles: true })));
    expect(h.calls).toEqual([
      {
        name: "upload",
        arg: expect.objectContaining({ spaceId: "org-a", runtimeId: "pod-a", fileUpload: { file: selected } }),
      },
    ]);
    expect(container.textContent).not.toContain("common.save");
  });

  it("keeps the effective slides during a failed replacement and retries the candidate", async () => {
    h.settings!.current = {
      ...h.settings!.current,
      source: "organization",
      file: file("effective"),
      analysis_reference: "prep:effective",
    };
    h.settings!.replacement = {
      ...h.settings!.current,
      file: file("candidate"),
      preparation_state: "failed",
      preparation_error: "Cannot convert",
      analysis_reference: null,
    };
    await render();
    expect(container.textContent).toContain("Cannot convert");
    await click("capability.ppt_builder.form.review");
    expect(h.review?.previewSource).toEqual({
      kind: "analysis",
      instanceId: "prep:effective",
      spaceId: "org-a",
      baseUrl: "/pod-a/ppt_builder",
    });
    await act(async () => h.review?.onClose());
    await click(`${K}.rerun`);
    expect(h.calls[0]).toEqual({
      name: "rerun",
      arg: { spaceId: "org-a", runtimeId: "pod-a", powerPointChange: { expected_file_id: "candidate" } },
    });
    await click(`${K}.reset`);
    expect(h.calls).toHaveLength(1);
    await click(`${K}.resetConfirm.confirm`);
    expect(h.calls[1]).toEqual({
      name: "reset",
      arg: { spaceId: "org-a", runtimeId: "pod-a", expectedFileId: "candidate" },
    });
  });

  it("saves builtin corrections on review close, retaining edits on conflict and the reviewed file identity", async () => {
    await render();
    await click("capability.ppt_builder.form.review");
    await act(async () => h.review?.onOverride("slide:1", { label: "Cover" }));
    h.settings!.current.file = file("promoted-while-reviewing");
    h.fail = true;
    await render();
    await act(async () => h.review?.onClose());
    expect(container.textContent).toContain("slide-review");
    expect(h.calls[0]).toEqual({
      name: "corrections",
      arg: {
        spaceId: "org-a",
        runtimeId: "pod-a",
        powerPointSettingsChange: {
          expected_file_id: undefined,
          config: { overrides: [{ pattern_id: "slide:1", label: "Cover" }] },
        },
      },
    });
    h.fail = false;
    await act(async () => h.review?.onClose());
    expect(container.textContent).not.toContain("slide-review");
  });

  it("changes every query scope when another organization or pod is opened", async () => {
    await render();
    await click("capability.ppt_builder.form.review");
    await act(async () => h.review?.onOverride("slide:1", { included: false }));
    h.queryArgs = [];
    await render("org-b", "pod-b");
    expect(h.queryArgs.length).toBeGreaterThan(0);
    for (const arg of h.queryArgs) expect(arg).toMatchObject({ spaceId: "org-b", runtimeId: "pod-b" });
    expect(container.textContent).not.toContain("slide-review");
    expect(h.calls).toHaveLength(0);
  });

  it("offers no write control without organization permission", async () => {
    await render("org-a", "pod-a", false);
    expect(container.querySelector('input[type="file"]')).toBeNull();
    expect(h.calls).toHaveLength(0);
  });
});
