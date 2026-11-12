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

// Analysis states, the structural-analysis explanation and template controls.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { AnalysisStatusResponse, Pattern, TemplateInventory } from "./api/pptBuilderCapabilityOpenApi";

const i18nState = vi.hoisted(() => ({ language: "fr" }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: i18nState }),
}));
vi.mock("./PatternReviewDialog", () => ({ PatternReviewDialog: () => null }));

import { AnalysisStatus, PptBuilderTemplatePanel, TemplateGuideLink } from "./PptBuilderTemplatePanel";
import { PptBuilderVisionSettings } from "./PptBuilderVisionSettings";
import { analysisPhase, canRerun, type AnalysisPhase, type PptBuilderAnalysis } from "./usePptBuilderAnalysis";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

let container: HTMLDivElement;
let root: Root | null = null;

function cleanup() {
  if (!root) return;
  const mounted = root;
  act(() => mounted.unmount());
  container.remove();
  root = null;
}

function render(ui: React.ReactElement) {
  cleanup();
  container = document.createElement("div");
  document.body.appendChild(container);
  const mounted = createRoot(container);
  root = mounted;
  act(() => {
    mounted.render(ui);
  });
}

afterEach(cleanup);

function status(overrides: Partial<AnalysisStatusResponse>): AnalysisStatusResponse {
  return {
    status: "succeeded",
    template_sha256: "sha",
    labelling_key: "rules",
    analysis_version: 3,
    current: true,
    updated_at: "2026-10-05T10:00:00Z",
    ...overrides,
  };
}

function analysis(phase: AnalysisPhase, overrides: Partial<PptBuilderAnalysis> = {}): PptBuilderAnalysis {
  return {
    phase,
    statusLoading: false,
    stagedFile: undefined,
    hasPersistedTemplate: true,
    error: null,
    canRerun: false,
    retry: null,
    retrying: false,
    retryFailed: false,
    refreshing: false,
    effective: null,
    summary: null,
    droppedOverrides: [],
    previewSource: null,
    overrides: [],
    updateOverride: () => {},
    handlePick: () => {},
    handleClear: () => {},
    handleUsePlatformTemplate: () => {},
    ...overrides,
  };
}

describe("analysisPhase", () => {
  const file = new File(["x"], "deck.pptx");

  it("derives the phase from the staged file, the saved hash and the row", () => {
    expect(analysisPhase({ stagedFile: file, templateSha: "sha", status: status({}) })).toBe("staged");
    expect(analysisPhase({ stagedFile: undefined, templateSha: null, status: undefined })).toBe("builtin");
    expect(analysisPhase({ stagedFile: undefined, templateSha: "sha", status: undefined })).toBe("unknown");
    expect(analysisPhase({ stagedFile: undefined, templateSha: "new", status: status({}) })).toBe("unknown");
    expect(analysisPhase({ stagedFile: undefined, templateSha: "sha", status: status({ status: "running" }) })).toBe(
      "running",
    );
  });

  it("asks for a re-run only for failed, interrupted or outdated analyses", () => {
    expect(canRerun("failed", undefined)).toBe(true);
    expect(canRerun("interrupted", undefined)).toBe(true);
    expect(canRerun("succeeded", status({}))).toBe(false);
    expect(canRerun("succeeded", status({ current: false }))).toBe(true);
    expect(canRerun("running", status({ status: "running" }))).toBe(false);
  });
});

