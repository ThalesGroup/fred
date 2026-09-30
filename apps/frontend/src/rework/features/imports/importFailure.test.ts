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

// The sentences here are the ones the backend actually writes — see
// ingestion_controller.py's quota guard and workflow.py's
// _wf_file_terminal_event_args. If one of them changes, this is where it shows.

import { describe, expect, it } from "vitest";
import type { TFunction } from "i18next";
import { importFailure } from "./importFailure";

const t = ((key: string) => key) as TFunction;

describe("importFailure", () => {
  it("says so when the failure came with no cause", () => {
    expect(importFailure({ error: null, stage: "analysis" }, t)).toEqual({
      summary: "rework.imports.failure.unreported",
      detail: null,
      hopeless: false,
    });
  });

  it("treats the backend's own placeholders as no cause, because that is what they are", () => {
    // Neither of these tells the reader anything; dressing them up as a cause
    // would be pretending we know something we do not.
    for (const error of ["Execution failed", "Ingestion failed. No failure details were reported."]) {
      expect(importFailure({ error, stage: "analysis" }, t).summary).toBe("rework.imports.failure.unreported");
    }
  });

  it("recognises a full storage", () => {
    const result = importFailure(
      {
        error:
          "Storage quota exceeded for team fredlab: limit is 10 GB, current usage is 10737418240 bytes, attempting to upload 4096 bytes.",
        stage: "upload",
      },
      t,
    );
    expect(result.summary).toBe("rework.imports.failure.quotaExceeded");
    // The numbers stay reachable — the summary is not a replacement for them.
    expect(result.detail).toContain("10737418240");
  });

  it("recognises a run that stopped without finishing", () => {
    expect(
      importFailure(
        {
          error:
            "Ingestion failed at the content extraction step. The worker stopped reporting activity before the heartbeat deadline. (HEARTBEAT)",
          stage: "analysis",
        },
        t,
      ).summary,
    ).toBe("rework.imports.failure.interrupted");
  });

  it("recognises a file type the pipeline has no processor for", () => {
    expect(importFailure({ error: "No fast text processor configured for '.dwg'", stage: "upload" }, t).summary).toBe(
      "rework.imports.failure.unsupportedType",
    );
  });

  it("recognises a lost connection during the transfer", () => {
    expect(importFailure({ error: "Failed to fetch", stage: "upload" }, t).summary).toBe(
      "rework.imports.failure.connectionLost",
    );
  });

  it("names the stage and keeps the original sentence for anything it does not know", () => {
    const error = "Ingestion failed. KeyError: 'page_count'";
    expect(importFailure({ error, stage: "analysis" }, t)).toEqual({
      summary: "rework.imports.failure.analysis",
      detail: error,
      hopeless: false,
    });
    expect(importFailure({ error, stage: "upload" }, t).summary).toBe("rework.imports.failure.upload");
  });

  it("does not offer to send a file again when the folder is what refuses it", () => {
    // Two documents already share that name there. Re-sending the same file
    // produces the same refusal, every time.
    const error =
      "This folder holds more than one document named 'report.pdf'. Delete or promote the alternate version before importing again.";

    expect(importFailure({ error, stage: "analysis" }, t)).toEqual({
      summary: "rework.imports.failure.ambiguousName",
      detail: error,
      hopeless: true,
    });
  });

  it("does not blame a team for a personal space being full", () => {
    const error = "Storage quota exceeded for personal space: limit is 1000 bytes, current usage is 999 bytes.";

    expect(importFailure({ error, stage: "upload" }, t).summary).toBe("rework.imports.failure.quotaExceededPersonal");
  });
});
