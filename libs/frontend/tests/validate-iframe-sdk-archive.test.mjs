import assert from "node:assert/strict";
import {
  mkdir,
  mkdtemp,
  readFile,
  rm,
  symlink,
  writeFile,
} from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import { pathToFileURL } from "node:url";
import test from "node:test";

import { packIframeSdk } from "../scripts/pack-iframe-sdk.mjs";
import { run } from "../scripts/process.mjs";
import {
  assertRuntimeReferences,
  validateIframeSdkArchive,
} from "../scripts/validate-iframe-sdk-archive.mjs";

async function mutateArchive(sourceArchive, context, mutate) {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-invalid-iframe-sdk-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await run("tar", ["-xzf", sourceArchive, "-C", temporary]);
  await mutate(path.join(temporary, "package"));
  const archive = path.join(temporary, "invalid.tgz");
  await run("tar", ["-czf", archive, "-C", temporary, "package"]);
  return archive;
}

async function editJson(filePath, edit) {
  const value = JSON.parse(await readFile(filePath, "utf8"));
  edit(value);
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

const { archivePath } = await packIframeSdk();

test("accepts the actual packed iframe SDK with runtime and declaration closure", async () => {
  const evidence = await validateIframeSdkArchive(archivePath);
  assert.equal(evidence.package, "@fred/iframe-sdk@0.0.0-development");
  assert.deepEqual(evidence.runtimeModules, [
    "dist/index.js",
    "dist/protocol.js",
  ]);
  assert.deepEqual(evidence.declarations, [
    "dist/types/.generated/applicationProtocol.d.ts",
    "dist/types/src/index.d.ts",
  ]);
});

test("loads the actual packed root entry with native ESM", async (context) => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-native-sdk-"));
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await run("tar", ["-xzf", archivePath, "-C", temporary]);
  const loaded = await import(
    `${pathToFileURL(path.join(temporary, "package/dist/index.js")).href}?native-esm`
  );
  assert.equal(typeof loaded.createFredApplicationClient, "function");
});

for (const file of [
  "dist/index.js",
  "dist/protocol.js",
  "dist/types/src/index.d.ts",
  "dist/types/.generated/applicationProtocol.d.ts",
  "LICENSE",
  "README.md",
  "build-evidence.json",
]) {
  test(`rejects missing ${file}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, (root) =>
      rm(path.join(root, file)),
    );
    await assert.rejects(
      validateIframeSdkArchive(archive),
      /packed inventory differs/,
    );
  });
}

test("rejects unexpected files and links", async (context) => {
  let archive = await mutateArchive(archivePath, context, (root) =>
    writeFile(path.join(root, "source.ts"), "export {};\n"),
  );
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /packed inventory differs/,
  );
  archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/index.js");
    await rm(file);
    await symlink("../protocol.js", file);
  });
  await assert.rejects(validateIframeSdkArchive(archive), /link/);
});

for (const [field, value] of [
  ["name", "@fred/not-the-sdk"],
  ["version", "1.0.0"],
  ["description", "unreviewed package"],
  ["license", "UNLICENSED"],
]) {
  test(`rejects wrong manifest ${field}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, (root) =>
      editJson(path.join(root, "package.json"), (manifest) => {
        manifest[field] = value;
      }),
    );
    await assert.rejects(validateIframeSdkArchive(archive), /strictly equal/);
  });
}

test("accepts executable runtime and declaration-only resolution on their proper paths", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const runtime = path.join(root, "dist/index.js");
    await writeFile(
      runtime,
      `import "./protocol.js";\n${await readFile(runtime, "utf8")}`,
    );
  });
  await assert.doesNotReject(validateIframeSdkArchive(archive));
});

