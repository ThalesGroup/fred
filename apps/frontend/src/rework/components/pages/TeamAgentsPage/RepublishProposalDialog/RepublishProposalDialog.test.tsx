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
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, opts?: Record<string, unknown>) => (opts ? `${key} ${JSON.stringify(opts)}` : key),
  }),
}));

import RepublishProposalDialog from "./RepublishProposalDialog";

let container: HTMLDivElement;
let root: Root;
const onPublish = vi.fn();
const onIgnore = vi.fn();

function render(blockedReason?: string) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(
      <RepublishProposalDialog
        open
        agentName="Helper"
        cause="reactivated"
        blockedReason={blockedReason}
        onPublish={onPublish}
        onIgnore={onIgnore}
      />,
    );
  });
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
  document.body.innerHTML = "";
  onPublish.mockClear();
  onIgnore.mockClear();
});

const button = (key: string) =>
  Array.from(document.querySelectorAll("button")).find((b) => b.textContent?.includes(key)) as HTMLButtonElement;

describe("RepublishProposalDialog", () => {
  it("stays open on a scrim click or Escape", () => {
    render();
    const dialog = document.querySelector('[role="alertdialog"]') as HTMLElement;
    act(() => (dialog.parentElement as HTMLElement).click());
    act(() => {
      window.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape" }));
    });
    expect(onIgnore).not.toHaveBeenCalled();
    expect(document.querySelector('[role="alertdialog"]')).not.toBeNull();
  });

  it("closes only through Publish or Ignore", () => {
    render();
    expect(document.body.textContent).toContain("rework.agentMarketplace.proposal.reactivated");
    act(() => button("proposal.ignore").click());
    expect(onIgnore).toHaveBeenCalledOnce();
    act(() => button("proposal.publish").click());
    expect(onPublish).toHaveBeenCalledOnce();
  });

  it("greys Publish and shows the quota reason when the quota is reached", () => {
    render("Quota reached");
    expect(button("proposal.publish").disabled).toBe(true);
    expect(document.body.textContent).toContain("Quota reached");
  });
});
