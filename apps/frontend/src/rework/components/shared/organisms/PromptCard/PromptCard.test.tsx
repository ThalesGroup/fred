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
import type { PromptSummary } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key }),
}));

import PromptCard from "./PromptCard.tsx";

const PROMPT = { id: "p-1", name: "Weekly report", session_count: 0 } as PromptSummary;

let container: HTMLDivElement;
let root: Root;

function mount(props: Partial<React.ComponentProps<typeof PromptCard>> = {}) {
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => {
    root.render(<PromptCard prompt={PROMPT} onView={() => {}} {...props} />);
  });
}

function star(): HTMLButtonElement | null {
  return container.querySelector('button[aria-label="rework.teams.prompts.favorite.filter"]');
}

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("PromptCard favorite star", () => {
  it("shows no star where favorites do not apply", () => {
    // The marketplace and the `/` picker pass no toggle.
    mount();
    expect(star()).toBeNull();
  });

  it("reflects the prompt's favorite state", () => {
    mount({ prompt: { ...PROMPT, is_favorite: true }, onToggleFavorite: () => {} });
    expect(star()?.getAttribute("aria-pressed")).toBe("true");
  });

  it("toggles without opening the prompt behind it", async () => {
    const onView = vi.fn();
    const onToggleFavorite = vi.fn();
    mount({ onView, onToggleFavorite });
    expect(star()?.getAttribute("aria-pressed")).toBe("false");

    await act(async () => {
      star()?.dispatchEvent(new MouseEvent("click", { bubbles: true, cancelable: true }));
    });

    expect(onToggleFavorite).toHaveBeenCalledOnce();
    expect(onView).not.toHaveBeenCalled();
  });
});
