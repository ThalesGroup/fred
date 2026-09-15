import assert from "node:assert/strict";
import { execFile } from "node:child_process";
import { createHash, generateKeyPairSync, sign } from "node:crypto";
import {
  chmod,
  mkdir,
  mkdtemp,
  readFile,
  rm,
  writeFile,
} from "node:fs/promises";
import https from "node:https";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import { promisify } from "node:util";

import {
  archiveTransferArtifactName,
  fixtureArchiveFilename,
} from "../scripts/fixture-transfer.mjs";
import {
  loadReleaseContract,
  packageRoles,
  workspaceRoot,
} from "../scripts/release-contract.mjs";
import {
  createCandidateEvidence,
  releaseContractDigest,
} from "../scripts/release-evidence.mjs";
import { run } from "../scripts/process.mjs";

const execFileAsync = promisify(execFile);
const scriptPath = path.join(workspaceRoot, "scripts/bootstrap-recovery.mjs");
const registryVerifierPath = path.join(
  workspaceRoot,
  "scripts/registry-verifier.mjs",
);
const loaderPath = path.join(
  workspaceRoot,
  "tests/fixtures/recovery-cli-loader.mjs",
);
const fixtureNpmPath = path.join(
  workspaceRoot,
  "tests/fixtures/recovery-cli-npm.mjs",
);
const producerToolchain = { node: "24.21.0", npm: "11.19.0" };
const applicationToolchain = {
  source: "apps/frontend/package-lock.json",
  isolation: "application-owned",
  node: "22.13.0",
  npm: "10.9.2",
};
const gates = {
  archives: { validated: true, reusedPackedBytes: true },
  consumers: { designTokens: {}, ui: {}, iframeSdk: {} },
  browser: {
    dependencyInstallations: 0,
    browserProvisioning: 0,
    externalRequests: 0,
  },
  host: { test: "recovery-cli-fixture-host" },
};

async function listen(server) {
  await new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", resolve);
  });
  return `https://127.0.0.1:${server.address().port}/`;
}

