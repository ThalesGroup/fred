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
import {
  access,
  cp,
  mkdir,
  mkdtemp,
  readFile,
  rename,
  rm,
  stat,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import {
  assertDedicatedFixtureOutput,
  assertSafeFixtureTransferOutput,
  createReleaseCandidateTransfer,
  createFixtureTransfer,
  releaseCandidateTransferMetadataFilename,
  fixtureArchiveFilename,
  fixtureExecution,
  fixtureTransferMetadataFilename,
  validateFixtureTransferMetadata,
  verifyFixtureTransfer,
} from "../scripts/fixture-transfer.mjs";
import {
  persistCandidatePair,
  validateTransferredFixture,
} from "../scripts/fixture-transfer-validation.mjs";
import {
  loadReleaseContract,
  packageRoles,
  workspaceRoot,
} from "../scripts/release-contract.mjs";
import { sha512Integrity } from "../scripts/release-evidence.mjs";
import { assertDocumentSchema } from "../scripts/schema-validation.mjs";

const sourceCommit = "a".repeat(40);
const execution = fixtureExecution({
  provider: "local-rehearsal",
  repository: "ThalesGroup/fred",
  workflow: "fixture-transfer-test",
  runId: "fixture-run",
  runAttempt: "1",
});
const applicationToolchain = {
  source: "apps/frontend/package-lock.json",
  isolation: "application-owned",
  node: "22.13.0",
  npm: "10.9.2",
};
const successfulGates = {
  archives: { validated: true, reusedPackedBytes: true },
  consumers: { designTokens: {}, ui: {}, iframeSdk: {} },
  browser: {
    dependencyInstallations: 0,
    browserProvisioning: 0,
    externalRequests: 0,
  },
  host: { test: "fixture-host-test" },
};

async function roots(context) {
  const root = await mkdtemp(
    path.join(os.tmpdir(), "fred-fixture-transfer-test-"),
  );
  context.after(() => rm(root, { recursive: true, force: true }));
  return {
    root,
    producer: path.join(root, "producer"),
    receiver: path.join(root, "receiver"),
    evidence: path.join(root, "final", "evidence.json"),
    stage: path.join(root, "staged"),
  };
}

test("a failed second final rename removes a complete record and both temporary files", async (context) => {
  const { root } = await roots(context);
  const recordPath = path.join(root, "candidate-record.json");
  const evidencePath = path.join(root, "candidate-evidence.json");
  let renames = 0;
  await assert.rejects(
    persistCandidatePair({
      recordPath,
      evidencePath,
      record: { readiness: "complete" },
      evidence: { kind: "release-candidate-evidence" },
      renameFile: async (...args) => {
        if (++renames === 2) throw new Error("second rename failed");
        return rename(...args);
      },
    }),
    /second rename failed/,
  );
  assert.equal(renames, 2);
  for (const file of [
    recordPath,
    evidencePath,
    `${recordPath}.tmp`,
    `${evidencePath}.tmp`,
  ])
    await assert.rejects(access(file), { code: "ENOENT" });
});

async function packerFixtures(root, contract, calls = []) {
  const packers = {};
  for (const role of packageRoles) {
    const expected = contract.packages[role];
    const archivePath = path.join(
      root,
      fixtureArchiveFilename(expected.name, expected.version),
    );
    packers[role] = async ({ validate, contract: selected }) => {
      calls.push(role);
      assert.equal(validate, true);
      assert.equal(selected, contract);
      await writeFile(archivePath, `${role} transferable fixture bytes`);
      return { archivePath };
    };
  }
  return packers;
}

async function createTransfer(context, selection) {
  const paths = await roots(context);
  const contract = await loadReleaseContract();
  const calls = [];
  await createFixtureTransfer({
    outputRoot: paths.producer,
    contract,
    selection,
    sourceCommit,
    sourceTreeClean: true,
    producerToolchain: contract.releaseToolchain,
    execution,
    createdAt: "2026-09-11T00:00:00.000Z",
    packers: await packerFixtures(paths.root, contract, calls),
  });
  await cp(paths.producer, paths.receiver, { recursive: true });
  return { paths, contract, calls };
}

test("schema and shared validator accept actual generated selected transfers and legacy all-member metadata", async (context) => {
  const schemaPath = path.join(
    workspaceRoot,
    "release/fixture-transfer.schema.json",
  );
  for (const [selection, expected] of [
    [undefined, ["designTokens", "ui", "iframeSdk"]],
    ["iframeSdk", ["iframeSdk"]],
    ["designTokens", ["designTokens"]],
    ["ui", ["ui"]],
    ["ui,designTokens", ["designTokens", "ui"]],
  ]) {
    await context.test(
      selection ?? "default all-member",
      async (subcontext) => {
        const { paths, contract, calls } = await createTransfer(
          subcontext,
          selection,
        );
        const metadata = JSON.parse(
          await readFile(
            path.join(paths.producer, fixtureTransferMetadataFilename),
            "utf8",
          ),
        );
        assert.deepEqual(calls, expected);
        assert.deepEqual(metadata.selectedIds, expected);
        assert.deepEqual(Object.keys(metadata.packages), expected);
        assert.equal(
          assertDocumentSchema(metadata, schemaPath, "generated transfer"),
          metadata,
        );
        assert.equal(
          validateFixtureTransferMetadata(metadata, {
            contract,
            sourceCommit,
            sourceTreeClean: true,
            execution,
          }),
          metadata,
        );
        if (selection === undefined) {
          delete metadata.selectedIds;
          await writeFile(
            path.join(paths.receiver, fixtureTransferMetadataFilename),
            `${JSON.stringify(metadata, null, 2)}\n`,
          );
          assertDocumentSchema(
            metadata,
            schemaPath,
            "legacy all-member transfer",
          );
          const verified = await verifyFixtureTransfer({
            transferRoot: paths.receiver,
            contract,
            sourceCommit,
            sourceTreeClean: true,
            execution,
          });
          assert.deepEqual(Object.keys(verified.archivePaths), expected);
          const result = await validateTransferredFixture({
            transferRoot: paths.receiver,
            evidencePath: paths.evidence,
            stageRoot: paths.stage,
            contract,
            sourceCommit,
            sourceTreeClean: true,
            execution,
            applicationToolchain,
            runGates: async ({ selectedIds }) => {
              assert.deepEqual(selectedIds, expected);
              return successfulGates;
            },
          });
          assert.equal(result.record.readiness, "fixture");
        }
      },
    );
  }
});

test("generated transfer metadata rejects invalid selection and package-set mismatches", async (context) => {
  const { paths, contract } = await createTransfer(context, "ui");
  const generated = JSON.parse(
    await readFile(
      path.join(paths.producer, fixtureTransferMetadataFilename),
      "utf8",
    ),
  );
  const validate = (metadata) =>
    validateFixtureTransferMetadata(metadata, {
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
    });
  for (const [selectedIds, failure] of [
    [[], /schema invalid.*selectedIds/],
    [["ui", "ui"], /schema invalid.*selectedIds/],
    [["unknown"], /unregistered selected member/],
    [["frontend-packages-workspace"], /schema invalid.*selectedIds/],
    [["ui", "designTokens"], /transfer selection order differs/],
  ]) {
    const changed = structuredClone(generated);
    changed.selectedIds = selectedIds;
    assert.throws(() => validate(changed), failure);
  }
  const future = structuredClone(generated);
  future.selectedIds = ["futureTool"];
  future.packages.futureTool = { ...future.packages.ui, role: "futureTool" };
  delete future.packages.ui;
  assertDocumentSchema(
    future,
    path.join(workspaceRoot, "release/fixture-transfer.schema.json"),
    "future registration shape",
  );
  assert.throws(() => validate(future), /unregistered selected member/);
  for (const mutate of [
    (metadata) => delete metadata.packages.ui,
    (metadata) => {
      metadata.packages.designTokens = {
        ...metadata.packages.ui,
        role: "designTokens",
      };
    },
    (metadata) => delete metadata.selectedIds,
  ]) {
    const changed = structuredClone(generated);
    mutate(changed);
    assert.throws(() => validate(changed), /schema invalid|packages keys/);
  }
});

async function mutateMetadata(root, mutate) {
  const metadataPath = path.join(root, fixtureTransferMetadataFilename);
  const metadata = JSON.parse(await readFile(metadataPath, "utf8"));
  mutate(metadata);
  await writeFile(metadataPath, `${JSON.stringify(metadata, null, 2)}\n`);
}

test("a valid fixture transfer is consumed from separate exact bytes without rebuilding", async (context) => {
  const { paths, contract, calls } = await createTransfer(context);
  assert.deepEqual(calls, ["designTokens", "ui", "iframeSdk"]);
  let downstreamCalls = 0;
  const result = await validateTransferredFixture({
    transferRoot: paths.receiver,
    evidencePath: paths.evidence,
    stageRoot: paths.stage,
    contract,
    sourceCommit,
    sourceTreeClean: true,
    execution,
    applicationToolchain,
    runGates: async ({ archivePaths, integrities }) => {
      downstreamCalls += 1;
      for (const role of packageRoles) {
        assert(archivePaths[role].startsWith(paths.receiver));
        assert.equal(
          integrities[role],
          await sha512Integrity(archivePaths[role]),
        );
      }
      return successfulGates;
    },
  });
  assert.equal(downstreamCalls, 1);
  assert.equal(result.evidence.kind, "fixture-candidate-evidence");
  assert.equal(result.evidence.transfer.kind, "fixture-archive-transfer");
  assert.equal(result.evidence.transfer.metadataDigest, result.metadataDigest);
  assert.equal(result.evidence.sourceCommit, sourceCommit);
  assert.deepEqual(result.evidence.applicationToolchain, applicationToolchain);
  assert.equal((await stat(paths.evidence)).isFile(), true);
  assert.equal(result.record.kind, "candidate");
  assert.equal(result.record.readiness, "fixture");
  assert.deepEqual(result.record.transferOrigin, {
    artifactName: result.evidence.transfer.artifactName,
    metadataDigest: result.metadataDigest,
    execution,
  });
  assert.equal((await stat(result.recordPath)).isFile(), true);
  assert.deepEqual(calls, ["designTokens", "ui", "iframeSdk"]);
});

test("selected SDK/UI archives transfer to a separate application environment without rebuilding", async (context) => {
  for (const [selection, expected] of [
    ["iframeSdk", ["iframeSdk"]],
    ["ui", ["ui"]],
  ]) {
    const paths = await roots(context);
    const contract = await loadReleaseContract();
    const calls = [];
    await createFixtureTransfer({
      outputRoot: paths.producer,
      contract,
      selection,
      sourceCommit,
      sourceTreeClean: true,
      producerToolchain: contract.releaseToolchain,
      execution,
      packers: await packerFixtures(paths.root, contract, calls),
    });
    assert.deepEqual(calls, expected);
    await cp(paths.producer, paths.receiver, { recursive: true });
    const result = await validateTransferredFixture({
      transferRoot: paths.receiver,
      evidencePath: paths.evidence,
      stageRoot: paths.stage,
      contract,
      selection,
      sourceCommit,
      sourceTreeClean: true,
      execution,
      applicationToolchain,
      runGates: async ({ archivePaths, integrities, selectedIds }) => {
        assert.deepEqual(selectedIds, expected);
        assert.deepEqual(Object.keys(archivePaths), expected);
        for (const id of expected)
          assert.equal(
            integrities[id],
            await sha512Integrity(archivePaths[id]),
          );
        return successfulGates;
      },
    });
    assert.deepEqual(Object.keys(result.evidence.packages), expected);
    assert.deepEqual(
      result.record.selected.map(({ id }) => id),
      expected,
    );
    assert.deepEqual(
      result.record.compatibilityOnly.map(({ id }) => id),
      selection === "ui" ? ["designTokens"] : [],
    );
    await assert.rejects(
      validateTransferredFixture({
        transferRoot: paths.receiver,
        evidencePath: paths.evidence,
        stageRoot: paths.stage,
        contract,
        selection: selection === "ui" ? "iframeSdk" : "ui",
        sourceCommit,
        sourceTreeClean: true,
        execution,
        applicationToolchain,
        runGates: async () =>
          assert.fail("mismatched selection must fail before gates"),
      }),
      /selection differs/,
    );
    assert.deepEqual(calls, expected);
  }
});

test("a maintainer-confirmed transfer becomes approved evidence only after receiver gates", async (context) => {
  const paths = await roots(context);
  const contract = await loadReleaseContract(
    path.join(workspaceRoot, "release/proposed-release-contract.json"),
  );
  await createReleaseCandidateTransfer({
    outputRoot: paths.producer,
    contract,
    sourceCommit,
    sourceTreeClean: true,
    producerToolchain: contract.releaseToolchain,
    execution,
    createdAt: "2026-09-14T00:00:00.000Z",
  });
  await cp(paths.producer, paths.receiver, { recursive: true });
  const result = await validateTransferredFixture({
    transferRoot: paths.receiver,
    evidencePath: paths.evidence,
    stageRoot: paths.stage,
    contract,
    sourceCommit,
    sourceTreeClean: true,
    execution,
    applicationToolchain,
    runGates: async () => successfulGates,
  });
  assert.equal(result.record.readiness, "incomplete"); // Injected receiver gates remain controlled.
  assert.equal(result.evidence.kind, "release-candidate-evidence");
  assert.equal(
    result.evidence.transfer.kind,
    "release-candidate-archive-transfer",
  );
  assert.equal(
    (
      await stat(
        path.join(paths.receiver, releaseCandidateTransferMetadataFilename),
      )
    ).isFile(),
    true,
  );
});

test("a proposed contract cannot create an archive transfer", async (context) => {
  const paths = await roots(context);
  const contract = await loadReleaseContract(
    path.join(workspaceRoot, "release/proposed-release-contract.json"),
  );
  contract.state = "proposed";
  contract.maintainerApproval.owners.packageApi = null;
  contract.maintainerApproval.publishingPolicy = null;
  await assert.rejects(
    createReleaseCandidateTransfer({
      outputRoot: paths.producer,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      producerToolchain: contract.releaseToolchain,
      execution,
      packers: await packerFixtures(paths.root, contract),
    }),
    /maintainer-confirmed/,
  );
});

test("invalid transfer sets fail before downstream installation or execution", async (context) => {
  const cases = [
    {
      name: "missing archive",
      mutate: async ({ paths, contract }) =>
        rm(
          path.join(
            paths.receiver,
            fixtureArchiveFilename(
              contract.packages.ui.name,
              contract.packages.ui.version,
            ),
          ),
        ),
      error: /file set differs/,
    },
    {
      name: "additional file",
      mutate: ({ paths }) =>
        writeFile(path.join(paths.receiver, "unexpected.tgz"), "unexpected"),
      error: /file set differs/,
    },
    {
      name: "truncated archive",
      mutate: async ({ paths, contract }) =>
        writeFile(
          path.join(
            paths.receiver,
            fixtureArchiveFilename(
              contract.packages.designTokens.name,
              contract.packages.designTokens.version,
            ),
          ),
          "short",
        ),
      error: /byte length differs/,
    },
    {
      name: "modified archive",
      mutate: async ({ paths, contract }) => {
        const target = path.join(
          paths.receiver,
          fixtureArchiveFilename(
            contract.packages.iframeSdk.name,
            contract.packages.iframeSdk.version,
          ),
        );
        const bytes = await readFile(target);
        bytes[0] ^= 1;
        await writeFile(target, bytes);
      },
      error: /integrity differs/,
    },
    {
      name: "wrong contract digest",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          metadata.contract.digest = `sha256-${Buffer.alloc(32).toString("base64")}`;
        }),
      error: /contract digest differs/,
    },
    {
      name: "wrong package coordinate",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          metadata.packages.ui.coordinate = "@fred/ui@9.9.9";
        }),
      error: /coordinate differs/,
    },
    {
      name: "missing integrity",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          delete metadata.packages.iframeSdk.integrity;
        }),
      error: /schema invalid/,
    },
    {
      name: "malformed integrity",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          metadata.packages.designTokens.integrity = "sha512-not base64";
        }),
      error: /schema invalid/,
    },
    {
      name: "wrong-length integrity",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          metadata.packages.designTokens.integrity = "sha512-YQ==";
        }),
      error: /schema invalid/,
    },
    {
      name: "inconsistent integrity",
      mutate: ({ paths }) =>
        mutateMetadata(paths.receiver, (metadata) => {
          metadata.packages.designTokens.integrity = `sha512-${Buffer.alloc(64).toString("base64")}`;
        }),
      error: /integrity differs/,
    },
  ];
  for (const scenario of cases) {
    await context.test(scenario.name, async (subcontext) => {
      const fixture = await createTransfer(subcontext);
      await scenario.mutate(fixture);
      let downstreamCalls = 0;
      await assert.rejects(
        validateTransferredFixture({
          transferRoot: fixture.paths.receiver,
          evidencePath: fixture.paths.evidence,
          stageRoot: fixture.paths.stage,
          contract: fixture.contract,
          sourceCommit,
          sourceTreeClean: true,
          execution,
          applicationToolchain,
          runGates: async () => {
            downstreamCalls += 1;
            return successfulGates;
          },
        }),
        scenario.error,
      );
      assert.equal(downstreamCalls, 0);
      await assert.rejects(access(fixture.paths.evidence), { code: "ENOENT" });
    });
  }
});

