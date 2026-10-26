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
import { readFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

const numericIdentifier = String.raw`(?:0|[1-9]\d*)`;
const prereleaseIdentifier = String.raw`(?:${numericIdentifier}|\d*[A-Za-z-][0-9A-Za-z-]*)`;
const semanticVersionPattern = new RegExp(
  String.raw`^${numericIdentifier}\.${numericIdentifier}\.${numericIdentifier}(?:-${prereleaseIdentifier}(?:\.${prereleaseIdentifier})*)?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$`,
);
const channelPattern = /^[a-z0-9][a-z0-9._-]*$/;
const commitPattern = /^[0-9a-f]{40}$/;
const runIdPattern = /^[1-9][0-9]*$/;

export const publishWorkflowPath =
  ".github/workflows/Publish-frontend-packages.yml";

export function validatePromotionInputs({ version, channel }) {
  assert(
    semanticVersionPattern.test(version ?? ""),
    "version must be an exact semantic version",
  );
  assert(channelPattern.test(channel ?? ""), "channel is invalid");
  return { version, channel };
}

export async function resolveSelectedWorkflowRun({
  github,
  owner,
  repo,
  runId,
  expectedBranch = "swift",
  expectedWorkflowPath = publishWorkflowPath,
}) {
  assert(runIdPattern.test(runId ?? ""), "selected run ID is invalid");
  const numericRunId = Number(runId);
  assert(Number.isSafeInteger(numericRunId), "selected run ID is invalid");
  const { data: run } = await github.rest.actions.getWorkflowRun({
    owner,
    repo,
    run_id: numericRunId,
  });
  const repository = `${owner}/${repo}`;
  assert.equal(String(run.id), runId, "selected workflow run ID differs");
  assert.equal(
    run.repository?.full_name,
    repository,
    "selected workflow run belongs to another repository",
  );
  assert.equal(
    run.head_repository?.full_name,
    repository,
    "selected workflow run source belongs to another repository",
  );
  assert.equal(
    run.path,
    expectedWorkflowPath,
    "selected run used another workflow",
  );
  assert.equal(
    run.head_branch,
    expectedBranch,
    "selected run used another source branch",
  );
  assert(
    commitPattern.test(run.head_sha ?? ""),
    "selected workflow run head commit is invalid",
  );
  return {
    repository,
    workflow: `${repository}/${run.path}@refs/heads/${run.head_branch}`,
    runId: String(run.id),
    sourceCommit: run.head_sha,
  };
}

export function validateReleaseOrigin({ metadata, identity }) {
  assert.deepEqual(
    metadata.preparedBy,
    {
      kind: "github-actions",
      repository: identity.repository,
      workflow: identity.workflow,
      runId: identity.runId,
    },
    "release metadata origin differs from the selected workflow run",
  );
  assert.equal(
    metadata.sourceCommit,
    identity.sourceCommit,
    "release source commit differs from the selected workflow run",
  );
  return metadata.sourceCommit;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  try {
    if (process.argv[2] === "validate-promotion")
      validatePromotionInputs({
        version: process.env.VERSION,
        channel: process.env.CHANNEL,
      });
    else if (process.argv[2] === "validate-release-origin") {
      const metadata = JSON.parse(await readFile(process.argv[3], "utf8"));
      const sourceCommit = validateReleaseOrigin({
        metadata,
        identity: {
          repository: process.env.EXPECTED_REPOSITORY,
          workflow: process.env.EXPECTED_WORKFLOW,
          runId: process.env.EXPECTED_RUN_ID,
          sourceCommit: process.env.EXPECTED_SOURCE_COMMIT,
        },
      });
      process.stdout.write(`${sourceCommit}\n`);
    } else throw new Error("operation is invalid");
  } catch (error) {
    process.stderr.write(`${error.message}\n`);
    process.exitCode = 1;
  }
}