async function cliFixture(context, registry) {
  const root = await mkdtemp(path.join(os.tmpdir(), "fred-recovery-cli-"));
  context.after(() => rm(root, { recursive: true, force: true }));
  const [contract, plan] = await Promise.all([
    loadReleaseContract(
      path.join(workspaceRoot, "release/development-fixture-contract.json"),
    ),
    readFile(
      path.join(workspaceRoot, "release/bootstrap-recovery.json"),
      "utf8",
    ).then(JSON.parse),
  ]);
  contract.state = "maintainer-confirmed";
  contract.registry = registry;
  for (const selected of Object.values(contract.packages))
    selected.expectedManifest.publishConfig.registry = registry;
  contract.maintainerApproval = {
    scopeOwner: "fred-oss",
    owners: {
      packageApi: "test-package-api-owner",
      sdkProtocol: "test-sdk-protocol-owner",
      release: "test-release-owner",
      npmPublishing: "test-npm-publishing-owner",
    },
    bootstrapIdentity: "marc.fawaz",
    bootstrapAuthorityVerified: true,
    registryAccess: "public",
    publishingPolicy: "direct",
  };
  contract.expectedProvenance = {
    repository: "https://github.com/ThalesGroup/fred",
    workflow: plan.recoveryExecution.workflow,
    certificateIssuer: "https://token.actions.githubusercontent.com",
  };
  const archives = [];
  for (const role of packageRoles) {
    const selected = contract.packages[role];
    const archivePath = path.join(
      root,
      fixtureArchiveFilename(selected.name, selected.version),
    );
    await writeFile(archivePath, `${role} original approved bytes`);
    archives.push({ role, path: archivePath });
  }
  const evidence = await createCandidateEvidence({
    contract,
    archives,
    sourceCommit: plan.incident.sourceCommit,
    producerToolchain,
    applicationToolchain,
    gates,
    approved: true,
  });
  const execution = {
    provider: "github-actions",
    repository: "ThalesGroup/fred",
    workflow: "Publish frontend packages",
    runId: plan.incident.workflowRunId,
    runAttempt: plan.incident.workflowRunAttempt,
  };
  const artifactName = archiveTransferArtifactName({
    contractState: contract.state,
    sourceCommit: plan.incident.sourceCommit,
    ...execution,
  });
  const transfer = {
    schemaVersion: 1,
    kind: "release-candidate-archive-transfer",
    artifactName,
    createdAt: "2026-09-14T14:09:00.000Z",
    sourceCommit: plan.incident.sourceCommit,
    sourceTreeClean: true,
    contract: {
      state: contract.state,
      digest: releaseContractDigest(contract),
    },
    producerToolchain,
    execution,
    producerValidation: {
      archives: true,
      consumers: false,
      browser: false,
      host: false,
    },
    packages: Object.fromEntries(
      packageRoles.map((role) => {
        const selected = contract.packages[role];
        const candidate = evidence.packages[role];
        return [
          role,
          {
            role,
            name: selected.name,
            version: selected.version,
            coordinate: candidate.coordinate,
            filename: candidate.filename,
            bytes: candidate.bytes,
            integrity: candidate.integrity,
          },
        ];
      }),
    ),
  };
  const transferPath = path.join(root, "candidate-transfer.json");
  await writeFile(transferPath, `${JSON.stringify(transfer, null, 2)}\n`);
  evidence.transfer = {
    kind: transfer.kind,
    artifactName,
    metadataFilename: "candidate-transfer.json",
    metadataDigest: `sha256-${createHash("sha256")
      .update(await readFile(transferPath))
      .digest("base64")}`,
    sourceTreeClean: true,
    execution,
  };
  await writeFile(
    path.join(root, "candidate-evidence.json"),
    `${JSON.stringify(evidence, null, 2)}\n`,
  );
  const artifactZipPath = path.join(root, "original-artifact.zip");
  await run(
    "zip",
    [
      "-q",
      artifactZipPath,
      "candidate-evidence.json",
      "candidate-transfer.json",
      ...packageRoles.map((role) => evidence.packages[role].filename),
    ],
    { cwd: root },
  );
  plan.incident.artifactZipSha256 = createHash("sha256")
    .update(await readFile(artifactZipPath))
    .digest("hex");
  const artifactMetadata = {
    id: plan.incident.artifactId,
    name: plan.incident.artifactName,
    expired: false,
    digest: `sha256:${plan.incident.artifactZipSha256}`,
    workflow_run: {
      id: Number(plan.incident.workflowRunId),
      head_sha: plan.incident.sourceCommit,
      head_branch: "swift",
    },
  };
  const paths = {
    contract: path.join(root, "contract.json"),
    plan: path.join(root, "plan.json"),
    artifactMetadata: path.join(root, "artifact-metadata.json"),
    artifactZip: artifactZipPath,
    materialized: path.join(root, "materialized"),
    recoveryEvidence: path.join(root, "recovery-evidence.json"),
    commandLog: path.join(root, "commands.jsonl"),
    publishedState: path.join(root, "published.json"),
    bin: path.join(root, "bin"),
  };
  await mkdir(paths.bin);
  const npmPath = path.join(paths.bin, "npm");
  await Promise.all([
    writeFile(paths.contract, `${JSON.stringify(contract, null, 2)}\n`),
    writeFile(paths.plan, `${JSON.stringify(plan, null, 2)}\n`),
    writeFile(
      paths.artifactMetadata,
      `${JSON.stringify(artifactMetadata, null, 2)}\n`,
    ),
    writeFile(paths.commandLog, ""),
    writeFile(
      paths.publishedState,
      `${JSON.stringify({ designTokens: true, ui: false, iframeSdk: false })}\n`,
    ),
    writeFile(
      npmPath,
      `#!/bin/sh\nexec ${JSON.stringify(process.execPath)} ${JSON.stringify(fixtureNpmPath)} "$@"\n`,
    ),
  ]);
  await chmod(npmPath, 0o755);
  return { root, contract, plan, evidence, paths };
}

function githubEnvironment(input) {
  return {
    ...process.env,
    GITHUB_ACTIONS: "true",
    GITHUB_REPOSITORY: "ThalesGroup/fred",
    GITHUB_REF: "refs/heads/swift",
    GITHUB_SHA: "c".repeat(40),
    GITHUB_WORKFLOW_REF:
      "ThalesGroup/fred/.github/workflows/Publish-frontend-packages.yml@refs/heads/swift",
    GITHUB_WORKFLOW: "Publish frontend packages",
    GITHUB_RUN_ID: "40000000000",
    GITHUB_RUN_ATTEMPT: "2",
    ...input,
  };
}