test("a non-regular transferred archive is rejected", async (context) => {
  const { paths, contract } = await createTransfer(context);
  const filename = fixtureArchiveFilename(
    contract.packages.ui.name,
    contract.packages.ui.version,
  );
  const target = path.join(paths.receiver, filename);
  const outside = path.join(paths.root, "outside-ui.tgz");
  await rm(target);
  await writeFile(outside, "ui transferable fixture bytes");
  await symlink(outside, target);
  await assert.rejects(
    verifyFixtureTransfer({
      transferRoot: paths.receiver,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
    }),
    /must be a regular non-symlink file/,
  );
});

test("commit and workflow-run mismatches reject before downstream gates", async (context) => {
  const { paths, contract } = await createTransfer(context);
  for (const expected of [
    { sourceCommit: "b".repeat(40), execution },
    {
      sourceCommit,
      execution: { ...execution, runId: "different-run" },
    },
    {
      sourceCommit,
      execution: { ...execution, runAttempt: "2" },
    },
    {
      sourceCommit,
      execution: { ...execution, repository: "Other/fred" },
    },
    {
      sourceCommit,
      execution: { ...execution, workflow: "different-workflow" },
    },
  ]) {
    await assert.rejects(
      verifyFixtureTransfer({
        transferRoot: paths.receiver,
        contract,
        sourceTreeClean: true,
        ...expected,
      }),
      /source commit differs|execution differs/,
    );
  }
});

