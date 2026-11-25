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

// The home question is copied into the composer, sent once when the chat is
// ready, and never replayed by a reload or a back navigation.

import { act, StrictMode, useEffect, useState } from "react";
import { createRoot, type Root } from "react-dom/client";
import { MemoryRouter, useLocation } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { initialPromptState, useInitialPrompt } from "./useInitialPrompt";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

const seen = { input: "", state: undefined as unknown };
const send = vi.fn();

// Like useManagedChat, the chat clears its composer when it mounts.
function Chat({ ready, typed }: { ready: boolean; typed?: string }) {
  const [input, setInput] = useState("");
  const location = useLocation();
  useEffect(() => setInput(""), []);
  useEffect(() => {
    if (typed) setInput(typed);
  }, [typed]);
  seen.input = input;
  seen.state = location.state;
  useInitialPrompt({ input, setInput, send: () => send(input), ready });
  return null;
}

let container: HTMLDivElement;
let root: Root;

function render(state: unknown, ready: boolean, typed?: string) {
  act(() =>
    root.render(
      <StrictMode>
        <MemoryRouter initialEntries={[{ pathname: "/team/t/managed-chat/a", state }]}>
          <Chat ready={ready} typed={typed} />
        </MemoryRouter>
      </StrictMode>,
    ),
  );
}

beforeEach(() => {
  send.mockReset();
  container = document.createElement("div");
  document.body.appendChild(container);
  root = createRoot(container);
});

afterEach(() => {
  act(() => root.unmount());
  container.remove();
});

describe("useInitialPrompt", () => {
  it("clears the router state at once, then copies and sends once the chat is ready", () => {
    render(initialPromptState("  Résume ce mail  "), false);
    expect(seen.state).toBeNull();
    expect(send).not.toHaveBeenCalled();

    render(undefined, true);
    render(undefined, true);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith("Résume ce mail");
  });

  it("survives the chat clearing its composer on mount (strict-mode double effects)", () => {
    render(initialPromptState("Bonjour"), true);
    expect(send).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith("Bonjour");
  });

  it("lets text typed by the person win over the home question", () => {
    render(initialPromptState("Bonjour"), false);
    render(undefined, false, "Autre chose");
    render(undefined, true, "Autre chose");
    expect(send).not.toHaveBeenCalled();
    expect(seen.input).toBe("Autre chose");
  });

  it("sends nothing on a fresh mount without router state (reload, back)", () => {
    render(undefined, true);
    expect(send).not.toHaveBeenCalled();
    expect(seen.input).toBe("");
  });

  it("ignores missing or blank questions", () => {
    render(initialPromptState("   "), true);
    render({ other: 1 }, true);
    expect(send).not.toHaveBeenCalled();
    expect(seen.input).toBe("");
  });
});