describe("AnalysisStatus", () => {
  it("says the analysis is in progress while pending or running", () => {
    for (const phase of ["pending", "running"] as const) {
      render(<AnalysisStatus analysis={analysis(phase)} />);
      expect(container.textContent).toContain("capability.ppt_builder.analysis.inProgress");
      expect(container.querySelector("button")).toBeNull();
    }
  });

  it("says an outdated analysis is being read again while it is refreshed", () => {
    render(<AnalysisStatus analysis={analysis("succeeded", { refreshing: true })} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.refreshing");
    expect(container.querySelector("button")).toBeNull();
  });

  it("shows the analysis error without offering a retry when CP has not authorized one", () => {
    render(<AnalysisStatus analysis={analysis("failed", { error: "The file has no slide.", canRerun: true })} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.failed");
    expect(container.textContent).toContain("The file has no slide.");
    expect(container.querySelector("button")).toBeNull();
  });

  it("offers a retry with an explanation that the draft is not submitted", () => {
    const retry = vi.fn(async () => {});
    render(<AnalysisStatus analysis={analysis("failed", { retry, retryFailed: true })} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.retrySavedTemplate");
    expect(container.textContent).toContain("capability.ppt_builder.analysis.retryFailed");
    act(() => container.querySelector("button")?.click());
    expect(retry).toHaveBeenCalledOnce();
    render(<AnalysisStatus analysis={analysis("failed", { retry, retrying: true })} />);
    expect(container.querySelector("button")?.disabled).toBe(true);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.retrying");
    render(<AnalysisStatus disabled analysis={analysis("failed", { retry })} />);
    expect(container.querySelector("button")?.disabled).toBe(true);
  });

  it("keeps an outdated analysis visible without promising a retry", () => {
    render(<AnalysisStatus analysis={analysis("succeeded", { canRerun: true })} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.outdated");
    expect(container.querySelector("button")).toBeNull();
  });

  it("names an interruption", () => {
    render(<AnalysisStatus analysis={analysis("interrupted", { canRerun: true })} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.interrupted");
  });

  it("stays silent once succeeded, and explains a staged file", () => {
    render(<AnalysisStatus analysis={analysis("succeeded")} />);
    expect(container.textContent).toBe("");
    render(<AnalysisStatus analysis={analysis("staged")} />);
    expect(container.textContent).toContain("capability.ppt_builder.analysis.staged");
  });
});

describe("PptBuilderVisionSettings", () => {
  it("keeps vision locked off with the structural-analysis explanation and no model picker", () => {
    render(<PptBuilderVisionSettings />);
    const toggle = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    expect(toggle.checked).toBe(false);
    expect(toggle.disabled).toBe(true);
    expect(container.textContent).toContain("capability.ppt_builder.fields.use_vision.unavailable");
    expect(container.querySelector("select")).toBeNull();
  });
});

describe("TemplateGuideLink", () => {
  it.each([
    ["fr", "/help/fr/guides/prepare-powerpoint-template"],
    ["en-GB", "/help/en/guides/prepare-powerpoint-template"],
  ])("opens the guide in the %s Help Center, in a new tab", (language, href) => {
    i18nState.language = language;
    render(
      <MemoryRouter>
        <TemplateGuideLink />
      </MemoryRouter>,
    );
    const link = container.querySelector("a") as HTMLAnchorElement;
    expect(link.textContent).toBe("capability.ppt_builder.form.templateGuide");
    expect(link.getAttribute("href")).toBe(href);
    expect(link.getAttribute("target")).toBe("_blank");
  });
});

describe("PptBuilderTemplatePanel", () => {
  const slide = (id: string, extra: Partial<Pattern> = {}) =>
    ({ id, source: "slide", label: id, kind: "bullets", ...extra }) as Pattern;
  const inventory = (patterns: Pattern[]): TemplateInventory => ({ slide_width: 1, slide_height: 1, patterns });

  function renderPanel(panelAnalysis: PptBuilderAnalysis) {
    render(
      <MemoryRouter>
        <PptBuilderTemplatePanel
          disabled={false}
          analysis={panelAnalysis}
          configValues={{}}
          onConfigChange={() => {}}
        />
      </MemoryRouter>,
    );
  }
  const advancedToggle = () =>
    [...container.querySelectorAll("button")].find((b) =>
      b.textContent?.includes("rework.teams.formAgent.advancedSettings"),
    ) as HTMLButtonElement;

  it("identifies the shared pod template without offering to remove it from the agent", () => {
    renderPanel(analysis("succeeded", { templateSource: "organization" }));
    expect(container.textContent).toContain("capability.ppt_builder.form.organizationTemplate");
    expect(container.textContent).not.toContain("capability.ppt_builder.form.usePlatformTemplate");
  });

  it("shows only the template and the plan approval by default", () => {
    const effective = inventory([slide("a"), slide("b", { included: false, exclusion_reason: "author" })]);
    renderPanel(analysis("succeeded", { effective, summary: { patterns: 1, excluded: 1 } }));
    const text = container.textContent ?? "";
    expect(text).toContain("capability.ppt_builder.form.replaceTemplate");
    expect(text).toContain("capability.ppt_builder.form.templateGuide");
    expect(text).toContain("capability.ppt_builder.fields.validate_plan.title");
    expect(text).not.toContain("capability.ppt_builder.form.review");
    expect(text).not.toContain("capability.ppt_builder.fields.use_vision.title");
    expect(text).not.toContain("capability.ppt_builder.fields.variety_check.title");
    expect(advancedToggle().getAttribute("aria-expanded")).toBe("false");
  });

  it("reveals the slide review, vision and variety settings once the advanced section is opened", () => {
    const effective = inventory([slide("a")]);
    renderPanel(analysis("succeeded", { effective, summary: { patterns: 1, excluded: 0 } }));
    act(() => advancedToggle().click());
    expect(advancedToggle().getAttribute("aria-expanded")).toBe("true");
    const text = container.textContent ?? "";
    expect(text).toContain("capability.ppt_builder.form.review");
    expect(text).toContain("capability.ppt_builder.fields.use_vision.title");
    expect(text).toContain("capability.ppt_builder.fields.variety_check.title");
  });

  it("offers a distinct action for a saved template, even while a replacement is staged", () => {
    const reset = vi.fn();
    renderPanel(
      analysis("staged", {
        stagedFile: new File(["deck"], "replacement.pptx"),
        handleUsePlatformTemplate: reset,
      }),
    );
    const button = [...container.querySelectorAll("button")].find(
      (item) => item.textContent === "capability.ppt_builder.form.usePlatformTemplate",
    );
    expect(button).toBeDefined();
    act(() => button?.click());
    expect(reset).toHaveBeenCalledOnce();

    renderPanel(analysis("builtin", { hasPersistedTemplate: false }));
    expect(container.textContent).not.toContain("capability.ppt_builder.form.usePlatformTemplate");
  });

  it("brings the slide review up when the analysis set slides aside", () => {
    const effective = inventory([slide("a"), slide("b", { included: false, exclusion_reason: "table" })]);
    renderPanel(analysis("succeeded", { effective, summary: { patterns: 1, excluded: 1 } }));
    expect(container.textContent).toContain("capability.ppt_builder.form.review");
    expect(advancedToggle().getAttribute("aria-expanded")).toBe("false");
    act(() => advancedToggle().click());
    const reviews = [...container.querySelectorAll("button")].filter((b) =>
      b.textContent?.includes("capability.ppt_builder.form.review"),
    );
    expect(reviews).toHaveLength(1);
  });
});
