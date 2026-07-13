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

// `scheduleFile` is what lets the upload drawer close as soon as a file is
// scheduled instead of waiting for its whole ingestion pipeline to finish
// (OPS-04 live-feedback fix). These tests pin down the exact contract: resolve
// on first task discovery without waiting for the underlying request, resolve
// cleanly when no task is ever produced (upload-only mode), and only surface a
// toast for a failure that happens before any task existed — a failure after
// that point is the failed task's job to report, via the tray.

import { describe, expect, it, vi } from "vitest";
import type { ScheduledTask } from "../../../../../slices/streamDocumentUpload";

const streamMock = vi.fn();
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  streamUploadOrProcessDocument: (...args: unknown[]) => streamMock(...args),
}));

import { scheduleFile } from "./DocumentUploadDrawer";

function pendingForever(): Promise<ScheduledTask[]> {
  return new Promise(() => {
    /* never settles within the test */
  });
}

describe("scheduleFile", () => {
  it("resolves as soon as the file is discovered, without waiting for the request to settle", async () => {
    streamMock.mockImplementation((_file, _mode, _meta, discover) => {
      discover({ taskId: "t-1", documentUid: "doc-1" });
      return pendingForever();
    });

    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFile(new File(["x"], "a.pdf"), "process", {}, onDiscovered, onBackgroundError);

    expect(onDiscovered).toHaveBeenCalledWith({ taskId: "t-1", documentUid: "doc-1" });
    expect(onBackgroundError).not.toHaveBeenCalled();
  });

  it("resolves once the request settles when no task is ever discovered (upload-only mode)", async () => {
    streamMock.mockResolvedValue([]);
    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFile(new File(["x"], "a.pdf"), "upload", {}, onDiscovered, onBackgroundError);

    expect(onDiscovered).not.toHaveBeenCalled();
    expect(onBackgroundError).not.toHaveBeenCalled();
  });

  it("reports a background error when the request fails before any task was discovered", async () => {
    streamMock.mockRejectedValue(new Error("network down"));
    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFile(new File(["x"], "a.pdf"), "process", {}, onDiscovered, onBackgroundError);

    expect(onBackgroundError).toHaveBeenCalledWith("network down");
  });

  it("does not report a background error for a failure that happens after the task was already discovered", async () => {
    let rejectFull!: (err: Error) => void;
    streamMock.mockImplementation(
      (_file, _mode, _meta, discover) =>
        new Promise<ScheduledTask[]>((_resolve, reject) => {
          discover({ taskId: "t-1", documentUid: "doc-1" });
          rejectFull = reject;
        }),
    );

    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFile(new File(["x"], "a.pdf"), "process", {}, onDiscovered, onBackgroundError);

    // The task was already discovered (scheduleFile resolved on it); the request
    // now fails in the background — the tray/Activity owns reporting that, not us.
    rejectFull(new Error("late failure"));
    await new Promise((r) => setTimeout(r, 0));

    expect(onBackgroundError).not.toHaveBeenCalled();
  });
});
