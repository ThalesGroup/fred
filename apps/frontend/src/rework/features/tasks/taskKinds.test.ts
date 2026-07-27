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

import { describe, it, expect } from "vitest";
import { taskBackendFor } from "./taskKinds";

// ── taskBackendFor ────────────────────────────────────────────────────────────
//
// The single source of truth useTaskSseManager.taskEventsBasePath and
// useTaskAcknowledgement both route off — a mismatch here means either the
// SSE stream or the acknowledgement POST hits the wrong backend and 404s
// (#2123 review: ack always called control-plane regardless of kind).

describe("taskBackendFor", () => {
  it("routes conversation erasure tasks to the control-plane backend", () => {
    expect(taskBackendFor("erasure")).toBe("control-plane");
  });

  it("routes migration tasks to the control-plane backend", () => {
    expect(taskBackendFor("migration")).toBe("control-plane");
  });

  it("routes evaluation tasks to the evaluation backend", () => {
    expect(taskBackendFor("evaluation")).toBe("evaluation");
  });

  it("routes ingestion tasks to the knowledge-flow backend", () => {
    expect(taskBackendFor("ingestion")).toBe("knowledge-flow");
  });

  it("falls back to knowledge-flow for an unknown kind", () => {
    expect(taskBackendFor("reindex")).toBe("knowledge-flow");
  });

  it("falls back to knowledge-flow when kind is null", () => {
    expect(taskBackendFor(null)).toBe("knowledge-flow");
  });
});
