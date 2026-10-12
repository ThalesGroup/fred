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

// The author's team is rendered checked because it already holds the prompt —
// an empty disabled box states the opposite. The trap this locks down is
// rendering it checked by adding it to the submitted set, which would make
// the import target the team that already owns the prompt.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, describe, expect, it, vi } from "vitest";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const importCalls: unknown[] = [];
const showError = vi.fn();
let importResults: { team_id: string; error?: string; error_code?: string }[] = [];

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({
  useToast: () => ({ showError, showSuccess: () => {} }),
}));
vi.mock("../../../../../../hooks/useFrontendBootstrap", () => ({
  useFrontendBootstrap: () => ({
    activeTeam: { id: "personal" },
    availableTeams: [
      { id: "origin-team", name: "Origin team", my_relations: ["team_editor"] },
      { id: "other-team", name: "Other team", my_relations: ["team_editor"] },
    ],
  }),
}));
vi.mock("../../../../../../slices/controlPlane/controlPlaneOpenApi", () => ({
  usePostMarketplacePromptImportControlPlaneV1MarketplacePromptsPromptIdImportPostMutation: () => [
    (arg: unknown) => {
      importCalls.push(arg);
      return { unwrap: async () => ({ results: importResults }) };
    },
    { isLoading: false },
  ],
}));

import ImportPromptDialog from "./ImportPromptDialog";

function rowFor(name: string): HTMLElement | null {
  return Array.from(document.querySelectorAll("label")).find((el) => el.textContent?.includes(name)) ?? null;
}

function checkboxFor(name: string): HTMLInputElement | null {
  return (rowFor(name)?.querySelector("input[type=checkbox]") as HTMLInputElement | null) ?? null;
}

describe("ImportPromptDialog origin team", () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = () => {
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
    act(() => {
      root.render(
        <ImportPromptDialog
          open
          promptId="p-1"
          promptName="Weekly review"
          originTeamId="origin-team"
          onClose={() => {}}
        />,
      );
    });
  };

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    importCalls.length = 0;
    importResults = [];
    showError.mockClear();
  });

  it("localizes a reserved skill command import error", async () => {
    importResults = [{ team_id: "other-team", error: "ENGLISH SERVER DETAIL", error_code: "prompt_command_reserved" }];
    render();
    act(() => {
      checkboxFor("Other team")!.click();
    });
    const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find(
      (b) => b.textContent?.trim() === "rework.marketplace.prompts.import.confirm",
    );
    await act(async () => {
      (confirm as HTMLButtonElement)?.click();
    });
    expect(showError).toHaveBeenCalledWith(
      expect.objectContaining({ detail: "rework.teams.prompts.form.commandReserved" }),
    );
  });

  it("renders the author's team checked and not selectable", () => {
    render();
    const origin = checkboxFor("Origin team");
    expect(origin).not.toBeNull();
    expect(origin!.checked).toBe(true);
    expect(origin!.disabled).toBe(true);
  });

  it("does not submit the author's team as an import target", async () => {
    render();
    const other = checkboxFor("Other team")!;
    act(() => {
      other.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    const confirm = Array.from(document.querySelectorAll('[role="dialog"] button')).find(
      (b) => b.textContent?.trim() === "rework.marketplace.prompts.import.confirm",
    );
    await act(async () => {
      confirm?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(importCalls).toHaveLength(1);
    const body = (importCalls[0] as { marketplaceImportRequest: { target_team_ids: string[] } })
      .marketplaceImportRequest;
    expect(body.target_team_ids).toEqual(["other-team"]);
    expect(body.target_team_ids).not.toContain("origin-team");
  });
});
