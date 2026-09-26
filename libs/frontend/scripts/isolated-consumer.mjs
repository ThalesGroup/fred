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
import { fileURLToPath } from "node:url";
import {
  cp,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  readdir,
  rm,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";

import { packDesignTokens, workspaceRoot } from "./pack-design-tokens.mjs";
import { run } from "./process.mjs";
import { parameterizeConsumerSources } from "./consumer-contract.mjs";
import { sha512Integrity } from "./release-evidence.mjs";
import { loadReleaseContract } from "./release-contract.mjs";
import { validateArchive } from "./validate-archive.mjs";
import { loadCompatibilityLedger } from "./compatibility-baselines.mjs";
import { assertCompatibleTokenProvision } from "./provision-compatible-token.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const fixtureRoot = path.resolve(
  scriptDirectory,
  "../fixtures/neutral-consumer",
);

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function isolatedEnvironment(consumerRoot) {
  const environment = { ...process.env };
  for (const key of Object.keys(environment)) {
    if (
      /^npm_(?:package|workspace)/i.test(key) ||
      ["INIT_CWD", "NODE_PATH"].includes(key)
    ) {
      delete environment[key];
    }
  }
  return {
    ...environment,
    npm_config_cache: path.join(consumerRoot, ".npm-cache"),
    npm_config_offline: "true",
    npm_config_audit: "false",
    npm_config_fund: "false",
  };
}

async function listFiles(root, relativeDirectory = "") {
  const entries = await readdir(path.join(root, relativeDirectory), {
    withFileTypes: true,
  });
  const files = [];
  for (const entry of entries) {
    const relativePath = path.posix.join(relativeDirectory, entry.name);
    if (entry.isDirectory()) {
      files.push(...(await listFiles(root, relativePath)));
    } else {
      files.push(relativePath);
    }
  }
  return files.sort();
}

async function assertNoLinks(root, relativeDirectory = "") {
  const entries = await readdir(path.join(root, relativeDirectory), {
    withFileTypes: true,
  });
  for (const entry of entries) {
    const relativePath = path.join(relativeDirectory, entry.name);
    const stat = await lstat(path.join(root, relativePath));
    assert(
      !stat.isSymbolicLink(),
      `isolated consumer contains a link: ${relativePath}`,
    );
    if (entry.isDirectory()) {
      await assertNoLinks(root, relativePath);
    }
  }
}

