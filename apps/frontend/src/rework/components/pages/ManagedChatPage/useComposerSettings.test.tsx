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
import type { ChatControlDescriptor, EffectiveChatModel } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { useComposerSettings } from "./useComposerSettings";

/** A reasoning_toggle descriptor. Each call returns a NEW array — the point of
 *  the regression below is that identity, not content, is what wakes the effect. */
function controls(): ChatControlDescriptor[] {
  return [{ capability_id: "platform", widget: "reasoning_toggle", params: {} }];
}

const SMALL = "model__mistral__mistral-small";
const LARGE = "model__mistral__mistral-large";

/** The agent's resolved model (Mistral Small) and the team's reasoning default for each row. */
function model(smallOn: boolean, largeOn = false, rows = ["small", "large"]): EffectiveChatModel {
  const all = {
    small: {
      profile_id: "chat.small",
      capability_id: SMALL,
      name: "mistral-small",
      reasoning_enabled: true,
      reasoning_default_on: smallOn,
    },
    large: {
      profile_id: "chat.large",
      capability_id: LARGE,
      name: "mistral-large",
      reasoning_enabled: true,
      reasoning_default_on: largeOn,
    },
  } as const;
  return {
    capability_id: SMALL,
    reasoning_enabled: true,
    selectable_models: rows.map((key) => all[key as keyof typeof all]),
  } as EffectiveChatModel;
}

type Hook = ReturnType<typeof useComposerSettings>;

function TestHost({
  sessionId,
  chatControls,
  effectiveModel,
  onChoiceDropped,
  onRender,
}: {
  sessionId: string | null;
  chatControls: readonly ChatControlDescriptor[];
  effectiveModel?: EffectiveChatModel;
  onChoiceDropped?: (label: string) => void;
  onRender: (hook: Hook) => void;
}) {
  onRender(useComposerSettings(sessionId, chatControls, effectiveModel, onChoiceDropped));
  return null;
}

describe("useComposerSettings — defaults never clobber an explicit pick", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: Hook;

  const dropped: string[] = [];
  const render = (
    sessionId: string | null,
    chatControls: readonly ChatControlDescriptor[],
    effectiveModel?: EffectiveChatModel,
  ) => {
    act(() => {
      root.render(
        <TestHost
          sessionId={sessionId}
          chatControls={chatControls}
          effectiveModel={effectiveModel}
          onChoiceDropped={(label) => dropped.push(label)}
          onRender={(h) => (latest = h)}
        />,
      );
    });
  };

  /** A reload (or leaving the conversation and coming back): nothing survives
   *  but sessionStorage. */
  const remount = (
    sessionId: string | null,
    chatControls: readonly ChatControlDescriptor[],
    effectiveModel?: EffectiveChatModel,
  ) => {
    act(() => root.unmount());
    root = createRoot(container);
    render(sessionId, chatControls, effectiveModel);
  };

  beforeEach(() => {
    dropped.length = 0;
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
    render(null, controls());
    expect(latest.reasoning).toBe(false);

    act(() => latest.setReasoning(true));
    expect(latest.reasoning).toBe(true);

    // handleSend mints the session id (suppressing the session-change reset)
    // and send() re-runs prepare-execution, whose response replaces
    // `chatControls` with an equal-but-new array.
    render("sid-1", controls());

    expect(latest.reasoning).toBe(true);
  });

  it("keeps a search policy / library pick across the same first-send refresh", () => {
    render(null, controls());

    act(() => latest.setSearchPolicy("semantic"));
    act(() => latest.setSelectedLibraryIds(["lib-a"]));

    render("sid-1", controls());

    expect(latest.searchPolicy).toBe("semantic");
    expect(latest.selectedLibraryIds).toEqual(["lib-a"]);
  });

  it("makes that pick durable: bindSession() persists it under the freshly minted session id", () => {
    render(null, controls());
    act(() => latest.setReasoning(true));

    // What useManagedChat does the moment it mints a session id for a
    // conversation that had none.
    act(() => latest.bindSession("sid-1"));
    remount("sid-1", controls());

    expect(latest.reasoning).toBe(true);
  });

  it("does not seed storage on bind when the user picked nothing — defaults keep applying", () => {
    render(null, []);

    act(() => latest.bindSession("sid-1"));

    expect(sessionStorage.getItem("chat.composer.sid-1")).toBeNull();
    render("sid-1", controls(), model(true));
    expect(latest.reasoning).toBe(true);
  });

  it("seeds reasoning from the team default once the models arrive and nothing was picked", () => {
    render(null, controls());
    expect(latest.reasoning).toBe(false);

    render(null, controls(), model(true));

    expect(latest.reasoning).toBe(true);
  });

  it("re-enables default hydration after reset() — a genuine session entry", () => {
    render(null, controls(), model(false));
    act(() => latest.setReasoning(true));

    // Entering another session: state is rebuilt from that session's storage
    // (empty here) and the models known so far.
    act(() => latest.reset("sid-2", []));
    expect(latest.reasoning).toBe(false);

    // …and that session's own refreshed models are applied normally.
    render("sid-2", controls(), model(true));

    expect(latest.reasoning).toBe(true);
  });

  it("stores the agent-question toggle separately for each conversation", () => {
    const questionControls: ChatControlDescriptor[] = [
      { capability_id: "platform", widget: "ask_user_toggle", params: { default: true } },
    ];
    render("sid-a", questionControls);
    expect(latest.askUser).toBe(true);
    act(() => latest.setAskUser(false));
    expect(latest.askUser).toBe(false);
    act(() => latest.reset("sid-b", questionControls));
    render("sid-b", questionControls);
    expect(latest.askUser).toBe(true);
    remount("sid-a", questionControls);
    expect(latest.askUser).toBe(false);
  });

  it("lets a stored session pick outrank the team default", () => {
    sessionStorage.setItem("chat.composer.sid-3", JSON.stringify({ reasoning: false }));

    render("sid-3", []);
    render("sid-3", controls(), model(true));

    expect(latest.reasoning).toBe(false);
  });

  it("falls back to the control default when a remembered scope is no longer offered", () => {
    const narrowed: ChatControlDescriptor[] = [
      {
        capability_id: "document_access",
        widget: "rag_scope",
        params: { default: "hybrid", options: ["hybrid", "general_only"] },
      },
    ];
    sessionStorage.setItem("chat.composer.sid-4", JSON.stringify({ ragScope: "corpus_only" }));

    render("sid-4", narrowed);
    expect(latest.ragScope).toBe("hybrid");

    act(() => latest.setRagScope("general_only"));
    expect(latest.ragScope).toBe("general_only");
  });
});

