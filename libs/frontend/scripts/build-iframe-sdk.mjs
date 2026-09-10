import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { fileURLToPath } from "node:url";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

import { build } from "vite";

import {
  IFRAME_SDK_CANONICAL_SOURCE_PATH,
  IFRAME_SDK_SOURCE_PATHS,
  ROOT_LICENSE_PATH,
} from "./package-inputs.mjs";
import { inspectModuleReferences } from "./module-references.mjs";
import { run } from "./process.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const repositoryRoot = path.resolve(scriptDirectory, "../../..");
export const packageRoot = path.resolve(scriptDirectory, "../iframe-sdk");
const generatedRoot = path.join(packageRoot, ".generated");
const distributionRoot = path.join(packageRoot, "dist");

function sha256(content) {
  return createHash("sha256").update(content).digest("hex");
}

function evidencePlugin(evidence, entry) {
  return {
    name: `fred-iframe-sdk-${entry}-evidence`,
    generateBundle(_options, bundle) {
      evidence.builds[entry] = {
        modules: [...this.getModuleIds()]
          .map((id) =>
            (path.isAbsolute(id) ? path.relative(repositoryRoot, id) : id)
              .split(path.sep)
              .join("/"),
          )
          .sort(),
        outputs: Object.keys(bundle).sort(),
      };
    },
  };
}

async function buildEntry(name, entry, evidence, emptyOutDir) {
  await build({
    configFile: false,
    root: packageRoot,
    plugins: [evidencePlugin(evidence, name)],
    build: {
      emptyOutDir,
      lib: { entry, formats: ["es"], fileName: () => `${name}.js` },
      rollupOptions: { external: () => false },
      target: "es2022",
    },
  });
}

export function assertIframeSdkBuildSourceGraph(evidence) {
  assert.deepEqual(evidence.sourceAllowlist, IFRAME_SDK_SOURCE_PATHS);
  assert.deepEqual(evidence.builds.index.modules, [
    "libs/frontend/iframe-sdk/.generated/applicationProtocol.ts",
    "libs/frontend/iframe-sdk/src/index.ts",
  ]);
  assert.deepEqual(evidence.builds.protocol.modules, [
    "libs/frontend/iframe-sdk/.generated/applicationProtocol.ts",
  ]);
  assert.deepEqual(evidence.builds.index.outputs, ["index.js"]);
  assert.deepEqual(evidence.builds.protocol.outputs, ["protocol.js"]);
}

export async function buildIframeSdk() {
  await Promise.all([
    rm(generatedRoot, { recursive: true, force: true }),
    rm(distributionRoot, { recursive: true, force: true }),
    rm(path.join(packageRoot, "LICENSE"), { force: true }),
    rm(path.join(packageRoot, "build-evidence.json"), { force: true }),
  ]);
  await mkdir(generatedRoot, { recursive: true });
  const canonicalSource = await readFile(
    path.join(repositoryRoot, IFRAME_SDK_CANONICAL_SOURCE_PATH),
  );
  await writeFile(
    path.join(generatedRoot, "applicationProtocol.ts"),
    canonicalSource,
  );

  const evidence = {
    sourceAllowlist: IFRAME_SDK_SOURCE_PATHS,
    canonicalProtocol: {
      path: IFRAME_SDK_CANONICAL_SOURCE_PATH,
      sha256: sha256(canonicalSource),
    },
    externals: [],
    builds: {},
  };
  await buildEntry(
    "index",
    path.join(packageRoot, "src/index.ts"),
    evidence,
    true,
  );
  await buildEntry(
    "protocol",
    path.join(generatedRoot, "applicationProtocol.ts"),
    evidence,
    false,
  );
  assertIframeSdkBuildSourceGraph(evidence);
  await run("npm", ["exec", "--", "tsc", "-p", "iframe-sdk/tsconfig.json"], {
    cwd: path.dirname(packageRoot),
  });
  await copyFile(
    path.join(repositoryRoot, ROOT_LICENSE_PATH),
    path.join(packageRoot, "LICENSE"),
  );
  evidence.licenseSha256 = sha256(
    await readFile(path.join(packageRoot, "LICENSE")),
  );
  evidence.runtimeImports = Object.fromEntries(
    await Promise.all(
      ["index.js", "protocol.js"].map(async (file) => [
        file,
        inspectModuleReferences(
          await readFile(path.join(distributionRoot, file), "utf8"),
          { fileName: file, mode: "runtime" },
        ).map(({ specifier }) => specifier),
      ]),
    ),
  );
  await writeFile(
    path.join(packageRoot, "build-evidence.json"),
    `${JSON.stringify(evidence, null, 2)}\n`,
  );
  return evidence;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(`${JSON.stringify(await buildIframeSdk(), null, 2)}\n`);
}
