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
import { validateArchive } from "./validate-archive.mjs";

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
} = {}) {
  const { archivePath } = await packDesignTokens();
  await validateArchive(archivePath);
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
      await readFile(path.join(fixtureRoot, "package.json"), "utf8"),
      "offline install must not add a local-file dependency",
    );
    await assertNoLinks(
      path.join(consumerRoot, "node_modules/@fred/design-tokens"),
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
  const result = await stageIsolatedConsumer({
    evidencePath: optionValue("--evidence"),
  });
  process.stdout.write(`${JSON.stringify(result.evidence, null, 2)}\n`);
}