test("application toolchain metadata is validated before downstream gates", async (context) => {
  const { paths, contract } = await createTransfer(context);
  let downstreamCalls = 0;
  await assert.rejects(
    validateTransferredFixture({
      transferRoot: paths.receiver,
      evidencePath: paths.evidence,
      stageRoot: paths.stage,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
      applicationToolchain: { ...applicationToolchain, npm: "latest" },
      runGates: async () => {
        downstreamCalls += 1;
        return successfulGates;
      },
    }),
    /application npm must be an exact version/,
  );
  assert.equal(downstreamCalls, 0);
});

test("a local generated archive cannot replace a missing transferred archive", async (context) => {
  const { paths, contract } = await createTransfer(context);
  const filename = fixtureArchiveFilename(
    contract.packages.ui.name,
    contract.packages.ui.version,
  );
  await rm(path.join(paths.receiver, filename));
  await writeFile(path.join(paths.root, filename), "local fallback bytes");
  await assert.rejects(
    verifyFixtureTransfer({
      transferRoot: paths.receiver,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
    }),
    /file set differs/,
  );
});

test("a failed downstream gate removes stale and writes no final success evidence", async (context) => {
  const { paths, contract } = await createTransfer(context);
  await mkdir(path.dirname(paths.evidence), { recursive: true });
  await writeFile(paths.evidence, "stale success");
  const recordPath = path.join(
    path.dirname(paths.evidence),
    "candidate-record.json",
  );
  await writeFile(recordPath, "stale record");
  await assert.rejects(
    validateTransferredFixture({
      transferRoot: paths.receiver,
      evidencePath: paths.evidence,
      stageRoot: paths.stage,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
      applicationToolchain,
      runGates: async () => {
        throw new Error("browser gate failed");
      },
    }),
    /browser gate failed/,
  );
  await assert.rejects(access(paths.evidence), { code: "ENOENT" });
  await assert.rejects(access(`${paths.evidence}.tmp`), { code: "ENOENT" });
  await assert.rejects(access(recordPath), { code: "ENOENT" });
});

