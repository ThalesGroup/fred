import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  extractReleaseArtifact,
  assertCandidateTransferBinding,
  retrieveReleaseArtifact,
  uploadedArtifactRef,
} from "../scripts/release-artifact.mjs";
import { run } from "../scripts/process.mjs";

test("a retained ZIP is checked against independently pinned API and byte identities", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-artifact-test-"));
  try {
    await writeFile(path.join(root, "publishing-attempt.json"), "{}\n");
    await run("zip", ["-q", "artifact.zip", "publishing-attempt.json"], {
      cwd: root,
    });
    const zip = await readFile(path.join(root, "artifact.zip"));
    const digest = createHash("sha256").update(zip).digest("hex");
    const ref = uploadedArtifactRef({
      artifactId: "17",
      artifactDigest: `sha256:${digest}`,
      recordDigest: `sha256-${"A".repeat(43)}=`,
      runId: "61",
      runAttempt: "2",
      sourceCommit: "a".repeat(40),
    });
    const metadata = {
      id: 17,
      workflow_run: { id: 61, head_sha: "a".repeat(40) },
      expired: false,
      digest: `sha256:${digest}`,
    };
    const runMetadata = {
      id: 61,
      run_attempt: 2,
      head_sha: "a".repeat(40),
      head_branch: "swift",
      event: "workflow_dispatch",
      path: ".github/workflows/Publish-frontend-packages.yml",
    };
    const read = async (url) =>
      url.endsWith("/zip")
        ? new Response(zip)
        : Response.json(url.includes("/attempts/") ? runMetadata : metadata);
    const artifact = await retrieveReleaseArtifact({
      ref,
      repository: "ThalesGroup/fred",
      token: "fixture-read-token",
      fetchImpl: read,
    });
    const extracted = await extractReleaseArtifact({
      zip: artifact.zip,
      expectedFiles: ["publishing-attempt.json"],
    });
    assert.deepEqual(extracted.names, ["publishing-attempt.json"]);
    await extracted.cleanup();
    await assert.rejects(
      retrieveReleaseArtifact({
        ref: { ...ref, zipSha256: "0".repeat(64) },
        repository: "ThalesGroup/fred",
        token: "fixture-read-token",
        fetchImpl: read,
      }),
      /API digest differs/,
    );
    await assert.rejects(
      retrieveReleaseArtifact({
        ref,
        repository: "ThalesGroup/fred",
        token: "fixture-read-token",
        fetchImpl: async (url) =>
          url.endsWith("/zip")
            ? new Response(Buffer.from("changed"))
            : Response.json(
                url.includes("/attempts/") ? runMetadata : metadata,
              ),
      }),
      /ZIP SHA-256 differs/,
    );
    await assert.rejects(
      retrieveReleaseArtifact({
        ref,
        repository: "ThalesGroup/fred",
        token: "fixture-read-token",
        fetchImpl: async () => Response.json({ ...metadata, expired: true }),
      }),
      /expired/,
    );
    await assert.rejects(
      retrieveReleaseArtifact({
        ref,
        repository: "ThalesGroup/fred",
        token: "fixture-read-token",
        fetchImpl: async (url) =>
          Response.json(
            url.includes("/attempts/")
              ? { ...runMetadata, run_attempt: 3 }
              : metadata,
          ),
      }),
      /workflow attempt differs/,
    );
    await assert.rejects(
      extractReleaseArtifact({ zip, expectedFiles: ["candidate-record.json"] }),
      /file set differs/,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});

test("candidate transfer evidence and record bind the actual metadata bytes and execution", () => {
  const metadata = {
    artifactName: "reviewed-candidate",
    execution: { provider: "github-actions", runId: "61", runAttempt: "1" },
  };
  const metadataBytes = Buffer.from(JSON.stringify(metadata));
  const digest = `sha256-${createHash("sha256").update(metadataBytes).digest("base64")}`;
  const origin = {
    metadataDigest: digest,
    artifactName: metadata.artifactName,
    execution: metadata.execution,
  };
  const binding = {
    metadataBytes,
    metadata,
    evidence: { transfer: origin },
    record: { transferOrigin: origin },
  };
  assert.doesNotThrow(() => assertCandidateTransferBinding(binding));
  assert.throws(
    () =>
      assertCandidateTransferBinding({
        ...binding,
        metadataBytes: Buffer.from(`${metadataBytes}\n`),
      }),
    /metadata bytes/,
  );
  assert.throws(
    () =>
      assertCandidateTransferBinding({
        ...binding,
        metadata: { ...metadata, artifactName: "changed" },
      }),
    /artifact name/,
  );
  assert.throws(
    () =>
      assertCandidateTransferBinding({
        ...binding,
        evidence: {
          transfer: {
            ...origin,
            execution: { ...metadata.execution, runAttempt: "2" },
          },
        },
      }),
    /execution differs/,
  );
});

test("retained ZIP extraction rejects symbolic links even when entry names are allowed", async () => {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-artifact-link-"));
  try {
    await symlink("../outside.tgz", path.join(root, "selected.tgz"));
    await run("zip", ["-y", "-q", "artifact.zip", "selected.tgz"], {
      cwd: root,
    });
    await assert.rejects(
      extractReleaseArtifact({
        zip: await readFile(path.join(root, "artifact.zip")),
        expectedFiles: ["selected.tgz"],
      }),
      /regular|symbolic|symlink/i,
    );
  } finally {
    await rm(root, { recursive: true, force: true });
  }
});
