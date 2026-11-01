import { monitorApi as api } from "./monitorApi";
const injectedRtkApi = api.injectEndpoints({
  endpoints: (build) => ({
    monitorStatus: build.query<MonitorStatusApiResponse, MonitorStatusApiArg>({
      query: () => ({ url: `/monitor/v1/status` }),
    }),
  }),
  overrideExisting: false,
});
export { injectedRtkApi as monitorApi };
export type MonitorStatusApiResponse = /** status 200 undefined */ Snapshot;
export type MonitorStatusApiArg = void;
export type ContainerStatus = {
  container: string;
  init: boolean;
  last_exit_at?: string | null;
  last_exit_reason?: string | null;
  phase: string;
  pod: string;
  ready: boolean;
  reason?: string | null;
  /** Kubernetes' cumulative count for this container in this pod, not an hourly rate. */
  restarts: number;
};
export type RecentEvent = {
  count: number;
  message: string;
  object: string;
  observed_at: string;
  reason: string;
  severity: string;
  uid: string;
};
export type ServiceState = "ready" | "degraded" | "updating" | "inactive" | "unknown";
export type ServiceStatus = {
  desired: number;
  kind: string;
  name: string;
  ready: number;
  state: ServiceState;
};
export type Source = "deployments" | "stateful_sets" | "daemon_sets" | "pods" | "events";
export type Snapshot = {
  containers: ContainerStatus[];
  event_window_seconds: number;
  events: RecentEvent[];
  events_limited: boolean;
  namespace: string;
  observed_at: string;
  services: ServiceStatus[];
  /** Sources exceeding the bounded Kubernetes pagination budget. */
  truncated_sources: Source[];
  /** An empty list from an unavailable source is not evidence of a healthy namespace. */
  unavailable_sources: Source[];
};
export const { useMonitorStatusQuery } = injectedRtkApi;
