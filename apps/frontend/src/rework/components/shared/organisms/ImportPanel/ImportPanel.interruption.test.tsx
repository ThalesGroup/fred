// @vitest-environment happy-dom
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

// A tab closed mid-import. What the server got is its own business and carries
// on; what never left exists nowhere but in a browser that is gone. On return
// the panel has to name those files — "some files did not arrive" is not
// something anyone can act on — and let the user finish that import, and only
// that import.

import { act } from "react";
import { createRoot, type Root } from "react-dom/client";
import { Provider } from "react-redux";
import { configureStore } from "@reduxjs/toolkit";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { taskSlice } from "../../../../features/tasks/taskSlice";
import { cancelImport, canCancelImport, clearHeldImports, runImport } from "../../../../features/imports/importRun";
import { forgetCachedRecord, unfinishedImports } from "../../../../features/imports/unfinishedImports";

declare global {
  // eslint-disable-next-line no-var
  var IS_REACT_ACT_ENVIRONMENT: boolean;
}
globalThis.IS_REACT_ACT_ENVIRONMENT = true;

vi.mock("react-i18next", () => ({
  useTranslation: () => ({ t: (key: string) => key, i18n: { language: "en" } }),
}));
vi.mock("@shared/molecules/Toast/ToastProvider", () => ({ useToast: () => ({ showError: vi.fn() }) }));
vi.mock("../../../../features/tasks/useTaskAcknowledgement", () => ({
  useTaskAcknowledgement: () => ({ acknowledge: vi.fn(), isAcknowledging: () => false }),
}));

const streamMock = vi.fn();
vi.mock("../../../../../slices/streamDocumentUpload", () => ({
  leafFileName: (file: File) => file.name.split("/").pop() || file.name,
  streamUploadOrProcessDocument: (...args: unknown[]) => streamMock(...args),
}));

import { ImportPanel } from "./ImportPanel";

let container: HTMLDivElement | undefined;
let root: Root | undefined;
let store: ReturnType<typeof makeStore>;

const makeStore = () => configureStore({ reducer: { tasks: taskSlice.reducer } });

/** Mounting the panel is "coming back to the page". */
function visit() {
  container = document.createElement("div");
  document.body.appendChild(container);
  const mounted = createRoot(container);
  root = mounted;
  act(() => {
    mounted.render(
      <Provider store={store}>
        <ImportPanel teamId="team-1" />
      </Provider>,
    );
  });
  act(() => {
    container!.querySelector("button")!.click();
  });
}

function leave() {
  if (!root) return;
  const mounted = root;
  act(() => {
    mounted.unmount();
  });
  container?.remove();
  root = undefined;
  container = undefined;
}

/** The tab is closed and reopened: the store goes, the record stays. */
function reopenTheTab() {
  leave();
  store = makeStore();
  visit();
}

beforeEach(() => {
  window.localStorage.clear();
  // The record is held in memory between reads; each test starts from a fresh
  // page load, not a cleared key.
  forgetCachedRecord();
  clearHeldImports();
  streamMock.mockReset();
  store = makeStore();
});

afterEach(leave);

const text = () => container?.textContent ?? "";
/** The card's own controls are icon buttons, labelled either way. */
const byLabel = (label: string) =>
  [...container!.querySelectorAll("button")].filter(
    (b) => b.getAttribute("title") === label || b.getAttribute("aria-label") === label,
  );
const sentNames = () => streamMock.mock.calls.flatMap((call) => (call[0] as File[]).map((f) => f.name));

/** An import where one of the two files is received and the other never is —
 *  the tab is closed while it is still queued. */
async function importCutOff() {
  streamMock.mockImplementation(async (files: File[], _mode, _meta, discover) => {
    for (const file of files) {
      if (file.name === "arrived.pdf") discover({ taskId: "task-ok", documentUid: "doc-ok", filename: file.name });
      // "lost.pdf" gets no line at all: the request never completed.
    }
    return [];
  });
  await act(async () => {
    await runImport(
      [
        {
          requestMetadata: { tags: ["tag-1"], profile: "standard" },
          files: [new File(["x"], "arrived.pdf"), new File(["y"], "lost.pdf")],
        },
      ],
      { dispatch: store.dispatch, uploadMode: "process", teamId: "team-1", onError: () => {} },
    );
  });
}

import en from "../../../../../locales/en/translation.json";
import fr from "../../../../../locales/fr/translation.json";

