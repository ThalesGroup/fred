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
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const navigate = vi.hoisted(() => vi.fn());
vi.mock("react-router-dom", () => ({ useNavigate: () => navigate }));
vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
vi.mock("@shared/atoms/Icon/Icon.tsx", () => ({ default: () => null }));
vi.mock("../../../../../hooks/useFrontendProperties.ts", () => ({
  useFrontendProperties: () => ({ agentIconName: "person" }),
}));

import HomeAskBox from "./HomeAskBox";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const agent = {
  agent_instance_id: "gen",
  team_id: "everyone",
  template_id: "tpl",
  display_name: "Généraliste",
  role: "Assistant",
  status: "enabled" as const,
};

let container: HTMLDivElement;
let root: Root;
const field = () => container.querySelector("textarea") as HTMLTextAreaElement;
const sendButton = () => container.querySelector('button[type="submit"]') as HTMLButtonElement;

function type(value: string) {
  Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value")!.set!.call(field(), value);
  act(() => {
    field().dispatchEvent(new Event("input", { bubbles: true }));
  });
}

beforeEach(() => {
  navigate.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
  act(() => root.render(<HomeAskBox agent={agent} />));
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("HomeAskBox", () => {
  it("offers text only, and sends nothing while empty", () => {
    expect(container.querySelector('input[type="file"]')).toBeNull();
    type("   ");
    expect(sendButton().disabled).toBe(true);
    act(() => field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(navigate).not.toHaveBeenCalled();
  });

  it("opens a new conversation with the agent and the question in router state", () => {
    type("  Traduis ce mail  ");
    act(() => field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(navigate).toHaveBeenCalledWith("/team/everyone/managed-chat/gen", {
      state: { initialPrompt: "Traduis ce mail" },
    });
  });

  it("keeps Shift+Enter for a new line", () => {
    type("Ligne");
    act(() => field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", shiftKey: true, bubbles: true })));
    expect(navigate).not.toHaveBeenCalled();
  });

  it("blocks a question over the agent pod limit, like the chat composer", () => {
    act(() => root.render(<HomeAskBox agent={agent} maxChars={5} />));
    type("  Bonjour  ");
    expect(sendButton().disabled).toBe(true);
    expect(field().getAttribute("aria-invalid")).toBe("true");
    expect(container.textContent).toContain("chatbot.errors.chatInputTooLong");
    act(() => field().dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true })));
    expect(navigate).not.toHaveBeenCalled();

    // The count is on the trimmed question that is sent.
    type("  Salut  ");
    expect(sendButton().disabled).toBe(false);
  });
});
