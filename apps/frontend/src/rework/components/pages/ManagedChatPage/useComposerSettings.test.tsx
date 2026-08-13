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

// #2369: the composer's defaults-hydration effect (chat_controls arrives async
// after mount, RFC §3.7) must never overwrite a pick the user made themselves.
// It could, in exactly one window: a brand-new conversation, where `sessionId`
// is still null so nothing is written to sessionStorage, and prepare-execution
// hands back a fresh `chat_controls` ARRAY IDENTITY on every send() — which is
// what re-runs the effect. Reasoning turned on before the first question was
// reverted to the widget default the moment that first question was sent (the
// turn itself ran with reasoning; only the composer forgot).
//
// Driven through a minimal host component — there is no
// @testing-library/react in this repo, same as useManagedChat.test.tsx.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { ChatControlDescriptor } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useComposerSettings } from "./useComposerSettings";

/** A reasoning_toggle descriptor, `params.default` being the agent author's
 *  preselection (#2175). Each call returns a NEW array — the point of the
 *  regression below is that identity, not content, is what wakes the effect. */
function controls(defaultOn: boolean): ChatControlDescriptor[] {
  return [{ capability_id: "platform", widget: "reasoning_toggle", params: { default: defaultOn, effort: "high" } }];
}

type Hook = ReturnType<typeof useComposerSettings>;

function TestHost({
  sessionId,
  chatControls,
  onRender,
}: {
  sessionId: string | null;
  chatControls: readonly ChatControlDescriptor[];
  onRender: (hook: Hook) => void;
}) {
  onRender(useComposerSettings(sessionId, chatControls));
  return null;
}

describe("useComposerSettings — defaults never clobber an explicit pick", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: Hook;

  const render = (sessionId: string | null, chatControls: readonly ChatControlDescriptor[]) => {
    act(() => {
      root.render(<TestHost sessionId={sessionId} chatControls={chatControls} onRender={(h) => (latest = h)} />);
    });
  };

  beforeEach(() => {
    sessionStorage.clear();
    container = document.createElement("div");
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => root.unmount());
    container.remove();
    sessionStorage.clear();
  });

  it("keeps a reasoning pick made before the first message, once that message binds a session", () => {
    // New conversation: no session id yet, so nothing this hook writes reaches
    // sessionStorage.
    render(null, controls(false));
    expect(latest.reasoning).toBe(false);

    act(() => latest.setReasoning(true));
    expect(latest.reasoning).toBe(true);

    // handleSend mints the session id (suppressing the session-change reset)
    // and send() re-runs prepare-execution, whose response replaces
    // `chatControls` with an equal-but-new array.
    render("sid-1", controls(false));

    expect(latest.reasoning).toBe(true);
  });

  it("keeps a search policy / library pick across the same first-send refresh", () => {
    render(null, controls(false));

    act(() => latest.setSearchPolicy("semantic"));
    act(() => latest.setSelectedLibraryIds(["lib-a"]));

    render("sid-1", controls(false));

    expect(latest.searchPolicy).toBe("semantic");
    expect(latest.selectedLibraryIds).toEqual(["lib-a"]);
  });

  it("still applies the author's defaults when chat_controls lands after mount and nothing was picked", () => {
    // The effect's original job: the eager prepare-execution call has not
    // resolved yet at mount, so the composer starts on the `?? false` fallback.
    render(null, []);
    expect(latest.reasoning).toBe(false);

    render(null, controls(true));

    expect(latest.reasoning).toBe(true);
  });

  it("re-enables default hydration after reset() — a genuine session entry", () => {
    render(null, controls(false));
    act(() => latest.setReasoning(true));

    // Entering another session: state is rebuilt from that session's storage
    // (empty here) with no chat_controls resolved for it yet.
    act(() => latest.reset("sid-2", []));
    expect(latest.reasoning).toBe(false);

    // …and that session's own controls, arriving after, are applied normally.
    render("sid-2", controls(true));

    expect(latest.reasoning).toBe(true);
  });

  it("lets a stored session pick outrank the author's default", () => {
    sessionStorage.setItem("chat.composer.sid-3", JSON.stringify({ reasoning: false }));

    render("sid-3", []);
    render("sid-3", controls(true));

    expect(latest.reasoning).toBe(false);
  });
});