for (const [name, source, pattern] of [
  [
    "a commented static runtime import",
    'import /* comment */ "./missing-runtime.js";',
    /runtime reference .*missing-runtime\.js without an executable packed module/,
  ],
  [
    "a literal-template dynamic runtime import",
    "export const loadMissing = () => import(`./missing-runtime.js`);",
    /runtime reference .*missing-runtime\.js without an executable packed module/,
  ],
  [
    "a computed dynamic runtime import",
    "export const loadComputed = (name) => import(name);",
    /non-literal dynamic import reference/,
  ],
  ["malformed runtime module syntax", "import {", /malformed module syntax/],
  [
    "a top-level return accepted by the TypeScript parser",
    "return;",
    /invalid native ESM syntax/,
  ],
  [
    "TypeScript-only syntax in runtime JavaScript",
    "const typed: number = 1;",
    /invalid native ESM syntax/,
  ],
]) {
  test(`rejects ${name}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const runtime = path.join(root, "dist/index.js");
      await writeFile(runtime, `${source}\n${await readFile(runtime, "utf8")}`);
    });
    await assert.rejects(validateIframeSdkArchive(archive), pattern);
  });
}

test("rejects a commented declaration import type without a target", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    await writeFile(
      path.join(root, "dist/types/src/index.d.ts"),
      'export type Missing = import /* comment */ ("./missing-types.js").Missing;\n',
    );
  });
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /unresolved declaration reference .*missing-types\.js/,
  );
});

test("rejects an extensionless runtime reference that native ESM cannot load", async (context) => {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-native-esm-"));
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await writeFile(path.join(temporary, "package.json"), '{"type":"module"}\n');
  await writeFile(path.join(temporary, "protocol.js"), "export {};\n");
  await writeFile(path.join(temporary, "index.js"), 'import "./protocol";\n');
  await assert.rejects(
    import(pathToFileURL(path.join(temporary, "index.js")).href),
  );

  const archive = await mutateArchive(archivePath, context, async (root) => {
    const runtime = path.join(root, "dist/index.js");
    await writeFile(
      runtime,
      `import "./protocol";\n${await readFile(runtime, "utf8")}`,
    );
  });
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /runtime reference .*protocol without an executable packed module/,
  );
});

test("rejects a runtime directory resolved only through index fallback", async (context) => {
  const temporary = await mkdtemp(
    path.join(os.tmpdir(), "fred-runtime-directory-"),
  );
  context.after(() => rm(temporary, { recursive: true, force: true }));
  await writeFile(path.join(temporary, "index.js"), 'import "./runtime";\n');
  await mkdir(path.join(temporary, "runtime"));
  await writeFile(path.join(temporary, "runtime/index.js"), "export {};\n");
  await assert.rejects(
    assertRuntimeReferences(temporary, "index.js"),
    /runtime reference .*runtime without an executable packed module/,
  );
});

test("rejects a runtime import resolved only by a declaration", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const runtime = path.join(root, "dist/index.js");
    await writeFile(
      runtime,
      `import "./types/src/index";\n${await readFile(runtime, "utf8")}`,
    );
  });
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /without an executable packed module/,
  );
});

test("rejects a runtime export condition resolved only by a declaration", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    editJson(path.join(root, "package.json"), (manifest) => {
      manifest.exports["."].import = "./dist/types/src/index.d.ts";
    }),
  );
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /runtime export has no executable packed module|deep-equal/,
  );
});

test("rejects a declaration reference without a packed declaration target", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const declaration = path.join(root, "dist/types/src/index.d.ts");
    await writeFile(
      declaration,
      `export type Missing = import("../../../protocol.js").Missing;\n`,
    );
  });
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /without a packed \.d\.ts target/,
  );
});

test("rejects a types export resolved only by executable JavaScript", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    editJson(path.join(root, "package.json"), (manifest) => {
      manifest.exports["."].types = "./dist/index.js";
    }),
  );
  await assert.rejects(
    validateIframeSdkArchive(archive),
    /types export has no packed \.d\.ts target|deep-equal/,
  );
});

for (const [name, mutate, pattern] of [
  [
    "an escaping export",
    (manifest) => (manifest.exports["."].import = "../outside.js"),
    /deep-equal|escaping|package-relative/,
  ],
  [
    "a local dependency",
    (manifest) => (manifest.dependencies = { local: "workspace:*" }),
    /no dependency entries/,
  ],
  [
    "a framework dependency",
    (manifest) => (manifest.peerDependencies = { react: "*" }),
    /no dependency entries/,
  ],
]) {
  test(`rejects ${name}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, (root) =>
      editJson(path.join(root, "package.json"), mutate),
    );
    await assert.rejects(validateIframeSdkArchive(archive), pattern);
  });
}

for (const file of ["LICENSE", "build-evidence.json"]) {
  test(`rejects modified ${file}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const target = path.join(root, file);
      await writeFile(target, `${await readFile(target, "utf8")}modified\n`);
    });
    await assert.rejects(
      validateIframeSdkArchive(archive),
      /license differs|deep-equal|canonicalProtocol|Unexpected/,
    );
  });
}

for (const forbidden of [
  "apps/frontend/source.ts",
  "/Users/example/fred",
  "@fred/ui",
  "node:fs",
  "RAGS",
]) {
  test(`rejects forbidden archive content ${forbidden}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const runtime = path.join(root, "dist/index.js");
      await writeFile(
        runtime,
        `${await readFile(runtime, "utf8")}\n/* ${forbidden} */\n`,
      );
    });
    await assert.rejects(
      validateIframeSdkArchive(archive),
      /forbidden|consumer-specific/,
    );
  });
}
