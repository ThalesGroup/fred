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

import { packDesignTokens } from "./pack-design-tokens.mjs";
import { packUi } from "./pack-ui.mjs";
import { run } from "./process.mjs";
import { consumerCache } from "./provision-react-consumer.mjs";
import { validateArchive } from "./validate-archive.mjs";
import { validateUiArchive } from "./validate-ui-archive.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");
const fixtureRoot = path.join(workspaceRoot, "fixtures/react-consumer");

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

function offlineEnvironment(cachePath = consumerCache) {
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

export async function assertReactConsumerFixture(root = fixtureRoot) {
  const manifest = JSON.parse(
    await readFile(path.join(root, "package.json"), "utf8"),
  );
  assert.deepEqual(manifest.dependencies, {
    react: "19.2.4",
    "react-dom": "19.2.4",
  });
  assert.deepEqual(manifest.devDependencies, {
    "@types/react": "19.2.14",
    "@types/react-dom": "19.2.3",
    typescript: "5.9.3",
    vite: "6.4.3",
  });
  const lock = JSON.parse(
    await readFile(path.join(root, "package-lock.json"), "utf8"),
  );
  assert.deepEqual(
    lock.packages[""].dependencies,
    manifest.dependencies,
    "consumer runtime dependencies are not lockfile-pinned",
  );
  assert.deepEqual(
    lock.packages[""].devDependencies,
    manifest.devDependencies,
    "consumer tooling is not lockfile-pinned",
  );
  const source = await readFile(path.join(root, "src/main.tsx"), "utf8");
  for (const requiredImport of [
    '"@fred/design-tokens/tokens.css"',
    '"@fred/ui/styles.css"',
  ]) {
    assert(
      source.includes(requiredImport),
      `isolated consumer must explicitly import ${requiredImport}`,
    );
  }
  assert(
    !/(?:workspace|file|link):|apps\/frontend|libs\/frontend/.test(
      `${JSON.stringify(manifest)}\n${source}`,
    ),
    "consumer fixture contains a local/FRED fallback",
  );
}

async function listFiles(root, relative = "") {
  const files = [];
  for (const entry of await readdir(path.join(root, relative), {
    withFileTypes: true,
  })) {
    const entryPath = path.posix.join(relative, entry.name);
    if (entry.isDirectory()) files.push(...(await listFiles(root, entryPath)));
    else files.push(entryPath);
  }
  return files.sort();
}

export async function assertNoLinks(root, relative = "") {
  for (const entry of await readdir(path.join(root, relative), {
    withFileTypes: true,
  })) {
    const entryPath = path.join(relative, entry.name);
    assert.equal(
      (await lstat(path.join(root, entryPath))).isSymbolicLink(),
      false,
      `isolated package contains a link: ${entryPath}`,
    );
    if (entry.isDirectory()) await assertNoLinks(root, entryPath);
  }
}

export async function stageIsolatedReactConsumer({
  keep = false,
  evidencePath,
  stagedOutputPath,
  cachePath = consumerCache,
} = {}) {
  await assertReactConsumerFixture();
  await stat(path.join(cachePath, "_cacache")).catch(() => {
    throw new Error(
      `React consumer cache is missing at ${cachePath}; run npm run consumer:provision first`,
    );
  });
  const { archivePath: tokenArchive } = await packDesignTokens();
  await validateArchive(tokenArchive);
  const { archivePath: uiArchive } = await packUi();
  await validateUiArchive(uiArchive);
  const consumerRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-react-consumer-"),
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
    const originalLock = await readFile(
      path.join(fixtureRoot, "package-lock.json"),
    );
    const tokenTarget = path.join(consumerRoot, "design-tokens.tgz");
    const uiTarget = path.join(consumerRoot, "ui.tgz");
    await Promise.all([cp(tokenArchive, tokenTarget), cp(uiArchive, uiTarget)]);
    const env = offlineEnvironment(cachePath);
    let archiveResolution;
    let dependencyInstall;
    try {
      archiveResolution = await run(
        "npm",
        [
          "install",
          "--offline",
          "--ignore-scripts",
          "--no-audit",
          "--no-fund",
          "--legacy-peer-deps",
          "--package-lock-only",
          "./design-tokens.tgz",
          "./ui.tgz",
        ],
        { cwd: consumerRoot, env },
      );
      dependencyInstall = await run(
        "npm",
        [
          "ci",
          "--offline",
          "--include=dev",
          "--ignore-scripts",
          "--no-audit",
          "--no-fund",
        ],
        { cwd: consumerRoot, env },
      );
    } catch (error) {
      throw new Error(
        `Offline React consumer installation failed using ${cachePath}; the lockfile-pinned cache may be incomplete. Run npm run consumer:provision with network access, then retry offline validation.\n${error.message}`,
        { cause: error },
      );
    }
    const resolvedGraph = await run("npm", ["ls", "--depth=0", "--json"], {
      cwd: consumerRoot,
      env,
    });
    const parsedGraph = JSON.parse(resolvedGraph.stdout);
    for (const [dependency, version] of Object.entries({
      "@fred/design-tokens": "0.0.0-development",
      "@fred/ui": "0.0.0-development",
      react: "19.2.4",
      "react-dom": "19.2.4",
    }))
      assert.equal(
        parsedGraph.dependencies?.[dependency]?.version,
        version,
        `isolated consumer resolved unexpected ${dependency}`,
      );
    const installedEntries = await readdir(
      path.join(consumerRoot, "node_modules"),
      { recursive: true },
    );
    const runtimeInstallations = Object.fromEntries(
      ["react", "react-dom"].map((dependency) => [
        dependency,
        installedEntries
          .filter(
            (entry) =>
              entry === `${dependency}/package.json` ||
              entry.endsWith(`/node_modules/${dependency}/package.json`),
          )
          .sort(),
      ]),
    );
    assert.deepEqual(runtimeInstallations, {
      react: ["react/package.json"],
      "react-dom": ["react-dom/package.json"],
    });
    assert.deepEqual(
      await readFile(path.join(fixtureRoot, "package-lock.json")),
      originalLock,
      "offline validation changed the committed pinned lockfile",
    );
    await Promise.all([
      assertNoLinks(
        path.join(consumerRoot, "node_modules/@fred/design-tokens"),
      ),
      assertNoLinks(path.join(consumerRoot, "node_modules/@fred/ui")),
    ]);
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
    const outputFiles = await listFiles(outputRoot);
    const checkout = path.resolve(workspaceRoot, "../..");
    for (const file of outputFiles.filter((name) =>
      /\.(?:js|css|html)$/.test(name),
    )) {
      const content = await readFile(path.join(outputRoot, file), "utf8");
      assert(
        !content.includes(checkout) && !content.includes("apps/frontend"),
        `${file} refers to the FRED checkout`,
      );
    }
    const evidence = {
      cache: "dedicated lockfile-pinned cache",
      installMode:
        "temporary archive lock resolution plus npm ci, offline, no scripts",
      dependencyInstall: dependencyInstall.stdout.trim(),
      resolvedGraph: parsedGraph,
      runtimeInstallations,
      archiveResolution: archiveResolution.stdout.trim(),
      typecheck: typecheck.stdout.trim(),
      build: build.stdout.trim(),
      outputFiles,
      packageLinks: 0,
      checkoutReferences: 0,
    };
    if (evidencePath) {
      const resolved = path.resolve(workspaceRoot, evidencePath);
      await mkdir(path.dirname(resolved), { recursive: true });
      await writeFile(resolved, `${JSON.stringify(evidence, null, 2)}\n`);
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
      cleanup: () => rm(consumerRoot, { recursive: true, force: true }),
    };
  } catch (error) {
    if (!keep) await rm(consumerRoot, { recursive: true, force: true });
    else
      process.stderr.write(
        `retained failed isolated consumer at ${consumerRoot}\n`,
      );
    throw error;
  } finally {
    if (!keep) await rm(consumerRoot, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await stageIsolatedReactConsumer({
    keep: process.argv.includes("--keep"),
    evidencePath: optionValue("--evidence"),
    stagedOutputPath: "target/staged-consumers/react",
  });
  process.stdout.write(`${JSON.stringify(result.evidence, null, 2)}\n`);
}
