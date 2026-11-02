// @vitest-environment happy-dom

import { afterEach, expect, it, vi } from "vitest";
import { store } from "../../common/store";
import { runtimeQueueApi as api } from "./runtimeQueueApi";

vi.mock("../../security/KeycloakService", () => ({
  KeyCloakService: {
    GetToken: () => "test-token",
    ensureFreshToken: async () => true,
    CallLogout: () => {},
  },
}));

afterEach(() => {
  store.dispatch(api.util.resetApiState());
  vi.unstubAllGlobals();
});

it("reads and updates the pending queue through the application store and prepared runtime", async () => {
  const requests: Request[] = [];
  const messages = [{ id: "message-1", text: "keep me", status: "waiting" }];
  vi.stubGlobal(
    "fetch",
    vi.fn(async (request: Request) => {
      requests.push(request);
      return new Response(JSON.stringify(messages), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      });
    }),
  );
  const target = {
    sessionId: "session-1",
    agentInstanceId: "agent-1",
    teamId: "team-1",
    executeStreamUrl: "/fred/agents/v2/agents/execute/stream",
  };
  const read = store.dispatch(api.endpoints.getPendingMessages.initiate(target));
  try {
    await expect(read.unwrap()).resolves.toEqual(messages);
    expect(api.endpoints.getPendingMessages.select(target)(store.getState()).data).toEqual(messages);
    const url = new URL(requests[0].url);
    expect(url.pathname).toBe("/fred/agents/v2/agents/sessions/session-1/pending");
    expect(url.searchParams.get("agent_instance_id")).toBe("agent-1");
    expect(url.searchParams.get("team_id")).toBe("team-1");

    await expect(
      store
        .dispatch(
          api.endpoints.updatePendingMessage.initiate({
            ...target,
            messageId: "message-1",
            pendingMessageUpdate: {
              request: "enqueue",
              agent_instance_id: "agent-1",
              team_id: "team-1",
              text: "keep me",
            },
          }),
        )
        .unwrap(),
    ).resolves.toEqual(messages);
    expect(new URL(requests[1].url).pathname).toBe("/fred/agents/v2/agents/sessions/session-1/pending/message-1");
    expect(requests[1].method).toBe("PUT");
    expect(await requests[1].json()).toEqual({
      request: "enqueue",
      agent_instance_id: "agent-1",
      team_id: "team-1",
      text: "keep me",
    });
  } finally {
    read.unsubscribe();
  }
});
