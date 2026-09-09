import assert from "node:assert/strict";
import { mkdtemp, readFile, rm, symlink, writeFile } from "node:fs/promises";
import os from "node:os";
import path from "node:path";
import test from "node:test";

import { packUi } from "../scripts/pack-ui.mjs";
import { run } from "../scripts/process.mjs";
import { validateUiArchive } from "../scripts/validate-ui-archive.mjs";

async function mutateArchive(sourceArchive, context, mutate) {
  const temporary = await mkdtemp(path.join(os.tmpdir(), "fred-invalid-ui-"));
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

const { archivePath } = await packUi();

test("accepts the actual packed UI archive", async () => {
  const evidence = await validateUiArchive(archivePath);
  assert.equal(evidence.package, "@fred/ui@0.0.0-development");
  assert.equal(evidence.glyphCount, 132);
  assert.deepEqual(evidence.externalModules, ["react", "react/jsx-runtime"]);
});

for (const file of [
  "dist/index.js",
  "dist/styles.css",
  "dist/fonts/MaterialSymbolsOutlined.woff2",
  "dist/types/src/index.d.ts",
  "licenses/Material-Symbols-Apache-2.0.txt",
  "THIRD_PARTY_NOTICES.md",
]) {
  test(`rejects missing ${file}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, (root) =>
      rm(path.join(root, file)),
    );
    await assert.rejects(
      validateUiArchive(archive),
      /packed inventory differs/,
    );
  });
}

test("rejects unexpected files", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    writeFile(path.join(root, "source.tsx"), "export {};\n"),
  );
  await assert.rejects(validateUiArchive(archive), /packed inventory differs/);
});

test("rejects symbolic links in the packed package", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/index.js");
    await rm(file);
    await symlink("../../README.md", file);
  });
  await assert.rejects(validateUiArchive(archive), /link/);
});

test("rejects an export that escapes the package", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    editJson(path.join(root, "package.json"), (manifest) => {
      manifest.exports["./styles.css"] = "../styles.css";
    }),
  );
  await assert.rejects(validateUiArchive(archive), /escapes the package/);
});

test("rejects an absent export target", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    editJson(path.join(root, "package.json"), (manifest) => {
      manifest.exports["./styles.css"] = "./dist/missing.css";
    }),
  );
  await assert.rejects(validateUiArchive(archive), /is absent/);
});

for (const peerMutation of [
  [
    "bundled React",
    (manifest) => {
      manifest.dependencies = { react: "19.2.4" };
    },
    /must use peers/,
  ],
  [
    "invalid React peer",
    (manifest) => {
      manifest.peerDependencies.react = "*";
    },
    /deep-equal/,
  ],
  [
    "workspace protocol",
    (manifest) => {
      manifest.peerDependencies.react = "workspace:*";
    },
    /deep-equal|local dependency/,
  ],
]) {
  test(`rejects ${peerMutation[0]}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, (root) =>
      editJson(path.join(root, "package.json"), peerMutation[1]),
    );
    await assert.rejects(validateUiArchive(archive), peerMutation[2]);
  });
}

test("rejects an undeclared JS module", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/index.js");
    await writeFile(
      file,
      `import "left-pad";\n${await readFile(file, "utf8")}`,
    );
  });
  await assert.rejects(
    validateUiArchive(archive),
    /undeclared bare module left-pad/,
  );
});

for (const forbidden of [
  "customAgent",
  "material-symbols-rounded",
  "material-symbols-sharp",
  "/images/icons/",
]) {
  test(`rejects application-only icon behavior ${forbidden}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const file = path.join(root, "dist/index.js");
      await writeFile(
        file,
        `${await readFile(file, "utf8")}\n/* ${forbidden} */\n`,
      );
    });
    await assert.rejects(
      validateUiArchive(archive),
      /application-only icon behavior/,
    );
  });
}

test("rejects application-only icon declarations", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(
      root,
      "dist/types/.generated/src/rework/components/shared/atoms/Icon/Icon.d.ts",
    );
    await writeFile(
      file,
      `${await readFile(file, "utf8")}\nexport type IconCategory = "rounded";\n`,
    );
  });
  await assert.rejects(
    validateUiArchive(archive),
    /application-only icon declarations/,
  );
});

for (const forbidden of [
  "@shared/atoms/Icon",
  "apps/frontend/src/index.scss",
  "/Users/example/fred/source.tsx",
]) {
  test(`rejects generated FRED reference ${forbidden}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const file = path.join(root, "dist/index.js");
      await writeFile(
        file,
        `${await readFile(file, "utf8")}\n/* ${forbidden} */\n`,
      );
    });
    await assert.rejects(
      validateUiArchive(archive),
      /forbidden FRED\/local reference|undeclared bare module/,
    );
  });
}

