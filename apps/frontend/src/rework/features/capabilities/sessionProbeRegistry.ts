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

// Session-probe registry keyed by capability id (#1905 auto-open) — the exact
// mirror of `sidePanelRegistry` for the headless per-session probes: the host
// asks which probes a session's ACTIVE capabilities contribute and mounts them
// (they render nothing). A capability with no plugin entry contributes nothing
// (silent skip, never a crash).

import { capabilityUiPlugins } from "./index";
import type { CapabilitySessionProbe, CapabilityUiPlugin } from "./types";

export interface SessionProbeEntry {
  /** Owning capability id (`manifest.id`). */
  capabilityId: string;
  /** The headless component to mount (renders nothing). */
  Probe: CapabilitySessionProbe;
}

export function buildSessionProbeRegistry(
  plugins: readonly CapabilityUiPlugin[] = capabilityUiPlugins,
): ReadonlyMap<string, readonly SessionProbeEntry[]> {
  const registry = new Map<string, SessionProbeEntry[]>();
  for (const plugin of plugins) {
    const probes = plugin.sessionProbes ?? [];
    if (probes.length === 0) continue;
    registry.set(
      plugin.id,
      probes.map((Probe) => ({ capabilityId: plugin.id, Probe })),
    );
  }
  return registry;
}

const sessionProbeRegistry = buildSessionProbeRegistry();

/**
 * Every session probe contributed by the given active capabilities, in the
 * order the capabilities are supplied (then plugin declaration order).
 * Capabilities without probes are skipped. Pure — safe to call on every render.
 */
export function sessionProbesForCapabilities(
  capabilityIds: readonly string[],
  registry: ReadonlyMap<string, readonly SessionProbeEntry[]> = sessionProbeRegistry,
): readonly SessionProbeEntry[] {
  const entries: SessionProbeEntry[] = [];
  for (const id of capabilityIds) {
    for (const entry of registry.get(id) ?? []) {
      entries.push(entry);
    }
  }
  return entries;
}
