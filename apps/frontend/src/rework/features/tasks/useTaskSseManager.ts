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

import { useEffect, useRef } from "react";
import { useDispatch, useSelector } from "react-redux";
import { KeyCloakService } from "../../../security/KeycloakService";
import { selectActiveTasks, taskEventReceived } from "./taskSlice";
import { TERMINAL_STATES, type AnyTaskEvent } from "./taskTypes";

// Task events are served by the backend that runs the task: ingestion/reindex
// tasks live in knowledge-flow, migration and conversation erasure in the
// control-plane, evaluation campaigns in the evaluation backend.
const DEFAULT_BASE_PATH = "/knowledge-flow/v1";
const BASE_PATH_BY_KIND: Record<string, string> = {
  migration: "/control-plane/v1",
  erasure: "/control-plane/v1",
  evaluation: "/evaluation/v1",
};

export function taskEventsBasePath(kind: string | null): string {
  return (kind && BASE_PATH_BY_KIND[kind]) || DEFAULT_BASE_PATH;
}

/**
 * Parse one SSE block (the text between blank-line separators) into its event id
 * and decoded task event. `id` is returned whenever an `id:` line is present — so
 * the caller can advance Last-Event-ID even for non-data frames — while `event`
 * is returned only when a `data:` line holds valid JSON. Heartbeat comments and
 * id-only / blank / unparseable frames yield no `event`.
 */
export function parseSseBlock(block: string): { id?: string; event?: AnyTaskEvent } {
  if (block.startsWith(": ")) return {}; // SSE heartbeat comment
  const lines = block.split("\n");

  const idLine = lines.find((l) => l.startsWith("id: "));
  const id = idLine?.slice(4).trim();

  const dataLine = lines.find((l) => l.startsWith("data: "));
  const raw = dataLine?.slice(6).trim();
  if (!raw) return { id };

  try {
    return { id, event: JSON.parse(raw) as AnyTaskEvent };
  } catch {
    return { id };
  }
}

const BASE_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

export function useTaskSseManager(): void {
  const dispatch = useDispatch();
  const activeTasks = useSelector(selectActiveTasks);
  const controllersRef = useRef<Map<string, AbortController>>(new Map());

  // Keep connections aligned with the active-task list.
  useEffect(() => {
    const remoteActiveTasks = activeTasks.filter((task) => !task.localOnly);
    const activeIds = new Set(remoteActiveTasks.map((t) => t.taskId));

    // Close connections for tasks that are no longer in the active list
    for (const [taskId, ac] of controllersRef.current.entries()) {
      if (!activeIds.has(taskId)) {
        ac.abort();
        controllersRef.current.delete(taskId);
      }
    }

    // Open new connections for newly registered tasks
    for (const task of remoteActiveTasks) {
      if (controllersRef.current.has(task.taskId)) continue;

      const ac = new AbortController();
      controllersRef.current.set(task.taskId, ac);

      const lastEventId = task.lastSeq >= 0 ? String(task.lastSeq) : undefined;
      const basePath = taskEventsBasePath(task.kind);
      openStream(task.taskId, basePath, lastEventId, ac.signal, dispatch);
    }
  }, [activeTasks, dispatch]);

  // Abort all connections on unmount
  useEffect(() => {
    return () => {
      for (const ac of controllersRef.current.values()) {
        ac.abort();
      }
      controllersRef.current.clear();
    };
  }, []);
}

async function openStream(
  taskId: string,
  basePath: string,
  initialLastEventId: string | undefined,
  signal: AbortSignal,
  dispatch: ReturnType<typeof useDispatch>,
): Promise<void> {
  let lastEventId: string | undefined = initialLastEventId;
  let backoffMs = BASE_BACKOFF_MS;

  while (!signal.aborted) {
    let retriable = true;

    try {
      await KeyCloakService.ensureFreshToken(30);
      const token = KeyCloakService.GetToken() ?? "";

      const headers: Record<string, string> = {
        Authorization: `Bearer ${token}`,
        Accept: "text/event-stream",
      };
      if (lastEventId !== undefined) {
        headers["Last-Event-ID"] = lastEventId;
      }

      const response = await fetch(`${basePath}/tasks/${taskId}/events`, {
        headers,
        signal,
      });

      if (!response.ok || !response.body) {
        // 4xx errors will not self-heal — do not reconnect
        if (response.status >= 400 && response.status < 500) {
          console.error(`[useTaskSseManager] task ${taskId}: HTTP ${response.status} (non-retriable)`);
          retriable = false;
        } else {
          console.warn(`[useTaskSseManager] task ${taskId}: HTTP ${response.status}, will retry`);
        }
      } else {
        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";

        try {
          while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += decoder.decode(value, { stream: true });
            const blocks = buf.split("\n\n");
            buf = blocks.pop() ?? "";

            for (const block of blocks) {
              const { id, event } = parseSseBlock(block);
              // Track the SSE event ID for Last-Event-ID on reconnect.
              if (id !== undefined) lastEventId = id;
              if (!event) continue;

              dispatch(taskEventReceived(event));
              backoffMs = BASE_BACKOFF_MS; // successful event — reset backoff

              if (TERMINAL_STATES.has(event.state)) {
                // Terminal: stop streaming. Succeeded tasks are kept in the store
                // for the session (admin history); the floating tray hides old ones
                // via `selectVisibleTasks`, and the user clears them explicitly.
                return; // clean terminal close — do not reconnect
              }
            }
          }
          // EOF without terminal state: server restarted or connection dropped — reconnect
        } finally {
          reader.releaseLock();
        }
      }
    } catch (err) {
      if ((err as Error)?.name === "AbortError") return;
      console.warn(`[useTaskSseManager] task ${taskId}: stream error, will retry`, err);
    }

    if (!retriable || signal.aborted) return;

    await abortableDelay(backoffMs, signal);
    backoffMs = Math.min(backoffMs * 2, MAX_BACKOFF_MS);
  }
}

function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve) => {
    if (signal.aborted) {
      resolve();
      return;
    }
    const timer = setTimeout(resolve, ms);
    signal.addEventListener(
      "abort",
      () => {
        clearTimeout(timer);
        resolve();
      },
      { once: true },
    );
  });
}