describe("useComposerSettings — model choice", () => {
  let container: HTMLDivElement;
  let root: Root;
  let latest: Hook;
  const dropped: string[] = [];

  const render = (sessionId: string | null, effectiveModel?: EffectiveChatModel) => {
    act(() => {
      root.render(
        <TestHost
          sessionId={sessionId}
          chatControls={controls()}
          effectiveModel={effectiveModel}
          onChoiceDropped={(label) => dropped.push(label)}
          onRender={(h) => (latest = h)}
        />,
      );
    });
  };

  beforeEach(() => {
    dropped.length = 0;
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

  it("starts a new conversation on the recommended model with its team reasoning default", () => {
    render(null, model(true));
    expect(latest.chatProfileId).toBeNull();
    expect(latest.reasoning).toBe(true);
  });

  it("reseeds reasoning from the team default of each model switched to", () => {
    render("sid-1", model(true, false));
    act(() => latest.setChatProfileId("chat.large"));
    expect(latest.chatProfileId).toBe("chat.large");
    expect(latest.reasoning).toBe(false);

    act(() => latest.setChatProfileId("chat.small"));
    // Picking the recommended model clears the choice.
    expect(latest.chatProfileId).toBeNull();
    expect(latest.reasoning).toBe(true);
  });

  it("keeps the choice for the conversation across a reload", () => {
    render("sid-1", model(false));
    act(() => latest.setChatProfileId("chat.large"));

    act(() => root.unmount());
    root = createRoot(container);
    render("sid-1", model(false));

    expect(latest.chatProfileId).toBe("chat.large");
  });

  it("clears a choice no longer offered, names the lost model and falls back to the recommended one", () => {
    render("sid-1", model(true, false));
    act(() => latest.setChatProfileId("chat.large"));

    render("sid-1", model(true, false, ["small"]));

    expect(latest.chatProfileId).toBeNull();
    expect(latest.reasoning).toBe(true);
    expect(dropped).toEqual(["Mistral Large"]);
    expect(JSON.parse(sessionStorage.getItem("chat.composer.sid-1") ?? "{}").chatProfileId).toBeNull();
  });

  it("checks the stored choice of a conversation it switches to, with the same list", () => {
    // sid-2 picked Large back when it was offered; the team has since disabled it.
    sessionStorage.setItem(
      "chat.composer.sid-2",
      JSON.stringify({ chatProfileId: "chat.large", chatModelLabel: "Mistral Large", reasoning: false }),
    );
    const onlySmall = model(true, false, ["small"]);
    render("sid-1", onlySmall);

    act(() => latest.reset("sid-2", controls()));

    expect(latest.chatProfileId).toBeNull();
    expect(latest.reasoning).toBe(true);
    expect(dropped).toEqual(["Mistral Large"]);
    expect(JSON.parse(sessionStorage.getItem("chat.composer.sid-2") ?? "{}").chatProfileId).toBeNull();
  });

  it("keeps the choice while the list is empty (locked or unreachable pod)", () => {
    render("sid-1", model(false));
    act(() => latest.setChatProfileId("chat.large"));

    render("sid-1", { capability_id: SMALL, selectable_models: [], choice_locked: true } as EffectiveChatModel);

    expect(latest.chatProfileId).toBe("chat.large");
    expect(dropped).toEqual([]);
  });
});
