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

// Pins down scheduleFiles' contract — see its doc comment in importRun.ts.

import { describe, expect, it, vi } from "vitest";
import type { ScheduledTask } from "../../../slices/streamDocumentUpload";

const streamMock = vi.fn();
vi.mock("../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: (...args: unknown[]) => streamMock(...args),
}));

const noteStarted = vi.fn();
vi.mock("./unfinishedImports", () => ({
  noteImportStarted: (...args: unknown[]) => noteStarted(...args),
  noteImportSettled: vi.fn(),
}));

import { chunkFilesByLeafName, runImport, runWithConcurrencyLimit, scheduleFiles } from "./importRun";

describe("scheduleFiles", () => {
  it("resolves once its single file is discovered, without waiting for the request to settle", async () => {
    streamMock.mockImplementation((_files, _mode, _meta, discover) => {
      discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
      return new Promise(() => {
        /* underlying request never settles within the test */
      });
    });

    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFiles([new File(["x"], "a.pdf")], "process", {}, onDiscovered, onBackgroundError);

    expect(onDiscovered).toHaveBeenCalledWith({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
    expect(onBackgroundError).not.toHaveBeenCalled();
  });

  it("does not resolve until every file in the batch has an outcome", async () => {
    let discoverSecond!: () => void;
    streamMock.mockImplementation((_files, _mode, _meta, discover) => {
      discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
      return new Promise((resolve) => {
        discoverSecond = () => {
          discover({ taskId: "t-2", documentUid: "doc-2", filename: "b.pdf" });
          resolve([]);
        };
      });
    });

    const onDiscovered = vi.fn();
    let resolved = false;
    const done = scheduleFiles(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf")],
      "process",
      {},
      onDiscovered,
      vi.fn(),
    ).then(() => {
      resolved = true;
    });

    await new Promise((r) => setTimeout(r, 0));
    expect(resolved).toBe(false); // a.pdf has a task, b.pdf doesn't yet

    discoverSecond();
    await done;

    expect(resolved).toBe(true);
    expect(onDiscovered).toHaveBeenCalledWith({ taskId: "t-2", documentUid: "doc-2", filename: "b.pdf" });
  });

  it("resolves once every file's onFileResolved fires, with no task ever discovered (upload-only mode)", async () => {
    streamMock.mockImplementation((_files, _mode, _meta, _discover, _onFileFailed, onFileResolved) => {
      onFileResolved("a.pdf");
      onFileResolved("b.pdf");
      return new Promise(() => {
        /* underlying request keeps streaming confirmation lines */
      });
    });

    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFiles(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf")],
      "upload",
      {},
      onDiscovered,
      onBackgroundError,
    );

    expect(onDiscovered).not.toHaveBeenCalled();
    expect(onBackgroundError).not.toHaveBeenCalled();
  });

  it("reports a background error when the request fails before any file has an outcome", async () => {
    streamMock.mockRejectedValue(new Error("network down"));
    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFiles([new File(["x"], "a.pdf")], "process", {}, onDiscovered, onBackgroundError);

    expect(onBackgroundError).toHaveBeenCalledWith("network down");
  });

  it("reports the mid-stream failure only for files still pending when it happened", async () => {
    // a.pdf already got its task before the connection drops; b.pdf and c.pdf
    // never got any outcome — only the generic transport error covers them,
    // and a.pdf must not be reported a second time (its task owns it).
    streamMock.mockImplementation((_files, _mode, _meta, discover) => {
      discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
      return Promise.reject(new Error("connection reset"));
    });

    const onBackgroundError = vi.fn();
    await scheduleFiles(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf"), new File(["x"], "c.pdf")],
      "process",
      {},
      vi.fn(),
      onBackgroundError,
    );

    expect(onBackgroundError).toHaveBeenCalledTimes(1);
    expect(onBackgroundError).toHaveBeenCalledWith("connection reset");
  });

  it("routes a per-file failure (onFileFailed) through onBackgroundError, naming the file, and still waits for the rest", async () => {
    let resolveA!: () => void;
    streamMock.mockImplementation((_files, _mode, _meta, discover, onFileFailed) => {
      onFileFailed("b.json", "unsupported extension");
      return new Promise((resolve) => {
        resolveA = () => {
          discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
          resolve([]);
        };
      });
    });

    const onBackgroundError = vi.fn();
    let resolved = false;
    const done = scheduleFiles(
      [new File(["x"], "a.pdf"), new File(["x"], "b.json")],
      "process",
      {},
      vi.fn(),
      onBackgroundError,
    ).then(() => {
      resolved = true;
    });

    await new Promise((r) => setTimeout(r, 0));
    expect(onBackgroundError).toHaveBeenCalledWith("b.json: unsupported extension");
    expect(resolved).toBe(false); // a.pdf hasn't resolved yet

    resolveA();
    await done;
    expect(resolved).toBe(true);
  });

  it("does not also report the generic rejection once every failure was already reported per file (whole-batch failure)", async () => {
    // Mirrors streamUploadOrProcessDocument's real contract for an all-fail batch:
    // it calls onFileFailed for each named file, then still rejects to signal no
    // task was ever produced — that rejection must not double up the toast.
    streamMock.mockImplementation((_files, _mode, _meta, _discover, onFileFailed) => {
      onFileFailed("a.json", "unsupported extension a");
      onFileFailed("b.json", "unsupported extension b");
      return Promise.reject(new Error("unsupported extension a"));
    });

    const onBackgroundError = vi.fn();
    await scheduleFiles(
      [new File(["x"], "a.json"), new File(["x"], "b.json")],
      "upload",
      {},
      vi.fn(),
      onBackgroundError,
    );

    expect(onBackgroundError).toHaveBeenCalledTimes(2);
    expect(onBackgroundError).toHaveBeenCalledWith("a.json: unsupported extension a");
    expect(onBackgroundError).toHaveBeenCalledWith("b.json: unsupported extension b");
  });

  it("does not report a background error for a failure that happens after every file already had a task", async () => {
    let rejectFull!: (err: Error) => void;
    streamMock.mockImplementation(
      (_files, _mode, _meta, discover) =>
        new Promise<ScheduledTask[]>((_resolve, reject) => {
          discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
          rejectFull = reject;
        }),
    );

    const onDiscovered = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFiles([new File(["x"], "a.pdf")], "process", {}, onDiscovered, onBackgroundError);

    // The task was already discovered (scheduleFiles resolved on it); the request
    // now fails in the background; the task UI owns reporting that.
    rejectFull(new Error("late failure"));
    await new Promise((r) => setTimeout(r, 0));

    expect(onBackgroundError).not.toHaveBeenCalled();
  });

  it("fails the files a cleanly-ended stream never spoke about", async () => {
    // A truncated body or a gateway timing out mid-response ends the read with
    // no error and no line for the rest. Nothing else will ever report on
    // those, so leaving them pending parks them in the panel as "sending" for
    // as long as the tab is open.
    streamMock.mockImplementation((_files, _mode, _meta, discover) => {
      discover({ taskId: "t-1", documentUid: "doc-1", filename: "a.pdf" });
      return Promise.resolve([]);
    });

    const onFailed = vi.fn();
    const onBackgroundError = vi.fn();
    await scheduleFiles(
      [new File(["x"], "a.pdf"), new File(["x"], "b.pdf")],
      "process",
      {},
      vi.fn(),
      onBackgroundError,
      undefined,
      { onFailed, onFinished: vi.fn() },
    );

    expect(onFailed).toHaveBeenCalledTimes(1);
    expect(onFailed.mock.calls[0][0]).toBe("b.pdf");
    // a.pdf got its task and is the task's to report on from here.
    expect(onFailed.mock.calls[0][1]).toContain("no word from the server");
    // Nothing failed at the request level, so nothing is raised globally —
    // the file's own card carries it.
    expect(onBackgroundError).not.toHaveBeenCalled();
  });
});

describe("runImport", () => {
  it("writes the record once for the whole import, not once per batch", async () => {
    // Each write rewrites the record whole, so one per batch made a large
    // import quadratic in its own size — on the main thread, before the first
    // byte left. One call covers every file just as durably.
    noteStarted.mockClear();
    streamMock.mockImplementation((files: File[], _mode, _meta, discover) => {
      for (const file of files) {
        discover({ taskId: `t-${file.name}`, documentUid: `doc-${file.name}`, filename: file.name });
      }
      return Promise.resolve([]);
    });
    const batches = Array.from({ length: 5 }, (_, i) => ({
      files: [new File(["x"], `f${i}-a.pdf`), new File(["x"], `f${i}-b.pdf`)],
      requestMetadata: { tags: ["tag-1"] },
    }));

    await runImport(batches, {
      dispatch: vi.fn(),
      uploadMode: "process",
      teamId: "team-1",
      onError: vi.fn(),
    });

    expect(noteStarted).toHaveBeenCalledTimes(1);
    expect(noteStarted.mock.calls[0][0]).toHaveLength(10);
  });
});

describe("runWithConcurrencyLimit", () => {
  it("never runs more than `limit` workers at once", async () => {
    let active = 0;
    let maxActive = 0;
    const items = [1, 2, 3, 4, 5, 6, 7, 8];

    await runWithConcurrencyLimit(items, 3, async () => {
      active++;
      maxActive = Math.max(maxActive, active);
      await new Promise((r) => setTimeout(r, 0));
      active--;
    });

    expect(maxActive).toBeLessThanOrEqual(3);
  });

  it("runs every item exactly once", async () => {
    const seen: number[] = [];
    await runWithConcurrencyLimit([1, 2, 3, 4, 5], 2, async (item) => {
      seen.push(item);
    });

    expect(seen.sort()).toEqual([1, 2, 3, 4, 5]);
  });
});

describe("chunkFilesByLeafName", () => {
  it("caps each batch at maxSize", () => {
    const files = Array.from({ length: 10 }, (_, i) => new File(["x"], `f${i}.pdf`));
    const batches = chunkFilesByLeafName(files, 4);

    expect(batches.map((b) => b.length)).toEqual([4, 4, 2]);
  });

  it("never puts two files with the same leaf name in the same batch", () => {
    const files = [
      new File(["x"], "report.pdf"),
      new File(["y"], "report.pdf"), // same leaf name, different content
      new File(["x"], "other.pdf"),
    ];
    const batches = chunkFilesByLeafName(files, 8);

    for (const batch of batches) {
      const names = batch.map((f) => f.name);
      expect(new Set(names).size).toBe(names.length);
    }
    expect(batches.flat()).toHaveLength(3);
  });
});
