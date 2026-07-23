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

// Session-probe registry (#1905 auto-open): a session's active capabilities
// resolve to the headless probes their plugins declare; capabilities without
// probes are skipped.

import { describe, expect, it } from "vitest";
import { buildSessionProbeRegistry, sessionProbesForCapabilities } from "./sessionProbeRegistry";
import type { CapabilityUiPlugin } from "./types";

function StubProbe() {
  return null;
}

describe("sessionProbeRegistry (#1905)", () => {
  const withProbe: CapabilityUiPlugin = { id: "writable_document", sessionProbes: [StubProbe] };
  const withoutProbe: CapabilityUiPlugin = { id: "ppt_filler", sidePanels: {} };

  it("resolves the probes an active capability contributes", () => {
    const registry = buildSessionProbeRegistry([withProbe, withoutProbe]);
    const entries = sessionProbesForCapabilities(["writable_document"], registry);

    expect(entries).toHaveLength(1);
    expect(entries[0]).toMatchObject({ capabilityId: "writable_document", Probe: StubProbe });
  });

  it("skips capabilities that declare no probe", () => {
    const registry = buildSessionProbeRegistry([withProbe, withoutProbe]);
    expect(sessionProbesForCapabilities(["ppt_filler"], registry)).toHaveLength(0);
  });

  it("skips capability ids with no registered plugin (silent, never a crash)", () => {
    const registry = buildSessionProbeRegistry([withProbe]);
    expect(sessionProbesForCapabilities(["not_installed"], registry)).toHaveLength(0);
  });

  it("preserves the order the capabilities are supplied", () => {
    const other: CapabilityUiPlugin = { id: "other", sessionProbes: [StubProbe] };
    const registry = buildSessionProbeRegistry([withProbe, other]);
    const entries = sessionProbesForCapabilities(["other", "writable_document"], registry);

    expect(entries.map((e) => e.capabilityId)).toEqual(["other", "writable_document"]);
  });
});
