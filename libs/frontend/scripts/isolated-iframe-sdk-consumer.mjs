import assert from "node:assert/strict";
import { fileURLToPath } from "node:url";
import {
  cp,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  stat,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { parameterizeConsumerSources } from "./consumer-contract.mjs";
import { installAfterOfflineReferenceValidation } from "./dependency-boundaries.mjs";
import { packIframeSdk } from "./pack-iframe-sdk.mjs";
import { run } from "./process.mjs";
import { iframeSdkConsumerCache } from "./provision-iframe-sdk-consumer.mjs";
import { loadReleaseContract } from "./release-contract.mjs";
import { sha512Integrity } from "./release-evidence.mjs";
import { validateIframeSdkArchive } from "./validate-iframe-sdk-archive.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");
const fixtureRoot = path.join(workspaceRoot, "fixtures/iframe-sdk-consumer");

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function offlineEnvironment(cachePath) {
  const environment = { ...process.env };
  for (const key of Object.keys(environment)) {
    if (
      /^npm_(?:package|workspace)/i.test(key) ||
      ["INIT_CWD", "NODE_PATH"].includes(key)
    )
      delete environment[key];
  }
  return {
    ...environment,
    npm_config_cache: cachePath,
    npm_config_offline: "true",
    npm_config_audit: "false",
    npm_config_fund: "false",
  };
}

async function assertNoLinks(root, relative = "") {
  for (const entry of await readdir(path.join(root, relative), {
    withFileTypes: true,
  })) {
    const entryPath = path.join(relative, entry.name);
    assert.equal(
      (await lstat(path.join(root, entryPath))).isSymbolicLink(),
      false,
      `isolated SDK contains a link: ${entryPath}`,
    );
    if (entry.isDirectory()) await assertNoLinks(root, entryPath);
  }
}

export async function assertIframeSdkConsumerFixture(root = fixtureRoot) {
  const manifest = JSON.parse(
    await readFile(path.join(root, "package.json"), "utf8"),
  );
  assert.equal(manifest.dependencies, undefined);
  assert.deepEqual(manifest.devDependencies, {
    typescript: "5.9.3",
    vite: "6.4.3",
  });
  const lock = JSON.parse(
    await readFile(path.join(root, "package-lock.json"), "utf8"),
  );
  assert.deepEqual(lock.packages[""].devDependencies, manifest.devDependencies);
  const source = await Promise.all(
    [
      "src/host.ts",
      "src/child.ts",
      "src/fixture-origin.ts",
      "src/readonly-declarations.ts",
    ].map((file) => readFile(path.join(root, file), "utf8")),
  );
  assert(source[0].includes('"@fred/iframe-sdk/protocol"'));
  assert(source[1].includes('"@fred/iframe-sdk"'));
  assert(source[3].includes("readonly-context-typecheck-only"));
  assert(source[3].includes("readonly-route-typecheck-only"));
  assert.equal((source[3].match(/@ts-expect-error/g) ?? []).length, 2);
  assert(
    !/(?:workspace|file|link):|apps\/frontend|libs\/frontend|\breact\b/i.test(
      `${JSON.stringify(manifest)}\n${source.join("\n")}`,
    ),
  );
}

