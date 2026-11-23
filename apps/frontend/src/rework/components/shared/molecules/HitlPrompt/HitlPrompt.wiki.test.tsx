// @vitest-environment happy-dom
// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { act } from "react";
import { createRoot } from "react-dom/client";
import { describe, expect, it, vi } from "vitest";
import type { ChatMessage } from "../../../../../slices/runtime/runtimeOpenApi";
import { reconstructPendingHitl } from "../../../pages/ManagedChatPage/toThreadMessages";
import { HitlPrompt } from "./HitlPrompt";

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "fr" } }),
}));
vi.mock("react-router-dom", () => ({ useParams: () => ({ teamId: "space" }) }));
const decision = vi.hoisted(() => ({ submit: vi.fn(), withdraw: vi.fn() }));
vi.mock("../../../../../slices/controlPlane/controlPlaneApiEnhancements", () => ({
  useSubmitWikiProposalMutation: () => [(args: unknown) => ({ unwrap: () => decision.submit(args) })],
  useWithdrawWikiProposalMutation: () => [(args: unknown) => ({ unwrap: () => decision.withdraw(args) })],
  useMySpacesQuery: () => ({ currentData: [{ id: "space", kind: "team" }] }),
  useWikiProposalQuery: () => ({
    data: { kind: "page", title: "Proposition", current_content_md: "", content_md: "Texte proposé" },
    isFetching: false,
  }),
}));

const request = {
  session_id: "session",
  exchange_id: "exchange",
  rank: 1,
  timestamp: "2026-11-09T06:00:00Z",
  role: "system",
  channel: "hitl_request",
  metadata: {},
  parts: [
    {
      type: "hitl_request",
      stage: "tool_approval",
      question: "Publier cette proposition ?",
      free_text: false,
      choices: [
        { id: "proceed", label: "Accepter" },
        { id: "cancel", label: "Refuser" },
      ],
      interrupt_id: "interrupt",
      resume_status: "pending",
      pending_calls: [
        {
          tool_call_id: "publish-call",
          tool_name: "wiki_submit_proposal",
          args_preview: '{"proposal_id":"isolated-proposal"}',
        },
      ],
    },
  ],
} satisfies ChatMessage;

describe("Wiki confirmation restored from history", () => {
  it.each(["proceed", "cancel"])("keeps the diff and sends %s with the restored identity", async (choice) => {
    decision.submit.mockReset().mockResolvedValue({ status: "pending" });
    decision.withdraw.mockReset().mockResolvedValue(undefined);
    const restored = reconstructPendingHitl(JSON.parse(JSON.stringify([request])));
    expect(restored?.payload.interrupt_id).toBe("interrupt");
    expect(restored?.payload.occurrence_id).toBeNull();
    const onAnswer = vi.fn();
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    const button = (label: string) =>
      Array.from(container.querySelectorAll("button")).find((element) => element.textContent?.includes(label))!;
    try {
      act(() => root.render(<HitlPrompt event={restored!} onAnswer={onAnswer} />));
      expect(button("Accepter").disabled).toBe(false);
      expect(button("Refuser").disabled).toBe(false);
      // Each submission is judged on its own card: never approved for the whole conversation.
      expect(button("chatbot.approveForConversation")).toBeUndefined();
      act(() => button("rework.wiki.proposal.seeChanges").click());
      expect(document.body.textContent).toContain("+ Texte proposé");
      await act(async () => button(choice === "proceed" ? "Accepter" : "Refuser").click());
      // The person's own call settles the draft before the run resumes.
      const call = choice === "proceed" ? decision.submit : decision.withdraw;
      expect(call).toHaveBeenCalledWith({ spaceId: "space", proposalId: "isolated-proposal" });
      expect(call.mock.invocationCallOrder[0]).toBeLessThan(onAnswer.mock.invocationCallOrder[0]);
      expect(onAnswer.mock.calls[0][0]).toBe(choice);
      act(() => root.render(<HitlPrompt event={restored!} onAnswer={onAnswer} readonly />));
      expect(button("Accepter")).toBeUndefined();
      expect(button("Refuser")).toBeUndefined();
      expect(button("rework.wiki.proposal.seeChanges")).toBeDefined();
      const response = {
        ...request,
        rank: 2,
        role: "user",
        channel: "hitl_response",
        parts: [{ type: "hitl_response", choice_id: choice }],
      } as ChatMessage;
      expect(reconstructPendingHitl([request, response])).toBeNull();
    } finally {
      act(() => root.unmount());
      container.remove();
    }
  });

  it("keeps the card and explains an outdated proposal instead of resuming", async () => {
    decision.submit.mockReset().mockRejectedValue({ status: 409, data: { detail: "stale" } });
    const restored = reconstructPendingHitl(JSON.parse(JSON.stringify([request])));
    const onAnswer = vi.fn();
    const container = document.createElement("div");
    document.body.append(container);
    const root = createRoot(container);
    try {
      act(() => root.render(<HitlPrompt event={restored!} onAnswer={onAnswer} />));
      const accept = Array.from(container.querySelectorAll("button")).find((b) => b.textContent?.includes("Accepter"))!;
      await act(async () => accept.click());
      expect(onAnswer).not.toHaveBeenCalled();
      expect(container.querySelector('[role="alert"]')?.textContent).toBe("rework.wiki.proposal.outdated");
      expect(accept.disabled).toBe(false);
    } finally {
      act(() => root.unmount());
      container.remove();
    }
  });
});
