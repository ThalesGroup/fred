import { fileURLToPath } from "node:url";
import { mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

import { buildIframeSdk } from "./build-iframe-sdk.mjs";
import { run } from "./process.mjs";
import { loadReleaseContract, packageContract } from "./release-contract.mjs";
import { validateIframeSdkArchive } from "./validate-iframe-sdk-archive.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
export const workspaceRoot = path.resolve(scriptDirectory, "..");

function optionValue(name) {
  const index = process.argv.indexOf(name);
  return index === -1 ? undefined : process.argv[index + 1];
}

export async function packIframeSdk({
  validate = false,
  evidencePath,
  contract: selectedContract,
} = {}) {
  const contract = selectedContract ?? (await loadReleaseContract());
  const expected = packageContract(contract, "iframeSdk");
  const rootManifest = JSON.parse(
    await readFile(path.join(workspaceRoot, "package.json"), "utf8"),
  );
  if (rootManifest.private !== true)
    throw new Error("frontend package workspace root must remain private");
  await buildIframeSdk();
  const archiveDirectory = path.join(workspaceRoot, "target/archives");
  await mkdir(archiveDirectory, { recursive: true });
  const { stdout } = await run(
    "npm",
    [
      "pack",
      "--json",
      "--workspace",
      expected.name,
      "--pack-destination",
      archiveDirectory,
    ],
    { cwd: workspaceRoot },
  );
  const [packResult] = JSON.parse(stdout);
  if (
    packResult.name !== expected.name ||
    packResult.version !== expected.version
  )
    throw new Error(`npm selected unexpected package: ${packResult.name}`);
  const archivePath = path.join(archiveDirectory, packResult.filename);
  const validation = validate
    ? await validateIframeSdkArchive(archivePath, { contract })
    : undefined;
  const evidence = { packResult, validation };
  if (evidencePath) {
    const resolved = path.resolve(workspaceRoot, evidencePath);
    await mkdir(path.dirname(resolved), { recursive: true });
    await writeFile(resolved, `${JSON.stringify(evidence, null, 2)}\n`);
  }
  return { archivePath, evidence };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await packIframeSdk({
    validate: process.argv.includes("--validate"),
    evidencePath: optionValue("--evidence"),
    contract: await loadReleaseContract(optionValue("--contract")),
  });
  process.stdout.write(`${JSON.stringify(result, null, 2)}\n`);
}
