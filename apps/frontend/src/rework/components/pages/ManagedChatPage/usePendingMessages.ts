import { canonicalizeRuntimeTeamId } from "../../../core/utils/runtimeTeamId";
import { useCallback, useEffect, useRef, useState } from "react";
import type { PendingMessage, PendingMessageUpdate } from "../../../../slices/runtime/runtimeOpenApi";
import {
  useLazyGetPendingMessagesQuery,
  useUpdatePendingMessageMutation,
} from "../../../../slices/runtime/runtimeQueueApi";

type QueueTarget = { teamId: string; agentInstanceId: string; sessionId: string | null };

/** Keep only a view of the durable queue; stale responses cannot cross visits. */
export function usePendingMessages(
  target: QueueTarget,
  prepare: (sessionId: string) => Promise<{ execute_stream_url: string }>,
  enabled: boolean,
  onError: () => void,
) {
  const { teamId, agentInstanceId, sessionId } = target;
  const [pendingMessages, setPendingMessages] = useState<PendingMessage[]>([]);
  const [ready, setReady] = useState(!sessionId);
  const [read] = useLazyGetPendingMessagesQuery();
  const [write] = useUpdatePendingMessageMutation();
  const visit = useRef(0);
  const active = useRef(sessionId);
  active.current = sessionId;
  const prepareRef = useRef(prepare);
  prepareRef.current = prepare;
  const onErrorRef = useRef(onError);
  onErrorRef.current = onError;
  const request = useRef(0);

  const refresh = useCallback(async () => {
    if (!sessionId || !enabled) return;
    const generation = visit.current;
    const serial = ++request.current;
    try {
      const prep = await prepareRef.current(sessionId);
      if (active.current !== sessionId || visit.current !== generation) return;
      const args = {
        sessionId,
        teamId: canonicalizeRuntimeTeamId(teamId),
        agentInstanceId,
        executeStreamUrl: prep.execute_stream_url,
      };
      const messages = await read(args).unwrap();
      if (!Array.isArray(messages)) throw new Error("Invalid pending-message response");
      if (active.current === sessionId && visit.current === generation && request.current === serial) {
        setPendingMessages(messages);
        setReady(true);
      }
      return messages;
    } catch {
      if (active.current === sessionId && visit.current === generation) onErrorRef.current();
    }
  }, [sessionId, teamId, agentInstanceId, enabled, read]);

  const modify = useCallback(
    async (id: string, text: string, action: PendingMessageUpdate["request"]) => {
      if (!sessionId || !enabled) return false;
      const generation = visit.current;
      ++request.current;
      try {
        const prep = await prepareRef.current(sessionId);
        if (active.current !== sessionId || visit.current !== generation) return false;
        const args = {
          sessionId,
          messageId: id,
          executeStreamUrl: prep.execute_stream_url,
          pendingMessageUpdate: {
            request: action,
            agent_instance_id: agentInstanceId,
            team_id: canonicalizeRuntimeTeamId(teamId),
            text,
          },
        };
        await write(args).unwrap();
        if (active.current !== sessionId || visit.current !== generation) return false;
        // Re-read after each mutation instead of trusting responses racing other tabs.
        await refresh();
        return active.current === sessionId && visit.current === generation;
      } catch {
        if (active.current === sessionId && visit.current === generation) onErrorRef.current();
        return false;
      }
    },
    [sessionId, teamId, agentInstanceId, enabled, write, refresh],
  );

  useEffect(() => {
    ++visit.current;
    setPendingMessages([]);
    setReady(!sessionId);
    void refresh();
    return () => {
      ++visit.current;
    };
  }, [sessionId, refresh]);

  return { pendingMessages, setPendingMessages, refresh, modify, ready };
}
