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

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
    i18n: { language: "en" },
  }),
}));

import PublishAgentDialog from "./PublishAgentDialog";

let container: HTMLDivElement;
let root: Root;
const onConfirm = vi.fn();

function render(
  fileNames: string[] = ["PowerPoint filler"],
  republish = false,
  usage: { publishedCount?: number; quota?: number } = { publishedCount: 3, quota: 5 },
) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <MemoryRouter>
        <PublishAgentDialog
          open
          agentName="Helper"
          republish={republish}
          fileNames={fileNames}
          publishedCount={usage.publishedCount}
          quota={usage.quota}
          onCancel={vi.fn()}
          onConfirm={onConfirm}
        />
      </MemoryRouter>,
    );
  });
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  onConfirm.mockClear();
});

const confirmButton = () =>
  Array.from(document.querySelectorAll("button")).find((b) =>
    b.textContent?.includes("publishDialog.confirm"),
  ) as HTMLButtonElement;

describe("PublishAgentDialog", () => {
  it("keeps the confirm action disabled until I understand is ticked", () => {
    render();
    expect(confirmButton().disabled).toBe(true);
    act(() => confirmButton().click());
    expect(onConfirm).not.toHaveBeenCalled();

    const checkbox = document.querySelector('input[type="checkbox"]') as HTMLInputElement;
    act(() => checkbox.click());
    expect(confirmButton().disabled).toBe(false);
    act(() => confirmButton().click());
    expect(onConfirm).toHaveBeenCalledOnce();
  });

  it("shows the quota usage, the files sentence and the Help Center link", () => {
    render();
    const text = document.body.textContent ?? "";
    expect(text).toContain('rework.agentMarketplace.publishDialog.quota {"count":3,"quota":5}');
    expect(text).toContain('rework.agentMarketplace.publishDialog.files {"names":"PowerPoint filler"}');
    const link = document.querySelector("a") as HTMLAnchorElement;
    expect(link.getAttribute("href")).toBe("/help/en/features/agents#the-agents-marketplace");
  });

  it("says when this publication takes the team's last slot, but not for a republish", () => {
    render(["PowerPoint filler"], false, { publishedCount: 4, quota: 5 });
    expect(document.body.textContent).toContain('publishDialog.quotaLast {"count":4,"quota":5}');
    act(() => root.unmount());
    container.remove();
    render(["PowerPoint filler"], true, { publishedCount: 4, quota: 5 });
    expect(document.body.textContent).not.toContain("quotaLast");
  });

  it("omits the quota line when the team's marketplace data is missing", () => {
    render(["PowerPoint filler"], false, {});
    expect(document.body.textContent).not.toContain("publishDialog.quota");
  });

  it("omits the files sentence when the agent holds no configuration file", () => {
    render([]);
    expect(document.body.textContent).not.toContain("publishDialog.files");
  });

  it("uses the republish wording for a published agent", () => {
    render([], true);
    expect(document.body.textContent).toContain("publishDialog.titleRepublish");
    expect(confirmButton().textContent).toContain("publishDialog.confirmRepublish");
  });
});
