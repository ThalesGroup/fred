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
import { EVICTION_DELAY_MS, selectActiveTasks, taskEventReceived, taskEvicted } from "./taskSlice";
import { TERMINAL_STATES, type AnyTaskEvent } from "./taskTypes";

const BASE_PATH = "/knowledge-flow/v1";
const BASE_BACKOFF_MS = 1_000;
const MAX_BACKOFF_MS = 30_000;

export function useTaskSseManager(): void {
  const dispatch = useDispatch();
  const activeTasks = useSelector(selectActiveTasks);
  const controllersRef = useRef<Map<string, AbortController>>(new Map());
  const evictionTimersRef = useRef<Map<string, ReturnType<typeof setTimeout>>>(new Map());

  // Keep connections aligned with the active-task list.
  useEffect(() => {
    const activeIds = new Set(activeTasks.map((t) => t.taskId));

    // Close connections for tasks that are no longer in the active list
    for (const [taskId, ac] of controllersRef.current.entries()) {
      if (!activeIds.has(taskId)) {
        ac.abort();
        controllersRef.current.delete(taskId);
      }
    }

    // Open new connections for newly registered tasks
    for (const task of activeTasks) {
      if (controllersRef.current.has(task.taskId)) continue;

      const ac = new AbortController();
      controllersRef.current.set(task.taskId, ac);

      const lastEventId = task.lastSeq >= 0 ? String(task.lastSeq) : undefined;
      openStream(task.taskId, lastEventId, ac.signal, dispatch, evictionTimersRef.current);
    }
  }, [activeTasks, dispatch]);

  // Abort all connections on unmount
  useEffect(() => {
    return () => {
      for (const ac of controllersRef.current.values()) {
        ac.abort();
      }
      controllersRef.current.clear();
      for (const timer of evictionTimersRef.current.values()) {
        clearTimeout(timer);
      }
      evictionTimersRef.current.clear();
    };
  }, []);
}

async function openStream(
  taskId: string,
  initialLastEventId: string | undefined,
  signal: AbortSignal,
  dispatch: ReturnType<typeof useDispatch>,
  evictionTimers: Map<string, ReturnType<typeof setTimeout>>,
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

      const response = await fetch(`${BASE_PATH}/tasks/${taskId}/events`, {
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
              if (block.startsWith(": ")) continue; // SSE heartbeat comment
              const lines = block.split("\n");

              // Track the SSE event ID for Last-Event-ID on reconnect
              const idLine = lines.find((l) => l.startsWith("id: "));
              if (idLine) lastEventId = idLine.slice(4).trim();

              const dataLine = lines.find((l) => l.startsWith("data: "));
              if (!dataLine) continue;
              const raw = dataLine.slice(6).trim();
              if (!raw) continue;

              let event: AnyTaskEvent;
              try {
                event = JSON.parse(raw) as AnyTaskEvent;
              } catch {
                console.warn(`[useTaskSseManager] task ${taskId}: unparseable frame`, raw);
                continue;
              }

              dispatch(taskEventReceived(event));
              backoffMs = BASE_BACKOFF_MS; // successful event — reset backoff

              if (TERMINAL_STATES.has(event.state)) {
                scheduleEviction(event.task_id, event.state, dispatch, evictionTimers);
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

function scheduleEviction(
  taskId: string,
  state: AnyTaskEvent["state"],
  dispatch: ReturnType<typeof useDispatch>,
  evictionTimers: Map<string, ReturnType<typeof setTimeout>>,
): void {
  if (state === "succeeded") {
    const timer = setTimeout(() => {
      dispatch(taskEvicted(taskId));
      evictionTimers.delete(taskId);
    }, EVICTION_DELAY_MS);
    evictionTimers.set(taskId, timer);
  }
  // failed/cancelled: eviction is driven by failuresAcknowledged + timer in TaskTray
}
