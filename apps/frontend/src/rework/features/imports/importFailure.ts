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

// Saying why an import failed, to someone who did not write the pipeline.
//
// The only account of a failure is a sentence the backend wrote in English for
// a log. Matching on it is fragile, and deliberately so: a pattern that stops
// matching falls back to naming the stage and keeping the original sentence as
// the detail, which is what happens today for every cause anyway. Nothing here
// invents a cause it cannot see — a failure reported with no message says
// exactly that.

import type { TFunction } from "i18next";
import type { ImportStage } from "../tasks/taskTypes";

export interface ImportFailure {
  /** One line, in the reader's language, about what to do or expect. */
  summary: string;
  /** The backend's own sentence, when it says more than the summary. Shown
   *  alongside, never instead. */
  detail: string | null;
  /** Re-sending the same file cannot change this outcome — the cause is in the
   *  destination, not the transfer. Offering a retry would only fail again. */
  hopeless: boolean;
}

/** A file the record still lists with no cause of its own was never answered
 *  for — the tab went away mid-import. Written as a sentence so it resolves
 *  through the same path as a cause the backend actually sent. */
export const INTERRUPTED_BEFORE_SEND = "The import was interrupted before this file was sent.";

/** Backend sentences we recognise, most specific first. `detailKey` is for a
 *  cause whose own sentence is no use to the reader — ours, or a backend one
 *  that says less than we can. Without it the detail is the sentence itself. */
const KNOWN_CAUSES: { pattern: RegExp; key: string; hopeless?: boolean; detailKey?: string }[] = [
  { pattern: /interrupted before this file was sent/i, key: "notSent", detailKey: "notSentDetail" },
  // The folder holds two documents of this name. Retrying cannot clear it — the
  // user has to rename or delete one of them there first — so it is named rather
  // than left to the generic "the upload failed".
  { pattern: /more than one document named/i, key: "ambiguousName", hopeless: true },
  // The backend names whose space it refused; only the team wording would be
  // wrong on a personal one, so that case is matched before the general form.
  { pattern: /quota exceeded for personal space/i, key: "quotaExceededPersonal" },
  { pattern: /storage quota exceeded/i, key: "quotaExceeded" },
  { pattern: /quota cannot be verified/i, key: "quotaUnknown" },
  { pattern: /no fast text processor|unsupported|not supported/i, key: "unsupportedType" },
  { pattern: /no word from the server about this file/i, key: "noAnswer" },
  { pattern: /stopped reporting activity|heartbeat|time limit was exceeded/i, key: "interrupted" },
  { pattern: /configured attempts exhausted/i, key: "attemptsExhausted" },
  { pattern: /failed to fetch|networkerror|network ?error|err_/i, key: "connectionLost" },
  { pattern: /upload failed: 5\d\d/i, key: "serverUnavailable" },
  { pattern: /upload failed: 40[13]|forbidden|not authorized|permission/i, key: "notAllowed" },
  { pattern: /content extraction step/i, key: "extraction" },
  { pattern: /indexing step/i, key: "indexing" },
  { pattern: /document preparation step/i, key: "preparation" },
];

/** Sentences that are the backend saying it has nothing to report. Treated as
 *  no cause at all, because that is what they mean. */
const EMPTY_CAUSES = [/^execution failed\.?$/i, /no failure details were reported/i];

export function importFailure(task: { error: string | null; stage: ImportStage | null }, t: TFunction): ImportFailure {
  const raw = task.error?.trim() ?? "";
  if (!raw || EMPTY_CAUSES.some((pattern) => pattern.test(raw))) {
    return { summary: t("rework.imports.failure.unreported"), detail: null, hopeless: false };
  }

  const known = KNOWN_CAUSES.find(({ pattern }) => pattern.test(raw));
  if (known) {
    return {
      summary: t(`rework.imports.failure.${known.key}`),
      detail: known.detailKey ? t(`rework.imports.failure.${known.detailKey}`) : raw,
      hopeless: known.hopeless ?? false,
    };
  }

  // Unrecognised: name which half of the import gave up and hand over the
  // original sentence unchanged. Paraphrasing it would be guessing.
  return {
    summary: t(task.stage === "upload" ? "rework.imports.failure.upload" : "rework.imports.failure.analysis"),
    detail: raw,
    hopeless: false,
  };
}
