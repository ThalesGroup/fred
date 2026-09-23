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

// The button's three states: downloadable, unavailable (each reason), failing.
// The "unavailable" cases matter most — a template that IS saved but whose
// instance id never arrived would otherwise download nothing, silently.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

vi.mock("react-i18next", () => ({ useTranslation: () => ({ t: (key: string) => key }) }));

const showError = vi.hoisted(() => vi.fn());
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError }) }));

const downloadStoredTemplate = vi.hoisted(() => vi.fn());
// The button narrows on this class by identity, so the mock must be the same
// class the test throws — not a look-alike.
const Missing = vi.hoisted(() => class StoredTemplateMissingError extends Error {});
vi.mock("./templateDownload", () => ({
  downloadStoredTemplate: (...args: unknown[]) => downloadStoredTemplate(...args),
  StoredTemplateMissingError: Missing,
}));

const { PptTemplateDownloadButton } = await import("./PptTemplateDownloadButton");

describe("PptTemplateDownloadButton", () => {
  let container: HTMLDivElement;
  let root: Root;

  const show = (props: Partial<Parameters<typeof PptTemplateDownloadButton>[0]> = {}) =>
    act(() => {
      root.render(<PptTemplateDownloadButton hasPersistedTemplate disabled={false} {...props} />);
    });

  const button = () => container.querySelector("button") as HTMLButtonElement | null;
  const click = () => act(() => void button()?.click());
  const settle = async () => {
    await act(async () => {
      await Promise.resolve();
    });
  };

  beforeEach(() => {
    downloadStoredTemplate.mockReset();
    downloadStoredTemplate.mockResolvedValue(undefined);
    showError.mockReset();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it("downloads the saved template of the edited instance", async () => {
    show({ teamId: "team-a", agentInstanceId: "inst-1", agentDisplayName: "Revue mensuelle" });
    expect(button()?.disabled).toBe(false);

    click();
    await settle();

    expect(downloadStoredTemplate).toHaveBeenCalledWith("team-a", "inst-1", "Revue mensuelle");
    expect(showError).not.toHaveBeenCalled();
  });

  it("stays visible but unavailable when no template is saved", () => {
    show({ teamId: "team-a", agentInstanceId: "inst-1", hasPersistedTemplate: false });

    expect(button()).not.toBeNull();
    expect(button()?.disabled).toBe(true);
  });

  it("stays unavailable while the agent is being created, template or not", () => {
    show({ teamId: "team-a", agentInstanceId: undefined });

    expect(button()?.disabled).toBe(true);
  });

  it("stays unavailable with no team in context", () => {
    show({ teamId: undefined, agentInstanceId: "inst-1" });

    expect(button()?.disabled).toBe(true);
  });

  it("says WHY it is unavailable, on the wrapper a disabled button cannot carry", () => {
    show({ teamId: "team-a", agentInstanceId: "inst-1", hasPersistedTemplate: false });

    expect(container.querySelector("span[title]")?.getAttribute("title")).toBe(
      "capability.ppt_filler.form.downloadTemplateUnavailable",
    );
  });

  it("says what it offers when it is available", () => {
    show({ teamId: "team-a", agentInstanceId: "inst-1" });

    expect(container.querySelector("span[title]")?.getAttribute("title")).toBe(
      "capability.ppt_filler.form.downloadTemplateHint",
    );
  });

  it("follows the form's own disabled state while saving", () => {
    show({ teamId: "team-a", agentInstanceId: "inst-1", disabled: true });

    expect(button()?.disabled).toBe(true);
  });

  it("tells the administrator when the template file itself is gone", async () => {
    downloadStoredTemplate.mockRejectedValue(new Missing("Download failed (404)"));
    show({ teamId: "team-a", agentInstanceId: "inst-1" });

    click();
    await settle();

    expect(showError.mock.calls[0][0]).toMatchObject({
      summary: "capability.ppt_filler.form.downloadMissing",
    });
  });

  it("reports a failed download instead of failing silently", async () => {
    downloadStoredTemplate.mockRejectedValue(new Error("Download failed (404)"));
    show({ teamId: "team-a", agentInstanceId: "inst-1" });

    click();
    await settle();

    expect(showError).toHaveBeenCalledTimes(1);
    expect(showError.mock.calls[0][0]).toMatchObject({
      summary: "capability.ppt_filler.form.downloadFailed",
      detail: "Download failed (404)",
    });
    // Comes back enabled: a failure must not leave it stuck mid-download.
    expect(button()?.disabled).toBe(false);
  });
});
