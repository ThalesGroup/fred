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

import { describe, expect, it } from "vitest";
import type { DocumentMetadata } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import type { TaskViewModel } from "../../../../features/tasks/taskTypes";
import { deriveDocStatus } from "./deriveDocStatus.ts";

const doc = (stages: Record<string, string>): DocumentMetadata =>
  ({ processing: { stages } }) as unknown as DocumentMetadata;

const task = (state: TaskViewModel["state"], progress: number | null = null): TaskViewModel =>
  ({ state, progress }) as TaskViewModel;

describe("deriveDocStatus", () => {
  it("returns raw when nothing is processed", () => {
    expect(deriveDocStatus(doc({}))).toEqual({ status: "raw", progress: null });
    expect(deriveDocStatus(doc({ raw: "done" }))).toEqual({ status: "raw", progress: null });
  });

  it("returns ready when the vector stage is done", () => {
    expect(deriveDocStatus(doc({ raw: "done", vector: "done" })).status).toBe("ready");
  });

  it("returns processing when a stage is in progress", () => {
    expect(deriveDocStatus(doc({ raw: "done", vector: "in_progress" })).status).toBe("processing");
  });

  it("returns failed when any stage failed", () => {
    expect(deriveDocStatus(doc({ raw: "done", vector: "failed" })).status).toBe("failed");
  });

  it("lets an active task win over the stored stages", () => {
    expect(deriveDocStatus(doc({ vector: "done" }), task("running", 0.4))).toEqual({
      status: "processing",
      progress: 0.4,
    });
    expect(deriveDocStatus(doc({ vector: "done" }), task("failed")).status).toBe("failed");
  });
});