describe("ImportPanel — an import cut off in the middle", () => {
  it("names the files that did not arrive, and only those", async () => {
    await importCutOff();
    reopenTheTab();

    // Drawn as what it is — an import that failed — keeping the cause it was
    // given rather than reducing every one of them to "did not arrive".
    expect(text()).toContain("rework.imports.failure.noAnswer");
    expect(text()).toContain("lost.pdf");
    expect(text()).not.toContain("arrived.pdf");
  });

  it("leaves what the server already received alone", async () => {
    await importCutOff();

    // Struck off the moment the server took it — it is the task's business now.
    expect(unfinishedImports().map((entry) => entry.filename)).toEqual(["lost.pdf"]);
  });

  it("finishes that import for the missing files, ignoring anything else picked", async () => {
    await importCutOff();
    reopenTheTab();
    streamMock.mockClear();
    streamMock.mockImplementation(async () => []);

    act(() => {
      byLabel("rework.imports.resend.action")[0]!.click();
    });
    const input = container!.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", {
      value: [new File(["y"], "lost.pdf"), new File(["z"], "unrelated.pdf")],
    });
    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {});

    // This finishes an import; it does not start a new one.
    expect(sentNames()).toEqual(["lost.pdf"]);
    // And it goes back where it was headed, sent the way it was being sent.
    expect(streamMock.mock.calls[0][1]).toBe("process");
    expect(streamMock.mock.calls[0][2]).toMatchObject({ tags: ["tag-1"], profile: "standard" });
  });

  it("resumes only what was picked, and keeps offering the rest", async () => {
    // Two files lost, one picked back. Clearing the whole block here would
    // mean the other is never offered again.
    streamMock.mockImplementation(async () => []);
    await act(async () => {
      await runImport(
        [
          {
            requestMetadata: { tags: ["tag-1"] },
            files: [new File(["x"], "one.pdf"), new File(["y"], "two.pdf")],
          },
        ],
        { dispatch: store.dispatch, uploadMode: "process", teamId: "team-1", onError: () => {} },
      );
    });
    reopenTheTab();
    streamMock.mockClear();

    // Each card asks for its own file, so what comes back answers for that
    // entry alone.
    const before = unfinishedImports();
    const oneEntry = before.find((e) => e.filename === "one.pdf")!.entryId;
    const twoEntry = before.find((e) => e.filename === "two.pdf")!.entryId;

    act(() => {
      byLabel("rework.imports.resend.action")[0]!.click();
    });
    const input = container!.querySelector('input[type="file"]') as HTMLInputElement;
    Object.defineProperty(input, "files", { value: [new File(["x"], "one.pdf")] });
    await act(async () => {
      input.dispatchEvent(new Event("change", { bubbles: true }));
    });
    await act(async () => {});

    expect(sentNames()).toEqual(["one.pdf"]);
    // The entry the button belonged to is answered for — superseded by the run
    // it started. The other is untouched, still owed, still offered.
    const left = unfinishedImports().map((e) => e.entryId);
    expect(left).not.toContain(oneEntry);
    expect(left).toContain(twoEntry);
    expect(text()).toContain("two.pdf");
  });

  it("gives up on the named files only, never on an import that is running", async () => {
    await importCutOff();
    reopenTheTab();
    // A fresh import starts while last visit's prompt is still on screen.
    streamMock.mockImplementation(() => new Promise(() => {}));
    void runImport([{ requestMetadata: { tags: ["tag-1"] }, files: [new File(["z"], "fresh.pdf")] }], {
      dispatch: store.dispatch,
      uploadMode: "process",
      teamId: "team-1",
      onError: () => {},
    });
    await act(async () => {});

    act(() => {
      byLabel("rework.tasks.card.acknowledge")[0]!.click();
    });

    // Only the dismissed card's file is dropped; the running one is still
    // expected, so closing the tab now would still name it.
    expect(unfinishedImports().map((e) => e.filename)).toEqual(["fresh.pdf"]);
  });

  it("forgets them when the user says so", async () => {
    await importCutOff();
    reopenTheTab();

    act(() => {
      byLabel("rework.tasks.card.acknowledge")[0]!.click();
    });

    expect(text()).not.toContain("lost.pdf");
    expect(unfinishedImports()).toEqual([]);
  });

  it("does not name a file the panel is still following", async () => {
    // Coming back to this page re-reads the record. A file still listed below
    // did not fail to arrive — it is simply still going.
    streamMock.mockImplementation(() => new Promise(() => {}));
    void runImport([{ requestMetadata: { tags: ["tag-1"] }, files: [new File(["x"], "going.pdf")] }], {
      dispatch: store.dispatch,
      uploadMode: "process",
      teamId: "team-1",
      onError: () => {},
    });
    await act(async () => {});

    visit();

    expect(text()).not.toContain("rework.imports.failure.noAnswer");
  });

  it("says nothing at all when the browser cleared its storage", async () => {
    await importCutOff();
    // A browser set to wipe site data on close: the record is gone, and with
    // it every trace of a file that never reached the server. There is nothing
    // to show and nothing to act on — the panel must simply be empty.
    leave();
    window.localStorage.clear();
    forgetCachedRecord();
    store = makeStore();
    visit();

    expect(text()).toContain("rework.imports.panel.empty");
    expect(text()).not.toContain("lost.pdf");
  });

  it("forgets an import nobody came back to", () => {
    // A week on, an unfinished import is archaeology. Offering it back is
    // noise, and a browser that never returns must not accumulate it.
    const stale = Date.now() - 8 * 24 * 60 * 60 * 1000;
    window.localStorage.setItem(
      "fred.imports.unfinished",
      JSON.stringify([
        {
          entryId: "old",
          filename: "forgotten.pdf",
          teamId: "team-1",
          uploadMode: "process",
          requestMetadata: {},
          notedAt: stale,
        },
        {
          entryId: "new",
          filename: "recent.pdf",
          teamId: "team-1",
          uploadMode: "process",
          requestMetadata: {},
          notedAt: Date.now(),
        },
      ]),
    );
    forgetCachedRecord();

    expect(unfinishedImports().map((e) => e.filename)).toEqual(["recent.pdf"]);
  });

  it("dates nothing it cannot date", () => {
    // A record written before we wrote down when an import started. Falling
    // back to 0 dated the card to 1970 and printed "497440h ago".
    window.localStorage.setItem(
      "fred.imports.unfinished",
      JSON.stringify([
        { entryId: "old", filename: "undated.pdf", teamId: "team-1", uploadMode: "process", requestMetadata: {} },
      ]),
    );
    forgetCachedRecord();
    visit();

    expect(text()).toContain("undated.pdf");
    expect(text()).not.toContain("hoursAgo");
    expect(text()).not.toContain("daysAgo");
    expect(text()).not.toContain("justNow");
  });

  it("keeps the status line short and puts the explanation in reach", () => {
    // The line truncates in a narrow panel, so it names what happened and the
    // tooltip carries what it means — the reader is not technical.
    window.localStorage.setItem(
      "fred.imports.unfinished",
      JSON.stringify([
        {
          entryId: "e",
          filename: "cut-off.pdf",
          teamId: "team-1",
          uploadMode: "process",
          requestMetadata: {},
          notedAt: Date.now(),
        },
      ]),
    );
    forgetCachedRecord();
    visit();

    expect(text()).toContain("rework.imports.failure.notSent");
    const short = (locale: typeof fr | typeof en) => (locale.rework.imports.failure as Record<string, string>).notSent;
    const long = (locale: typeof fr | typeof en) =>
      (locale.rework.imports.failure as Record<string, string>).notSentDetail;
    for (const locale of [fr, en]) {
      expect(short(locale).length).toBeLessThan(25);
      expect(long(locale).length).toBeGreaterThan(short(locale).length);
    }
  });

  it("offers no resend for a cause resending cannot change", () => {
    window.localStorage.setItem(
      "fred.imports.unfinished",
      JSON.stringify([
        {
          entryId: "amb",
          filename: "twice.pdf",
          teamId: "team-1",
          uploadMode: "process",
          requestMetadata: {},
          notedAt: Date.now(),
          cause: "This folder holds more than one document named 'twice.pdf'.",
        },
      ]),
    );
    forgetCachedRecord();
    visit();

    expect(text()).toContain("rework.imports.failure.ambiguousName");
    // Sending it again cannot change what the folder holds.
    expect(byLabel("rework.imports.resend.action")).toHaveLength(0);
  });

  // The card turns up after a reload, out of any context that would explain
  // it. Its cause and its one button are the whole explanation, so a missing
  // string leaves the user a raw key where the reason should be.
  it.each(["fr", "en"])("explains itself in %s", (locale) => {
    const imports = (locale === "fr" ? fr : en).rework.imports;
    expect((imports.failure as Record<string, string>).notSent, `${locale}: no cause`).toBeTruthy();
    expect(imports.resend.action, `${locale}: no resend label`).toBeTruthy();
  });
});