function prepareArguments(paths) {
  return [
    scriptPath,
    "--mode",
    "prepare",
    "--contract",
    paths.contract,
    "--plan",
    paths.plan,
    "--artifact-zip",
    paths.artifactZip,
    "--artifact-metadata",
    paths.artifactMetadata,
    "--materialize-root",
    paths.materialized,
    "--output",
    paths.recoveryEvidence,
  ];
}

function publishArguments(paths) {
  return [
    scriptPath,
    "--mode",
    "publish",
    "--contract",
    paths.contract,
    "--plan",
    paths.plan,
    "--artifact-zip",
    path.join(paths.materialized, "original-release-artifact.zip"),
    "--artifact-metadata",
    path.join(paths.materialized, "original-artifact-metadata.json"),
    "--evidence",
    path.join(paths.materialized, "candidate-evidence.json"),
    "--recovery-evidence",
    paths.recoveryEvidence,
    "--archive-root",
    paths.materialized,
  ];
}

function controlledEnvironment(input, extra = {}) {
  const environment = githubEnvironment({
    NODE_EXTRA_CA_CERTS: input.certificatePath,
    NODE_OPTIONS: `--import=${loaderPath}`,
    PATH: `${input.paths.bin}${path.delimiter}${process.env.PATH}`,
    FRED_RECOVERY_CLI_CONTRACT: input.paths.contract,
    FRED_RECOVERY_CLI_EVIDENCE: path.join(
      input.root,
      "candidate-evidence.json",
    ),
    FRED_RECOVERY_CLI_ARCHIVE_ROOT: input.root,
    FRED_RECOVERY_CLI_COMMAND_LOG: input.paths.commandLog,
    FRED_RECOVERY_CLI_PUBLISHED_STATE: input.paths.publishedState,
    ...extra,
  });
  for (const name of ["NODE_AUTH_TOKEN", "NPM_TOKEN", "npm_token"])
    delete environment[name];
  return environment;
}

async function runCli(
  input,
  args,
  extraEnvironment = {},
  node = process.execPath,
) {
  return execFileAsync(node, args, {
    cwd: workspaceRoot,
    env: controlledEnvironment(input, extraEnvironment),
    encoding: "utf8",
    timeout: 10_000,
  });
}

async function commandLog(input) {
  return (await readFile(input.paths.commandLog, "utf8"))
    .split("\n")
    .filter(Boolean)
    .map(JSON.parse);
}

function provenanceDocument(input, role, invalidSignature) {
  const expected = input.evidence.packages[role].expectedProvenance;
  const [workflowLocation, workflowRef] = expected.workflow.split("@");
  const workflowPath = workflowLocation.slice(`${expected.repository}/`.length);
  const statement = {
    subject: [
      { digest: { sha512: expected.artifactDigest.slice("sha512-".length) } },
    ],
    predicate: {
      buildDefinition: {
        externalParameters: {
          workflow: {
            repository: expected.repository,
            path: workflowPath,
            ref: workflowRef,
          },
        },
        resolvedDependencies: [
          {
            uri: expected.repository,
            digest: { gitCommit: expected.sourceCommit },
          },
        ],
      },
    },
  };
  const payload = Buffer.from(JSON.stringify(statement)).toString("base64");
  const signature = sign(
    null,
    Buffer.from(invalidSignature ? `${payload}-invalid` : payload),
    input.privateKey,
  ).toString("base64");
  return {
    attestations: [
      {
        predicateType: "https://slsa.dev/provenance/v1",
        bundle: {
          dsseEnvelope: {
            payloadType: "application/vnd.in-toto+json",
            payload,
            signatures: [{ sig: signature }],
          },
          fixtureCertificateIdentityURI: expected.workflow,
          fixtureCertificateIssuer:
            input.contract.expectedProvenance.certificateIssuer,
          fixturePublicKey: input.publicKey,
        },
      },
    ],
  };
}

