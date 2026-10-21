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

import { useMemo } from "react";
import { controlPlaneApi } from "../../../../slices/controlPlane/controlPlaneOpenApi";
import { knowledgeFlowApi } from "../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { ObservabilityDeps } from "../scenarios/observabilityScenario";
import { statusOf } from "../scenarios/runScope";
import { FRESH, useApiDispatch } from "./api";

// A backend the deployment does not run answers one of these; anything else is a real failure.
const ABSENT = new Set([404, 501, 503]);

async function orAbsent<T>(read: () => Promise<T>): Promise<T | null> {
  try {
    return await read();
  } catch (error) {
    if (ABSENT.has(statusOf(error) ?? 0)) return null;
    throw error;
  }
}

interface PrometheusTargets {
  data?: { activeTargets?: Array<{ health?: string; labels?: { job?: string } }> };
}

export function useObservabilityDeps(): ObservabilityDeps {
  const dispatch = useApiDispatch();
  return useMemo(() => {
    const cp = controlPlaneApi.endpoints;
    const kf = knowledgeFlowApi.endpoints;
    const lastDay = () => ({ since: new Date(Date.now() - 86_400_000).toISOString(), until: new Date().toISOString() });
    return {
      kpis: [
        {
          id: "kpi-sessions",
          title: "The conversations KPI can be read",
          read: async () =>
            (await dispatch(cp.handlerControlPlaneV1KpiPresetsSessionsOverTimeGet.initiate(lastDay(), FRESH)).unwrap())
              .rows.length,
        },
        {
          id: "kpi-messages",
          title: "The messages KPI can be read",
          read: async () =>
            (await dispatch(cp.handlerControlPlaneV1KpiPresetsMessagesOverTimeGet.initiate(lastDay(), FRESH)).unwrap())
              .rows.length,
        },
        {
          id: "kpi-tokens",
          title: "The token usage KPI can be read",
          read: async () =>
            (
              await dispatch(
                cp.handlerControlPlaneV1KpiPresetsTokenUsageOverTimeGet.initiate(lastDay(), FRESH),
              ).unwrap()
            ).rows.length,
        },
      ],
      searchHealth: () =>
        orAbsent(async () => {
          const health = (await dispatch(kf.osHealth.initiate({}, FRESH)).unwrap()) as { status?: string } | null;
          return String(health?.status ?? "unknown");
        }),
      metricsTargets: () =>
        orAbsent(async () => {
          const response = (await dispatch(kf.prometheusTargets.initiate({}, FRESH)).unwrap()) as PrometheusTargets;
          return (response.data?.activeTargets ?? []).map((t) => ({
            job: t.labels?.job ?? "unknown",
            up: t.health === "up",
          }));
        }),
    };
  }, [dispatch]);
}