export async function stageIsolatedConsumer({
  keep = false,
  evidencePath,
  stagedOutputPath,
  contract: selectedContract,
  archivePath: suppliedArchive,
  expectedIntegrity,
  compatibleToken,
} = {}) {
  const contract = selectedContract ?? (await loadReleaseContract());
  if (compatibleToken) {
    const prepared = await assertCompatibleTokenProvision({
      contract,
      ledger: await loadCompatibilityLedger(),
      outputRoot: compatibleToken.outputRoot,
    });
    assert.equal(
      prepared.archivePath,
      compatibleToken.archivePath,
      "neutral consumer token archive differs from prepared baseline",
    );
    assert.equal(
      prepared.receipt.coordinate,
      compatibleToken.coordinate,
      "neutral consumer token coordinate differs from prepared baseline",
    );
    assert.equal(
      prepared.receipt.integrity,
      compatibleToken.integrity,
      "neutral consumer token integrity differs from prepared baseline",
    );
    if (suppliedArchive)
      assert.equal(
        suppliedArchive,
        prepared.archivePath,
        "neutral consumer supplied archive differs from prepared baseline",
      );
  }
  const archivePath =
    compatibleToken?.archivePath ??
    suppliedArchive ??
    (await packDesignTokens({ contract })).archivePath;
  // Compatibility bytes are a separately approved historical release, not a
  // new candidate to compare against today's canonical FRED token sources.
  if (!compatibleToken) await validateArchive(archivePath, { contract });
  if (expectedIntegrity)
    assert.equal(
      await sha512Integrity(archivePath),
      expectedIntegrity,
      "design-token candidate integrity differs",
    );
  const consumerRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-neutral-consumer-"),
  );
  const relativeToWorkspace = path.relative(workspaceRoot, consumerRoot);
  assert(
    relativeToWorkspace.startsWith("..") &&
      !path.isAbsolute(relativeToWorkspace),
    "consumer must be outside the FRED workspace",
  );
  try {
    await cp(fixtureRoot, consumerRoot, { recursive: true });
    await parameterizeConsumerSources(consumerRoot, contract, ["designTokens"]);
    const originalManifest = await readFile(
      path.join(consumerRoot, "package.json"),
      "utf8",
    );
    const stagedArchive = path.join(consumerRoot, "design-tokens.tgz");
    await cp(archivePath, stagedArchive);
    const environment = isolatedEnvironment(consumerRoot);
    const install = await run(
      "npm",
      [
        "install",
        "--offline",
        "--ignore-scripts",
        "--no-audit",
        "--no-fund",
        "--no-save",
        "--package-lock=false",
        "./design-tokens.tgz",
      ],
      { cwd: consumerRoot, env: environment },
    );
    assert.equal(
      await readFile(path.join(consumerRoot, "package.json"), "utf8"),
      originalManifest,
      "offline install must not add a local-file dependency",
    );
    await assertNoLinks(
      path.join(
        consumerRoot,
        "node_modules",
        contract.packages.designTokens.name,
      ),
    );
    const build = await run("node", ["build.mjs"], {
      cwd: consumerRoot,
      env: environment,
    });
    const outputRoot = path.join(consumerRoot, "dist");
    const outputFiles = await listFiles(outputRoot);
    assert.deepEqual(outputFiles, [
      "fonts.css",
      "fonts.html",
      "fonts/Geist-Italic.woff2",
      "fonts/Geist.woff2",
      "tokens-only.html",
      "tokens.css",
    ]);
    const checkoutPath = path.resolve(workspaceRoot, "../..");
    for (const relativePath of outputFiles.filter((file) =>
      /\.(?:css|html)$/.test(file),
    )) {
      const content = await readFile(
        path.join(outputRoot, relativePath),
        "utf8",
      );
      assert(
        !content.includes(checkoutPath),
        `${relativePath} contains the FRED checkout path`,
      );
      assert(
        !content.includes("apps/frontend"),
        `${relativePath} contains a canonical source path`,
      );
    }
    assert.match(
      await readFile(path.join(outputRoot, "tokens.css"), "utf8"),
      /data-theme="light"/,
    );
    assert.match(
      await readFile(path.join(outputRoot, "tokens.css"), "utf8"),
      /data-theme="dark"/,
    );
    assert.match(
      await readFile(path.join(outputRoot, "fonts.css"), "utf8"),
      /\.\/fonts\/Geist\.woff2/,
    );

    const evidence = {
      archive: path.basename(archivePath),
      installMode: "offline tarball, no save, no lock, no scripts",
      installOutput: install.stdout.trim(),
      buildOutput: build.stdout.trim(),
      packageIsLinked: false,
      outputFiles,
      sourceCheckoutReferences: 0,
    };
    if (evidencePath) {
      const resolvedEvidence = path.resolve(workspaceRoot, evidencePath);
      await mkdir(path.dirname(resolvedEvidence), { recursive: true });
      await writeFile(
        resolvedEvidence,
        `${JSON.stringify(evidence, null, 2)}\n`,
      );
    }
    if (stagedOutputPath) {
      const resolvedOutput = path.resolve(workspaceRoot, stagedOutputPath);
      await rm(resolvedOutput, { recursive: true, force: true });
      await mkdir(path.dirname(resolvedOutput), { recursive: true });
      await cp(outputRoot, resolvedOutput, { recursive: true });
    }
    return {
      consumerRoot,
      outputRoot,
      evidence,
      cleanup: () => rm(consumerRoot, { recursive: true }),
    };
  } catch (error) {
    await rm(consumerRoot, { recursive: true, force: true });
    throw error;
  } finally {
    if (!keep) {
      await rm(consumerRoot, { recursive: true, force: true });
    }
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const contract = await loadReleaseContract(optionValue("--contract"));
  const prepared = process.argv.includes("--compatible-token")
    ? await assertCompatibleTokenProvision({
        contract,
        ledger: await loadCompatibilityLedger(),
      })
    : undefined;
  const result = await stageIsolatedConsumer({
    evidencePath: optionValue("--evidence"),
    stagedOutputPath: "target/staged-consumers/tokens",
    contract,
    archivePath: prepared?.archivePath,
    expectedIntegrity: prepared?.receipt.integrity,
    compatibleToken: prepared
      ? {
          archivePath: prepared.archivePath,
          coordinate: prepared.receipt.coordinate,
          integrity: prepared.receipt.integrity,
        }
      : undefined,
  });
  process.stdout.write(`${JSON.stringify(result.evidence, null, 2)}\n`);
}
