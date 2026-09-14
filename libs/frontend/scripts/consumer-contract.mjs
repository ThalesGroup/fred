import { readFile, readdir, writeFile } from "node:fs/promises";
import path from "node:path";

const developmentNames = {
  designTokens: "@fred/design-tokens",
  ui: "@fred/ui",
  iframeSdk: "@fred/iframe-sdk",
};

export async function parameterizeConsumerSources(root, contract, roles) {
  const replacements = roles
    .map((role) => [developmentNames[role], contract.packages[role].name])
    .filter(([from, to]) => from !== to);
  if (replacements.length === 0) return;
  for (const entry of await readdir(root, {
    recursive: true,
    withFileTypes: true,
  })) {
    if (!entry.isFile() || !/\.(?:json|[cm]?[jt]sx?)$/.test(entry.name))
      continue;
    const filePath = path.join(entry.parentPath, entry.name);
    let content = await readFile(filePath, "utf8");
    for (const [from, to] of replacements)
      content = content.replaceAll(from, to);
    await writeFile(filePath, content);
  }
}