test("an archive changed by a downstream gate cannot be re-baselined into final evidence", async (context) => {
  const { paths, contract } = await createTransfer(context);
  await assert.rejects(
    validateTransferredFixture({
      transferRoot: paths.receiver,
      evidencePath: paths.evidence,
      stageRoot: paths.stage,
      contract,
      sourceCommit,
      sourceTreeClean: true,
      execution,
      applicationToolchain,
      runGates: async ({ archivePaths }) => {
        await writeFile(archivePaths.ui, "mutated by downstream gate");
        return successfulGates;
      },
    }),
    /byte length differs|integrity differs/,
  );
  await assert.rejects(access(paths.evidence), { code: "ENOENT" });
});

test("fixture transfer creation rejects broad or sensitive output roots before deletion", async () => {
  const repositoryRoot = path.resolve(workspaceRoot, "../..");
  const protectedPaths = [
    path.parse(workspaceRoot).root,
    os.homedir(),
    repositoryRoot,
    workspaceRoot,
    path.join(workspaceRoot, "target"),
  ];
  for (const protectedPath of protectedPaths)
    await assert.rejects(
      assertSafeFixtureTransferOutput(protectedPath),
      /dedicated descendant|overlaps a sensitive repository or filesystem root/,
    );
  await access(path.join(workspaceRoot, "package.json"));
});

test("sensitive checkout roots remain rejected inside system temporary space", () => {
  const temporaryRoot = path.join(path.parse(workspaceRoot).root, "tmp");
  const repository = path.join(temporaryRoot, "checkout");
  const producerWorkspace = path.join(repository, "libs/frontend");
  const producerTarget = path.join(producerWorkspace, "target");
  const common = {
    producerTarget,
    repository,
    producerWorkspace,
    home: path.join(temporaryRoot, "home"),
    temporaryRoots: [temporaryRoot],
  };
  for (const target of [repository, producerWorkspace, producerTarget])
    assert.throws(
      () => assertDedicatedFixtureOutput({ target, ...common }),
      /overlaps a sensitive repository or filesystem root/,
    );
  assert.equal(
    assertDedicatedFixtureOutput({
      target: path.join(producerTarget, "fixture-transfer"),
      ...common,
    }),
    path.join(producerTarget, "fixture-transfer"),
  );
  assert.equal(
    assertDedicatedFixtureOutput({
      target: path.join(temporaryRoot, "fixture-rehearsal"),
      ...common,
    }),
    path.join(temporaryRoot, "fixture-rehearsal"),
  );
});
