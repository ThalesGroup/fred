import { fileURLToPath } from "node:url";
import { copyFile, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import path from "node:path";

const outputRoot = path.resolve("dist");
const tokensUrl = import.meta.resolve("@fred/design-tokens/tokens.css");
const fontsUrl = import.meta.resolve("@fred/design-tokens/fonts.css");
const tokensPath = fileURLToPath(tokensUrl);
const fontsPath = fileURLToPath(fontsUrl);
const tokensCss = await readFile(tokensPath, "utf8");
const fontsCss = await readFile(fontsPath, "utf8");

await rm(outputRoot, { recursive: true, force: true });
await mkdir(path.join(outputRoot, "fonts"), { recursive: true });
await Promise.all([
  writeFile(path.join(outputRoot, "tokens.css"), tokensCss),
  writeFile(path.join(outputRoot, "fonts.css"), fontsCss),
]);

const fontUrls = [...fontsCss.matchAll(/url\((['"]?)([^'"()]+)\1\)/g)].map(
  (match) => match[2],
);
if (fontUrls.length !== 2) {
  throw new Error(`Expected two packaged font URLs, found ${fontUrls.length}`);
}
for (const fontUrl of fontUrls) {
  const source = fileURLToPath(new URL(fontUrl, fontsUrl));
  await copyFile(source, path.join(outputRoot, "fonts", path.basename(source)));
}

const probeStyles = `
  html, body { overflow: visible; }
  body { user-select: text; }
  #outside-probe { box-sizing: content-box; }
  .probe {
    color: var(--on-surface);
    background-color: var(--surface-main);
    padding: var(--spacing-m);
    border-radius: var(--radius-s);
    font: var(--font-body-medium);
  }
`;

await writeFile(
  path.join(outputRoot, "tokens-only.html"),
  `<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="./tokens.css">
    <style>${probeStyles}</style>
    <title>Neutral token consumer</title>
  </head>
  <body>
    <div id="outside-probe">Consumer-owned shell probe</div>
    <div class="probe" id="probe">Token probe</div>
  </body>
</html>
`,
);

await writeFile(
  path.join(outputRoot, "fonts.html"),
  `<!doctype html>
<html lang="en" data-theme="light">
  <head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="./tokens.css">
    <link rel="stylesheet" href="./fonts.css">
    <style>
      .regular { font: 400 32px/1 "Geist", sans-serif; }
      .italic { font: italic 400 32px/1 "Geist", sans-serif; }
    </style>
    <title>Neutral font consumer</title>
  </head>
  <body>
    <div class="regular" id="regular">Regular Geist probe</div>
    <div class="italic" id="italic">Italic Geist probe</div>
  </body>
</html>
`,
);
