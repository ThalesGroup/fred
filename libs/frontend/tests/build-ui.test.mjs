import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";
import { pathToFileURL } from "node:url";

import {
  assertUiBuildSourceGraph,
  buildUi,
  isUiExternal,
  packageRoot,
  UI_RUNTIME_SOURCE_PATHS,
} from "../scripts/build-ui.mjs";

async function hash(relativePath) {
  return createHash("sha256")
    .update(await readFile(path.join(packageRoot, relativePath)))
    .digest("hex");
}

test("UI output is deterministic, scoped, closed, and externalized", async () => {
  const firstEvidence = await buildUi();
  const firstHashes = await Promise.all(
    [
      "dist/index.js",
      "dist/styles.css",
      "dist/fonts/MaterialSymbolsOutlined.woff2",
      "dist/types/src/index.d.ts",
    ].map(hash),
  );
  const secondEvidence = await buildUi();
  const secondHashes = await Promise.all(
    [
      "dist/index.js",
      "dist/styles.css",
      "dist/fonts/MaterialSymbolsOutlined.woff2",
      "dist/types/src/index.d.ts",
    ].map(hash),
  );
  assert.deepEqual(secondHashes, firstHashes);
  assert.deepEqual(
    secondEvidence.sourceAllowlist,
    firstEvidence.sourceAllowlist,
  );
  const css = await readFile(path.join(packageRoot, "dist/styles.css"), "utf8");
  assert.match(css, /\.fred-ui/);
  assert.doesNotMatch(css, /(?:^|})\s*(?:html|body|:root)\b/);
  assert.doesNotMatch(css, /@import/i);
  assert.doesNotMatch(css, /https?:\/\//i);
  const js = await readFile(path.join(packageRoot, "dist/index.js"), "utf8");
  assert.match(js, /from\s+"react\/jsx-runtime"/);
  assert.doesNotMatch(js, /apps\/frontend|@shared|@rework|node_modules\/react/);
  assert.doesNotMatch(
    js,
    /customAgent|material-symbols-(?:rounded|sharp)|\/images\/icons\//,
  );
  const runtime = await import(
    `${pathToFileURL(path.join(packageRoot, "dist/index.js")).href}?test=${Date.now()}`
  );
  assert.deepEqual(Object.keys(runtime).sort(), [
    "Button",
    "Icon",
    "IconButton",
    "Spinner",
    "TextInput",
  ]);
  const declarations = await readFile(
    path.join(packageRoot, "dist/types/src/index.d.ts"),
    "utf8",
  );
  for (const publicType of [
    "ButtonProps",
    "ButtonSize",
    "ButtonVariant",
    "ColorTheme",
    "IconButtonProps",
    "IconButtonVariant",
    "IconProps",
    "MaterialIconType",
    "SpinnerProps",
    "TextInputProps",
  ])
    assert.match(declarations, new RegExp(`\\b${publicType}\\b`), publicType);
  const manifest = JSON.parse(
    await readFile(path.join(packageRoot, "package.json"), "utf8"),
  );
  assert.deepEqual(manifest.peerDependencies, {
    "@fred/design-tokens": "0.0.0-development",
    react: "^19.2.4",
    "react-dom": "^19.2.4",
  });
  assertUiBuildSourceGraph(secondEvidence.modules);
});

test("missing or unexpected canonical modules fail the source-graph gate", () => {
  const evidenceModules = UI_RUNTIME_SOURCE_PATHS.map((source) => ({
    id: source.replace(
      /^apps\/frontend\/src\//,
      "libs/frontend/ui/.generated/src/",
    ),
    external: false,
  }));
  assert.doesNotThrow(() => assertUiBuildSourceGraph(evidenceModules));
  assert.throws(
    () => assertUiBuildSourceGraph(evidenceModules.slice(1)),
    /differs from the canonical allowlist/,
  );
  assert.throws(
    () =>
      assertUiBuildSourceGraph([
        ...evidenceModules,
        {
          id: "libs/frontend/ui/.generated/src/unreviewed.ts",
          external: false,
        },
      ]),
    /differs from the canonical allowlist/,
  );
});

test("externalizes React, React DOM, their subpaths, and both JSX runtimes", () => {
  for (const module of [
    "react",
    "react/jsx-runtime",
    "react/jsx-dev-runtime",
    "react-dom",
    "react-dom/client",
    "react-dom/server",
  ])
    assert.equal(isUiExternal(module), true, module);
  assert.equal(isUiExternal("reactive-library"), false);
});
