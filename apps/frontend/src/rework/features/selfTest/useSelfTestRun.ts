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

import { useCallback, useEffect, useRef, useState } from "react";
import { KeyCloakService } from "../../../security/KeycloakService";

// Mirrors the control-plane self_test contract (VALID-02). Kept local: the
// harness is admin-only and config-gated, not part of the generated OpenAPI.
const BASE_PATH = "/control-plane/v1";

export type SelfTestStepStatus = "pending" | "running" | "passed" | "failed" | "skipped";
export type SelfTestRunState = "running" | "passed" | "failed";

export interface SelfTestStep {
  id: string;
  title: string;
  status: SelfTestStepStatus;
  detail: string | null;
  error: string | null;
  duration_ms: number | null;
}

export interface SelfTestRun {
  run_id: string;
  state: SelfTestRunState;
  progress: number | null;
  step: string | null;
  steps: SelfTestStep[];
}

interface SelfTestEvent {
  run_id: string;
  state: SelfTestRunState;
  seq: number;
  progress: number | null;
  step: string | null;
  steps: SelfTestStep[];
}

export interface UseSelfTestRun {
  run: SelfTestRun | null;
  isRunning: boolean;
  error: string | null;
  start: () => void;
}

async function authHeaders(extra: Record<string, string> = {}): Promise<Record<string, string>> {
  await KeyCloakService.ensureFreshToken(30);
  const token = KeyCloakService.GetToken() ?? "";
  return { Authorization: `Bearer ${token}`, ...extra };
}

function parseDataBlock(block: string): SelfTestEvent | null {
  const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
  const raw = dataLine?.slice(6).trim();
  if (!raw) return null;
  try {
    return JSON.parse(raw) as SelfTestEvent;
  } catch {
    return null;
  }
}

/**
 * Drives one admin self-test campaign: POSTs to start it, then streams per-step
 * transitions over SSE. Single in-flight run; a new start() supersedes the old.
 */
export function useSelfTestRun(): UseSelfTestRun {
  const [run, setRun] = useState<SelfTestRun | null>(null);
  const [isRunning, setIsRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const controllerRef = useRef<AbortController | null>(null);

  const stream = useCallback(async (runId: string, signal: AbortSignal): Promise<void> => {
    const response = await fetch(`${BASE_PATH}/self-test/runs/${runId}/events`, {
      headers: await authHeaders({ Accept: "text/event-stream" }),
      signal,
    });
    if (!response.ok || !response.body) {
      throw new Error(`stream HTTP ${response.status}`);
    }

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
          const event = parseDataBlock(block);
          if (!event) continue;
          setRun({
            run_id: event.run_id,
            state: event.state,
            progress: event.progress,
            step: event.step,
            steps: event.steps,
          });
          if (event.state !== "running") return; // terminal — stop streaming
        }
      }
    } finally {
      reader.releaseLock();
    }
  }, []);

  const start = useCallback(() => {
    controllerRef.current?.abort();
    const controller = new AbortController();
    controllerRef.current = controller;

    setError(null);
    setRun(null);
    setIsRunning(true);

    void (async () => {
      try {
        const response = await fetch(`${BASE_PATH}/self-test/runs`, {
          method: "POST",
          headers: await authHeaders(),
          signal: controller.signal,
        });
        if (!response.ok) {
          throw new Error(
            response.status === 404
              ? "Self-test harness is disabled (set self_test.enabled in the control-plane config)."
              : `Failed to start run: HTTP ${response.status}`,
          );
        }
        const { run_id: runId } = (await response.json()) as { run_id: string };
        await stream(runId, controller.signal);
      } catch (err) {
        if ((err as Error)?.name !== "AbortError") {
          setError((err as Error)?.message ?? "Self-test run failed");
        }
      } finally {
        if (!controller.signal.aborted) setIsRunning(false);
      }
    })();
  }, [stream]);

  useEffect(() => {
    return () => controllerRef.current?.abort();
  }, []);

  return { run, isRunning, error, start };
}