async function controlledFixture(context) {
  const tlsRoot = await mkdtemp(path.join(os.tmpdir(), "fred-recovery-tls-"));
  context.after(() => rm(tlsRoot, { recursive: true, force: true }));
  const keyPath = path.join(tlsRoot, "key.pem");
  const certificatePath = path.join(tlsRoot, "certificate.pem");
  await run("openssl", [
    "req",
    "-x509",
    "-newkey",
    "rsa:2048",
    "-nodes",
    "-days",
    "1",
    "-subj",
    "/CN=localhost",
    "-addext",
    "subjectAltName=IP:127.0.0.1",
    "-keyout",
    keyPath,
    "-out",
    certificatePath,
  ]);
  let input;
  const control = { invalidProvenance: false };
  const server = https.createServer(
    {
      key: await readFile(keyPath),
      cert: await readFile(certificatePath),
    },
    async (request, response) => {
      try {
        const selectedUrl = new URL(request.url, input.contract.registry);
        const attestationPrefix = "/-/npm/v1/attestations/";
        if (selectedUrl.pathname.startsWith(attestationPrefix)) {
          const coordinate = decodeURIComponent(
            selectedUrl.pathname.slice(attestationPrefix.length),
          );
          const role = Object.entries(input.evidence.packages).find(
            ([, candidate]) => candidate.coordinate === coordinate,
          )?.[0];
          assert(role, `unexpected controlled attestation ${coordinate}`);
          response.writeHead(200, { "content-type": "application/json" });
          response.end(
            JSON.stringify(
              provenanceDocument(input, role, control.invalidProvenance),
            ),
          );
          return;
        }
        const [encodedName, encodedVersion] = selectedUrl.pathname
          .slice(1)
          .split("/");
        const name = decodeURIComponent(encodedName);
        const version = encodedVersion
          ? decodeURIComponent(encodedVersion)
          : undefined;
        const role = Object.entries(input.contract.packages).find(
          ([, selected]) =>
            selected.name === name &&
            (version === undefined || selected.version === version),
        )?.[0];
        assert(role, `unexpected controlled metadata ${selectedUrl.pathname}`);
        const published = JSON.parse(
          await readFile(input.paths.publishedState, "utf8"),
        );
        if (!published[role]) {
          response.writeHead(404, { "content-type": "application/json" });
          response.end(JSON.stringify({ error: "not found" }));
          return;
        }
        const candidate = input.evidence.packages[role];
        response.writeHead(200, { "content-type": "application/json" });
        const metadata = {
          name: input.contract.packages[role].name,
          version: input.contract.packages[role].version,
          dist: {
            integrity: candidate.integrity,
            attestations: {
              url: new URL(
                `${attestationPrefix}${encodeURIComponent(candidate.coordinate)}`,
                input.contract.registry,
              ).href,
            },
          },
        };
        response.end(
          JSON.stringify(
            version === undefined
              ? {
                  name: metadata.name,
                  versions: { [metadata.version]: metadata },
                }
              : metadata,
          ),
        );
      } catch (error) {
        response.writeHead(500, { "content-type": "application/json" });
        response.end(JSON.stringify({ error: error.message }));
      }
    },
  );
  context.after(() => new Promise((resolve) => server.close(() => resolve())));
  input = await cliFixture(context, await listen(server));
  const { publicKey, privateKey } = generateKeyPairSync("ed25519");
  input.certificatePath = certificatePath;
  input.publicKey = publicKey.export({ type: "spki", format: "pem" });
  input.privateKey = privateKey;
  input.control = control;
  return input;
}

async function prepareRecovery(input) {
  return runCli(input, prepareArguments(input.paths));
}

test("the recovery preparation CLI completes in a fresh process", async (context) => {
  const input = await controlledFixture(context);
  const result = await prepareRecovery(input);
  assert.match(result.stdout, /prepared recovery evidence/);
  assert.equal(
    JSON.parse(await readFile(input.paths.recoveryEvidence, "utf8")).kind,
    "frontend-bootstrap-recovery-evidence",
  );
  assert.deepEqual(
    (await commandLog(input)).map(({ command }) => command),
    ["pack", "lock", "ci", "ls", "audit-signatures"],
  );
});

test("the controlled recovery publication CLI publishes only UI then SDK", async (context) => {
  const input = await controlledFixture(context);
  await prepareRecovery(input);
  await writeFile(input.paths.commandLog, "");
  const result = await runCli(input, publishArguments(input.paths));
  assert.deepEqual(JSON.parse(result.stdout).published, [
    input.evidence.packages.ui.coordinate,
    input.evidence.packages.iframeSdk.coordinate,
  ]);
  assert.deepEqual(
    (await commandLog(input))
      .filter(({ command }) => command === "publish")
      .map(({ role }) => role),
    ["ui", "iframeSdk"],
  );
});

