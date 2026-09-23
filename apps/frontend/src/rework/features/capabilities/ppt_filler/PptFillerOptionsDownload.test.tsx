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

// Both option surfaces must offer the download, wired to the same state. The
// button's own behaviour is covered next door; what these assert is the wiring
// that the two surfaces can silently disagree on — and a staged file must not
// change what the button offers.

import { renderToStaticMarkup } from "react-dom/server";
import { beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));
vi.mock("react-router-dom", () => ({ Link: ({ children }: { children?: unknown }) => <a>{children as never}</a> }));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}));

// The download button stands in for itself, reporting the props each surface
// hands it: this is what the two surfaces could drift on.
vi.mock("./PptTemplateDownloadButton", () => ({
  PptTemplateDownloadButton: (props: Record<string, unknown>) => (
    <button
      data-download
      data-team={String(props.teamId)}
      data-instance={String(props.agentInstanceId)}
      data-name={String(props.agentDisplayName)}
      data-has-template={String(props.hasPersistedTemplate)}
      data-disabled={String(props.disabled)}
    />
  ),
}));

const analysis = vi.hoisted(() => ({
  value: {} as Record<string, unknown>,
}));
vi.mock("./usePptTemplateAnalysis", () => ({
  usePptTemplateAnalysis: () => analysis.value,
  useTemplateErrorText: () => () => "",
}));

const { PptFillerConfigForm } = await import("./PptFillerConfigForm");
const { PptFillerPackOptions } = await import("./PptFillerPackOptions");

const hookState = (overrides: Record<string, unknown> = {}) => ({
  stagedFile: undefined,
  hasPersistedTemplate: true,
  isAnalyzing: false,
  analyzeFailed: false,
  previewSlides: [],
  previewErrors: [],
  blockingError: null,
  stagedAnalyzedClean: false,
  handlePick: vi.fn(),
  handleClear: vi.fn(),
  errorText: () => "",
  ...overrides,
});

const props = {
  capabilityId: "ppt_filler",
  teamId: "team-a",
  agentInstanceId: "inst-1",
  agentDisplayName: "Revue mensuelle",
  disabled: false,
  configValues: {},
  onConfigChange: vi.fn(),
  assetFiles: {},
  onAssetFileChange: vi.fn(),
  onBlockingErrorChange: vi.fn(),
};

const attr = (markup: string, name: string) =>
  markup.match(new RegExp(`data-download[^>]*${name}="([^"]*)"`))?.[1] ?? null;

const surfaces = [
  ["Advanced view widget", PptFillerConfigForm],
  ["Simple view pack options", PptFillerPackOptions],
] as const;

describe.each(surfaces)("%s", (_label, Surface) => {
  const render = (overrides: Record<string, unknown> = {}) =>
    renderToStaticMarkup(<Surface {...props} {...overrides} />);

  beforeEach(() => {
    analysis.value = hookState();
  });

  it("offers the download, carrying the edited instance", () => {
    const markup = render();

    expect(markup).toContain("data-download");
    expect(attr(markup, "data-team")).toBe("team-a");
    expect(attr(markup, "data-instance")).toBe("inst-1");
    expect(attr(markup, "data-name")).toBe("Revue mensuelle");
    expect(attr(markup, "data-has-template")).toBe("true");
    expect(attr(markup, "data-disabled")).toBe("false");
  });

  it("hands down an absent instance id while the agent is being created", () => {
    const markup = render({ agentInstanceId: undefined, agentDisplayName: undefined });

    expect(markup).toContain("data-download");
    expect(attr(markup, "data-instance")).toBe("undefined");
  });

  it("reports no saved template when there is none", () => {
    analysis.value = hookState({ hasPersistedTemplate: false });

    expect(attr(render(), "data-has-template")).toBe("false");
  });

  it("keeps offering the SAVED template while a new file is staged", () => {
    analysis.value = hookState({ stagedFile: new File(["x"], "nouveau.pptx") });

    expect(attr(render(), "data-has-template")).toBe("true");
  });

  it("offers nothing to download when a file is staged on an agent with none saved", () => {
    analysis.value = hookState({
      hasPersistedTemplate: false,
      stagedFile: new File(["x"], "nouveau.pptx"),
    });

    expect(attr(render(), "data-has-template")).toBe("false");
  });
});