export async function stageIsolatedIframeSdkConsumer({
  keep = false,
  evidencePath,
  stagedOutputPath,
  cachePath = iframeSdkConsumerCache,
  contract: selectedContract,
  archivePath: suppliedArchive,
  expectedIntegrity,
} = {}) {
  const contract = selectedContract ?? (await loadReleaseContract());
  await assertIframeSdkConsumerFixture();
  await stat(path.join(cachePath, "_cacache")).catch(() => {
    throw new Error(
      `iframe SDK consumer cache is missing at ${cachePath}; run npm run consumer:provision:iframe-sdk first`,
    );
  });
  const archivePath =
    suppliedArchive ?? (await packIframeSdk({ contract })).archivePath;
  await validateIframeSdkArchive(archivePath, { contract });
  if (expectedIntegrity)
    assert.equal(
      await sha512Integrity(archivePath),
      expectedIntegrity,
      "iframe SDK candidate integrity differs",
    );
  const consumerRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-iframe-sdk-consumer-"),
  );
  assert(
    path.relative(workspaceRoot, consumerRoot).startsWith(".."),
    "consumer must be outside FRED",
  );
  try {
    await cp(fixtureRoot, consumerRoot, {
      recursive: true,
      filter: (source) => !source.includes("node_modules"),
    });
    await parameterizeConsumerSources(consumerRoot, contract, ["iframeSdk"]);
    const originalLock = await readFile(
      path.join(fixtureRoot, "package-lock.json"),
    );
    const archiveTarget = path.join(consumerRoot, "iframe-sdk.tgz");
    await cp(archivePath, archiveTarget);
    const candidateEvidence = {
      packages: {
        iframeSdk: {
          coordinate: `${contract.packages.iframeSdk.name}@${contract.packages.iframeSdk.version}`,
          filename: path.basename(archiveTarget),
          integrity: await sha512Integrity(archiveTarget),
        },
      },
    };
    const env = offlineEnvironment(cachePath);
    try {
      await run(
        "npm",
        [
          "install",
          "--offline",
          "--ignore-scripts",
          "--no-audit",
          "--no-fund",
          "--package-lock-only",
          "./iframe-sdk.tgz",
        ],
        { cwd: consumerRoot, env },
      );
      await installAfterOfflineReferenceValidation({
        manifest: JSON.parse(
          await readFile(path.join(consumerRoot, "package.json"), "utf8"),
        ),
        lockfile: JSON.parse(
          await readFile(path.join(consumerRoot, "package-lock.json"), "utf8"),
        ),
        consumerRoot,
        evidence: candidateEvidence,
        installDependencies: () =>
          run(
            "npm",
            [
              "ci",
              "--offline",
              "--include=dev",
              "--ignore-scripts",
              "--no-audit",
              "--no-fund",
            ],
            {
              cwd: consumerRoot,
              env,
            },
          ),
      });
    } catch (error) {
      throw new Error(
        `Offline iframe SDK consumer installation failed using ${cachePath}. Run npm run consumer:provision:iframe-sdk with network access, then retry.\n${error.message}`,
        { cause: error },
      );
    }
    assert.deepEqual(
      await readFile(path.join(fixtureRoot, "package-lock.json")),
      originalLock,
      "offline validation changed the pinned lockfile",
    );
    const graph = JSON.parse(
      (
        await run("npm", ["ls", "--depth=0", "--json", "--include=dev"], {
          cwd: consumerRoot,
          env,
        })
      ).stdout,
    );
    assert.equal(
      graph.dependencies?.[contract.packages.iframeSdk.name]?.version,
      contract.packages.iframeSdk.version,
    );
    assert(
      !Object.keys(graph.dependencies ?? {}).some(
        (name) =>
          name === "react" ||
          (name.startsWith("@fred/") &&
            name !== contract.packages.iframeSdk.name),
      ),
    );
    await assertNoLinks(
      path.join(consumerRoot, "node_modules", contract.packages.iframeSdk.name),
    );
    const typecheck = await run(
      path.join(consumerRoot, "node_modules/.bin/tsc"),
      ["--noEmit"],
      { cwd: consumerRoot, env },
    );
    const build = await run(
      path.join(consumerRoot, "node_modules/.bin/vite"),
      ["build"],
      { cwd: consumerRoot, env },
    );
    const outputRoot = path.join(consumerRoot, "dist");
    const outputs = await readdir(outputRoot, { recursive: true });
    const checkout = path.resolve(workspaceRoot, "../..");
    for (const file of outputs.filter((name) => /\.(?:js|html)$/.test(name))) {
      const content = await readFile(path.join(outputRoot, file), "utf8");
      assert(
        !content.includes(checkout) && !content.includes("apps/frontend"),
        `${file} refers to the FRED checkout`,
      );
      assert(
        !content.includes("readonly-context-typecheck-only") &&
          !content.includes("readonly-route-typecheck-only"),
        `${file} includes typecheck-only declaration assertions`,
      );
    }
    const stagedOutput = path.resolve(
      stagedOutputPath ??
        path.join(workspaceRoot, "target/staged-consumers/iframe-sdk"),
    );
    await rm(stagedOutput, { recursive: true, force: true });
    await mkdir(path.dirname(stagedOutput), { recursive: true });
    await cp(outputRoot, stagedOutput, { recursive: true });
    const evidence = {
      archive: path.basename(archivePath),
      cache: cachePath,
      consumerRoot,
      dependencyGraph: Object.fromEntries(
        Object.entries(graph.dependencies ?? {}).map(([name, value]) => [
          name,
          value.version,
        ]),
      ),
      network: "npm offline mode",
      outputFiles: outputs.sort(),
      stagedOutput,
      typecheck: typecheck.stderr,
      build: build.stderr,
    };
    if (evidencePath) {
      const resolved = path.resolve(workspaceRoot, evidencePath);
      await mkdir(path.dirname(resolved), { recursive: true });
      await writeFile(resolved, `${JSON.stringify(evidence, null, 2)}\n`);
    }
    return evidence;
  } finally {
    if (!keep) await rm(consumerRoot, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(
      await stageIsolatedIframeSdkConsumer({
        keep: process.argv.includes("--keep"),
        evidencePath: optionValue("--evidence"),
        stagedOutputPath: optionValue("--stage"),
        contract: await loadReleaseContract(optionValue("--contract")),
      }),
      null,
      2,
    )}\n`,
  );
}