test("invalid recovery inputs fail in fresh processes before publication", async (context) => {
  await context.test("invalid original artifact", async (subcontext) => {
    const input = await controlledFixture(subcontext);
    await writeFile(input.paths.artifactZip, "changed ZIP bytes");
    await assert.rejects(
      prepareRecovery(input),
      /original recovery artifact ZIP digest differs/,
    );
    assert.equal(
      (await commandLog(input)).some(({ command }) => command === "publish"),
      false,
    );
  });
  await context.test("altered transferred copy", async (subcontext) => {
    const input = await controlledFixture(subcontext);
    await prepareRecovery(input);
    await writeFile(input.paths.commandLog, "");
    await writeFile(
      path.join(input.paths.materialized, input.evidence.packages.ui.filename),
      "altered transferred UI bytes",
    );
    await assert.rejects(
      runCli(input, publishArguments(input.paths)),
      /candidate copy differs from the pinned original artifact/,
    );
    assert.equal(
      (await commandLog(input)).some(({ command }) => command === "publish"),
      false,
    );
  });
});

test("existing-package provenance failures stop both CLI phases", async (context) => {
  await context.test("preparation", async (subcontext) => {
    const input = await controlledFixture(subcontext);
    input.control.invalidProvenance = true;
    await assert.rejects(prepareRecovery(input), /signature is invalid/);
    assert.equal(
      (await commandLog(input)).some(({ command }) => command === "publish"),
      false,
    );
  });
  await context.test("publication", async (subcontext) => {
    const input = await controlledFixture(subcontext);
    await prepareRecovery(input);
    await writeFile(input.paths.commandLog, "");
    input.control.invalidProvenance = true;
    await assert.rejects(
      runCli(input, publishArguments(input.paths)),
      /signature is invalid/,
    );
    assert.equal(
      (await commandLog(input)).some(({ command }) => command === "publish"),
      false,
    );
  });
});

test("a recovery publication failure exits nonzero before SDK", async (context) => {
  const input = await controlledFixture(context);
  await prepareRecovery(input);
  await writeFile(input.paths.commandLog, "");
  await assert.rejects(
    runCli(input, publishArguments(input.paths), {
      FRED_RECOVERY_CLI_FAIL_PUBLISH: "ui",
    }),
    /publish command failed.*reconciliation confirmed.*stop before continuing/,
  );
  assert.deepEqual(
    (await commandLog(input))
      .filter(({ command }) => command === "publish")
      .map(({ role }) => role),
    ["ui"],
  );
});

test("the registry verifier CLI loads and enforces recovery evidence", async (context) => {
  const input = await controlledFixture(context);
  await prepareRecovery(input);
  const registryArguments = [
    registryVerifierPath,
    "--contract",
    input.paths.contract,
    "--evidence",
    path.join(input.paths.materialized, "candidate-evidence.json"),
    "--recovery-plan",
    input.paths.plan,
    "--recovery-evidence",
    input.paths.recoveryEvidence,
    "--design-tokens",
    input.evidence.packages.designTokens.coordinate,
    "--ui",
    input.evidence.packages.ui.coordinate,
    "--iframe-sdk",
    input.evidence.packages.iframeSdk.coordinate,
  ];
  await assert.rejects(
    runCli(input, registryArguments),
    /PLAYWRIGHT_BROWSERS_PATH is required/,
  );

  const invalidEvidencePath = path.join(input.root, "invalid-recovery.json");
  const invalidEvidence = JSON.parse(
    await readFile(input.paths.recoveryEvidence, "utf8"),
  );
  invalidEvidence.expectedProvenance.ui.sourceCommit = "d".repeat(40);
  await writeFile(
    invalidEvidencePath,
    `${JSON.stringify(invalidEvidence, null, 2)}\n`,
  );
  const invalidArguments = [...registryArguments];
  invalidArguments[invalidArguments.indexOf(input.paths.recoveryEvidence)] =
    invalidEvidencePath;
  await assert.rejects(
    runCli(input, invalidArguments),
    /recovery provenance expectations differ/,
  );
});