test("rejects an unresolved declaration reference", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/types/src/index.d.ts");
    await writeFile(
      file,
      `export type X = import("./missing.ts").X;\n${await readFile(file, "utf8")}`,
    );
  });
  await assert.rejects(validateUiArchive(archive), /unresolved reference/);
});

test("rejects an escaping declaration reference", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/types/src/index.d.ts");
    await writeFile(
      file,
      `export type X = import("../../../../../outside").X;\n${await readFile(file, "utf8")}`,
    );
  });
  await assert.rejects(validateUiArchive(archive), /escaping reference/);
});

test("rejects a declaration reference that resolves to a directory", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/types/src/index.d.ts");
    await writeFile(
      file,
      `export type X = import("..").X;\n${await readFile(file, "utf8")}`,
    );
  });
  await assert.rejects(validateUiArchive(archive), /unresolved reference/);
});

for (const cssMutation of [
  [
    "mixed-case imports",
    '@ImPoRt "./missing.css";',
    /must not contain @import/,
  ],
  [
    "external assets",
    '.fred-ui .material-symbols-outlined { background: url("https://fonts.example/font.woff2"); }',
    /non-package URL/,
  ],
  ["document selectors", "html body { overflow: hidden; }", /shell selector/],
  [
    "unscoped base rules",
    "* { box-sizing: border-box; }",
    /unscoped non-module selector/,
  ],
  [
    "selectors escaping the UI root",
    ".fred-ui + #outside-probe { box-sizing: border-box; }",
    /unscoped non-module selector/,
  ],
  [
    "shell behavior",
    ".fred-ui { overflow: hidden; }",
    /shell behavior overflow/,
  ],
  [
    "unresolved custom properties",
    ".fred-ui ._broken { color: var(--missing-reviewed-token); }",
    /custom-property references absent/,
  ],
]) {
  test(`rejects UI CSS ${cssMutation[0]}`, async (context) => {
    const archive = await mutateArchive(archivePath, context, async (root) => {
      const file = path.join(root, "dist/styles.css");
      await writeFile(
        file,
        `${await readFile(file, "utf8")}\n${cssMutation[1]}\n`,
      );
    });
    await assert.rejects(validateUiArchive(archive), cssMutation[2]);
  });
}

test("rejects a modified Material font", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(root, "dist/fonts/MaterialSymbolsOutlined.woff2");
    const content = await readFile(file);
    content[100] ^= 1;
    await writeFile(file, content);
  });
  await assert.rejects(validateUiArchive(archive), /differs from provenance/);
});

test("rejects an unsupported declared glyph", async (context) => {
  const archive = await mutateArchive(archivePath, context, async (root) => {
    const file = path.join(
      root,
      "dist/types/.generated/src/rework/components/shared/utils/Type.d.ts",
    );
    const content = await readFile(file, "utf8");
    await writeFile(
      file,
      content.replace('"book_2"]', '"book_2", "not_a_fred_symbol"]'),
    );
  });
  await assert.rejects(
    validateUiArchive(archive),
    /unsupported packed Material Symbols names/,
  );
});

for (const input of [
  "LICENSE",
  "licenses/Material-Symbols-Apache-2.0.txt",
  "THIRD_PARTY_NOTICES.md",
]) {
  for (const kind of ["truncated", "modified"]) {
    test(`rejects ${kind} ${input}`, async (context) => {
      const archive = await mutateArchive(
        archivePath,
        context,
        async (root) => {
          const file = path.join(root, input);
          const content = await readFile(file);
          if (kind === "truncated")
            await writeFile(file, content.subarray(0, 100));
          else {
            content[50] ^= 1;
            await writeFile(file, content);
          }
        },
      );
      await assert.rejects(
        validateUiArchive(archive),
        /approved complete content/,
      );
    });
  }
}

test("rejects build evidence that marks React internal", async (context) => {
  const archive = await mutateArchive(archivePath, context, (root) =>
    editJson(path.join(root, "build-evidence.json"), (evidence) => {
      evidence.modules.find(({ id }) => id === "react").external = false;
    }),
  );
  await assert.rejects(
    validateUiArchive(archive),
    /react is not proven external/,
  );
});
