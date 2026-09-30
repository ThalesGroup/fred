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
import type { TFunction } from "i18next";
import { relativeTime, stepLabel, taskSupportDetails } from "./taskLabels";

const SEC = 1_000;
const MIN = 60 * SEC;
const HOUR = 60 * MIN;

// Stub mirroring the en bundle's `rework.tasks.time.*` so the assertions test the
// branching in relativeTime, not the contents of the translation file.
const t = ((key: string, opts?: { count?: number }) => {
  if (key.endsWith("justNow")) return "just now";
  if (key.endsWith("minAgo")) return `${opts?.count} min ago`;
  if (key.endsWith("hoursAgo")) return `${opts?.count}h ago`;
  if (key.endsWith("daysAgo")) return `${opts?.count}d ago`;
  return key;
}) as unknown as TFunction;

const DAY = 24 * HOUR;

describe("relativeTime", () => {
  it("counts in days past a day, never in three-figure hours", () => {
    // The unfinished-imports record is kept for a week, so a card can legitimately
    // be days old; "168h ago" is not something anyone reads as a week.
    const now = Date.now();
    expect(relativeTime(now - 23 * HOUR, t, now)).toBe("23h ago");
    expect(relativeTime(now - 3 * DAY, t, now)).toBe("3d ago");
    expect(relativeTime(now - 7 * DAY, t, now)).toBe("7d ago");
  });

  it("returns 'just now' for less than 60 seconds ago", () => {
    const now = Date.now();
    expect(relativeTime(now - 30 * SEC, t, now)).toBe("just now");
  });

  it("returns 'just now' at exactly 0 seconds difference", () => {
    const now = Date.now();
    expect(relativeTime(now, t, now)).toBe("just now");
  });

  it("returns 'just now' at 59 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * SEC, t, now)).toBe("just now");
  });

  it("returns '1 min ago' at exactly 60 seconds", () => {
    const now = Date.now();
    expect(relativeTime(now - 60 * SEC, t, now)).toBe("1 min ago");
  });

  it("returns correct minute count for multi-minute gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 5 * MIN, t, now)).toBe("5 min ago");
  });

  it("returns '59 min ago' just before the hour boundary", () => {
    const now = Date.now();
    expect(relativeTime(now - 59 * MIN, t, now)).toBe("59 min ago");
  });

  it("returns '1h ago' at exactly one hour", () => {
    const now = Date.now();
    expect(relativeTime(now - HOUR, t, now)).toBe("1h ago");
  });

  it("returns correct hour count for multi-hour gaps", () => {
    const now = Date.now();
    expect(relativeTime(now - 3 * HOUR, t, now)).toBe("3h ago");
  });
});

describe("ingestion support labels", () => {
  it("names the stage instead of leaking a pipeline identifier into the page", () => {
    // Nothing describes the transfer on the task feed — it is over before the
    // first event arrives.
    expect(stepLabel({ kind: "ingestion", step: null, stage: "upload" }, t)).toBe("rework.tasks.importStage.upload");
    // A step the pipeline reports and we have no wording for must not print
    // its English identifier into a French page.
    expect(stepLabel({ kind: "ingestion", step: "resolving scope", stage: "analysis" }, t)).toBe(
      "rework.tasks.importStage.analysis",
    );
    // A chat attachment carries its own already-translated step and no stage.
    expect(stepLabel({ kind: "ingestion", step: "Préparation…", stage: null }, t)).toBe("Préparation…");
  });

  it("translates known ingestion steps without changing other task kinds", () => {
    expect(stepLabel({ kind: "ingestion", step: "indexing", stage: "analysis" }, t)).toBe(
      "rework.tasks.ingestionStep.indexing",
    );
    expect(stepLabel({ kind: "migration", step: "indexing", stage: null }, t)).toBe("indexing");
  });

  it("copies the document, task reference, stage and failure together", () => {
    const translate = ((key: string, options?: { id: string }) =>
      options?.id ? `Reference: ${options.id}` : key) as TFunction;
    const details = taskSupportDetails(
      {
        taskId: "task-123",
        kind: "ingestion",
        target: { type: "document", id: "doc-456", label: "report.pdf" },
        step: "indexing",
        stage: "analysis",
        conflict: null,
        teamId: null,
        error: "Configured attempts exhausted.",
        owner: null,
        localOnly: false,
        state: "failed",
        progress: null,
        lastSeq: 3,
        registeredAt: 1,
        terminalAt: 2,
        acknowledgedAt: null,
        warnings: null,
      },
      translate,
    );
    expect(details).toContain("report.pdf");
    expect(details).toContain("task-123");
    expect(details).toContain("doc-456");
    expect(details).toContain("indexing");
    expect(details).toContain("Configured attempts exhausted.");
  });
});
