import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { packDesignTokens } from "../scripts/pack-design-tokens.mjs";
import { run } from "../scripts/process.mjs";
import { validateArchive } from "../scripts/validate-archive.mjs";

async function mutateArchive(sourceArchive, context, mutate) {
  const temporaryRoot = await mkdtemp(
    path.join(os.tmpdir(), "fred-invalid-archive-"),
  );
  context.after(() => rm(temporaryRoot, { recursive: true, force: true }));
  await run("tar", ["-xzf", sourceArchive, "-C", temporaryRoot]);
  await mutate(path.join(temporaryRoot, "package"));
  const archive = path.join(temporaryRoot, "invalid.tgz");
  await run("tar", ["-czf", archive, "-C", temporaryRoot, "package"]);
  return archive;
}

async function editJson(filePath, edit) {
  const value = JSON.parse(await readFile(filePath, "utf8"));
  edit(value);
  await writeFile(filePath, `${JSON.stringify(value, null, 2)}\n`);
}

const { archivePath } = await packDesignTokens();

test("accepts the actual packed design-token archive", async () => {
  const result = await validateArchive(archivePath);
  assert.equal(result.package, "@fred/design-tokens@0.0.0-development");
  assert.equal(result.files.length, 9);
  assert.deepEqual(result.cssAssets["dist/tokens.css"], []);
});

for (const assetKind of ["font", "image", "icon"]) {
  test(`rejects a missing ${assetKind} referenced by CSS`, async (context) => {
    const archive = await mutateArchive(
      archivePath,
      context,
      async (packageRoot) => {
        const cssPath = path.join(packageRoot, "dist/tokens.css");
        await writeFile(
          cssPath,
          `${await readFile(cssPath, "utf8")}\n.missing { src: url("./missing.${assetKind}"); }\n`,
        );
      },
    );
    await assert.rejects(
      () => validateArchive(archive),
      new RegExp(`missing\\.${assetKind}`),
    );
  });
}

test("rejects an export that escapes the package", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await editJson(path.join(packageRoot, "package.json"), (manifest) => {
        manifest.exports["./tokens.css"] = "../tokens.css";
      });
    },
  );
  await assert.rejects(() => validateArchive(archive), /escapes the package/);
});

test("rejects an absent export target", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await editJson(path.join(packageRoot, "package.json"), (manifest) => {
        manifest.exports["./tokens.css"] = "./dist/absent.css";
      });
    },
  );
  await assert.rejects(() => validateArchive(archive), /is absent/);
});

test("rejects an unexpected packed file", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await writeFile(path.join(packageRoot, "unexpected.txt"), "not public\n");
    },
  );
  await assert.rejects(
    () => validateArchive(archive),
    /packed inventory differs/,
  );
});

test("rejects an absent notice file", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await rm(path.join(packageRoot, "THIRD_PARTY_NOTICES.md"));
    },
  );
  await assert.rejects(
    () => validateArchive(archive),
    /packed inventory differs/,
  );
});

test("rejects an incomplete Geist notice", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await writeFile(
        path.join(packageRoot, "THIRD_PARTY_NOTICES.md"),
        "# Third-party notices\n",
      );
    },
  );
  await assert.rejects(() => validateArchive(archive), /notice omits/);
});

test("rejects a runtime dependency", async (context) => {
  const archive = await mutateArchive(
    archivePath,
    context,
    async (packageRoot) => {
      await editJson(path.join(packageRoot, "package.json"), (manifest) => {
        manifest.dependencies = { example: "1.0.0" };
      });
    },
  );
  await assert.rejects(
    () => validateArchive(archive),
    /must not declare runtime dependencies/,
  );
});

for (const forbidden of [
  "@shared/token",
  "apps/frontend/src/styles/index.css",
  "/tmp/fred-frontend-packaging/source.css",
]) {
  test(`rejects generated source reference ${forbidden}`, async (context) => {
    const archive = await mutateArchive(
      archivePath,
      context,
      async (packageRoot) => {
        const cssPath = path.join(packageRoot, "dist/tokens.css");
        await writeFile(
          cssPath,
          `${await readFile(cssPath, "utf8")}\n/* ${forbidden} */\n`,
        );
      },
    );
    await assert.rejects(
      () => validateArchive(archive),
      /source alias|source path|checkout path/,
    );
  });
}

for (const protocol of ["workspace:*", "file:../dependency"]) {
  test(`rejects ${protocol} dependencies`, async (context) => {
    const archive = await mutateArchive(
      archivePath,
      context,
      async (packageRoot) => {
        await editJson(path.join(packageRoot, "package.json"), (manifest) => {
          manifest.devDependencies = { example: protocol };
        });
      },
    );
    await assert.rejects(
      () => validateArchive(archive),
      /uses a local dependency protocol/,
    );
  });
}
