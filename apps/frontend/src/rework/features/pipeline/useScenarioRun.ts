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
import type { Reporter, Scenario, StepReport } from "./types";

export interface PipelineRun {
  steps: StepReport[];
  isRunning: boolean;
  /** Resolves when the run ends, so Run all can chain families. */
  start: () => Promise<void>;
}

export interface Runner {
  steps: StepReport[];
  isRunning: boolean;
  run: (body: (report: Reporter, signal: AbortSignal) => Promise<void>) => Promise<void>;
}

/** One run at a time: a new run aborts the previous one and clears its report. */
export function useRunner(): Runner {
  const [steps, setSteps] = useState<StepReport[]>([]);
  const [isRunning, setIsRunning] = useState(false);
  const controllerRef = useRef<AbortController | null>(null);

  const report = useCallback((step: StepReport) => {
    setSteps((prev) => {
      const i = prev.findIndex((s) => s.id === step.id);
      if (i === -1) return [...prev, step];
      const next = [...prev];
      next[i] = step;
      return next;
    });
  }, []);

  const run = useCallback(
    async (body: (report: Reporter, signal: AbortSignal) => Promise<void>) => {
      controllerRef.current?.abort();
      const controller = new AbortController();
      controllerRef.current = controller;
      setSteps([]);
      setIsRunning(true);
      try {
        await body(report, controller.signal);
      } finally {
        if (!controller.signal.aborted) setIsRunning(false);
      }
    },
    [report],
  );

  useEffect(() => () => controllerRef.current?.abort(), []);

  return { steps, isRunning, run };
}

export function useScenarioRun<D>(scenario: Scenario<D>, deps: D): PipelineRun {
  const { steps, isRunning, run } = useRunner();
  const start = useCallback(() => run((report, signal) => scenario(deps, report, signal)), [run, scenario, deps]);
  return { steps, isRunning, start };
}