describe("ImportPanel — taking a file back before it is sent", () => {
  it("cancels what is still queued and never sends it", async () => {
    // Requests go a few at a time. Hold every one of them open, and the batches
    // past the concurrency limit are still waiting their turn — those are the
    // ones the user can still take back.
    const release: (() => void)[] = [];
    streamMock.mockImplementation(() => new Promise<never[]>((resolve) => release.push(() => resolve([]))));
    const running = runImport(
      ["a.pdf", "b.pdf", "c.pdf", "d.pdf", "queued.pdf"].map((name) => ({
        requestMetadata: { tags: ["tag-1"] },
        files: [new File(["x"], name)],
      })),
      { dispatch: store.dispatch, uploadMode: "process", teamId: "team-1", onError: () => {} },
    );
    await act(async () => {});

    const entry = (label: string) =>
      Object.values(store.getState().tasks.byId).find((vm) => vm.target?.label === label)!;
    // The ones on the wire are the server's now; only the queued one is ours.
    expect(canCancelImport(entry("a.pdf").taskId)).toBe(false);
    expect(canCancelImport(entry("queued.pdf").taskId)).toBe(true);

    const queuedId = entry("queued.pdf").taskId;
    act(() => {
      cancelImport(queuedId, store.dispatch);
    });
    await act(async () => {
      for (const done of release) done();
      await running;
    });

    expect(sentNames()).toEqual(["a.pdf", "b.pdf", "c.pdf", "d.pdf"]);
    expect(store.getState().tasks.byId[queuedId]).toBeUndefined();
    // And it is not left behind as a file that failed to arrive.
    expect(unfinishedImports().map((e) => e.filename)).not.toContain("queued.pdf");
  });
});
