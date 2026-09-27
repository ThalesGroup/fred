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

import assert from "node:assert/strict";
import { appendFile, readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import { validateArtifactRef } from "./release-dispatch.mjs";

export function releaseSummary({
  operation,
  selected,
  candidateRef,
  attemptRef,
  result,
}) {
  assert(
    ["prepare-only", "publish", "verify"].includes(operation),
    "invalid release summary operation",
  );
  const candidate = validateArtifactRef(candidateRef, "summary candidate");
  const lines = [
    `### Frontend packages: ${operation}`,
    "",
    `Selected: ${selected.join(", ")}`,
    `Candidate: run ${candidate.runId} attempt ${candidate.runAttempt}, artifact ${candidate.artifactId}, ZIP SHA-256 ${candidate.zipSha256}, record ${candidate.recordDigest}`,
  ];
  if (attemptRef) {
    const attempt = validateArtifactRef(attemptRef, "summary attempt");
    lines.push(
      `Publishing attempt: run ${attempt.runId} attempt ${attempt.runAttempt}, artifact ${attempt.artifactId}, ZIP SHA-256 ${attempt.zipSha256}`,
    );
  }
  if (operation === "publish")
    lines.push(
      `Registry outcomes: ${Object.entries(result.states)
        .map(([id, state]) => `${id}=${state}`)
        .join(", ")}`,
    );
  if (operation === "verify")
    lines.push(
      `Public gates: ${Object.entries(result.gates)
        .map(([gate, passed]) => `${gate}=${passed}`)
        .join(", ")}`,
      `Verifier: ${result.verifierExecution.sourceCommit} / ${result.verifierExecution.runId} / ${result.verifierExecution.runAttempt}`,
    );
  lines.push(
    "Candidate/attempt retention is requested for 30 days; confirm each artifact's actual API expiry before continuation.",
    "",
  );
  return `${lines.join("\n")}\n`;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const operation = process.argv[2];
  const result = process.argv[3]
    ? JSON.parse(await readFile(process.argv[3], "utf8"))
    : undefined;
  const attemptRef = process.env.RELEASE_CURRENT_ATTEMPT_REF
    ? JSON.parse(process.env.RELEASE_CURRENT_ATTEMPT_REF)
    : undefined;
  const summary = releaseSummary({
    operation,
    selected: (process.env.RELEASE_SELECTION ?? "").split(","),
    candidateRef: JSON.parse(process.env.RELEASE_CANDIDATE_REF ?? "null"),
    attemptRef,
    result,
  });
  if (process.env.GITHUB_STEP_SUMMARY)
    await appendFile(process.env.GITHUB_STEP_SUMMARY, summary);
  process.stdout.write(summary);
}
