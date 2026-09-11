import { access, mkdir, mkdtemp, rm } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

import { packIframeSdk } from "./pack-iframe-sdk.mjs";
import { run } from "./process.mjs";
import { validateIframeSdkArchive } from "./validate-iframe-sdk-archive.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const repositoryRoot = path.resolve(scriptDirectory, "../../..");
const frontendRoot = path.join(repositoryRoot, "apps/frontend");
const integrationTest =
  "src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.sdk-integration.test.tsx";

export async function runIframeSdkHostIntegration() {
  const vitest = path.join(frontendRoot, "node_modules/.bin/vitest");
  try {
    await access(vitest);
  } catch {
    throw new Error(
      "frontend dependencies are missing; run `npm ci` in apps/frontend before the packed SDK host integration",
    );
  }

  const targetRoot = path.join(frontendRoot, "target");
  await mkdir(targetRoot, { recursive: true });
  const temporary = await mkdtemp(
    path.join(targetRoot, "iframe-sdk-host-integration-"),
  );
  try {
    const { archivePath } = await packIframeSdk();
    await validateIframeSdkArchive(archivePath);
    await run("tar", ["-xzf", archivePath, "-C", temporary]);
    const sdkEntry = path.join(temporary, "package/dist/index.js");
    const result = await run(vitest, ["run", integrationTest], {
      cwd: frontendRoot,
      env: {
        ...process.env,
        FRED_IFRAME_SDK_ENTRY_URL: sdkEntry,
        NODE_ENV: "test",
      },
    });
    return {
      archivePath,
      sdkEntry: "temporary-package/dist/index.js",
      test: integrationTest,
      stdout: result.stdout.trim(),
      stderr: result.stderr.trim(),
    };
  } finally {
    await rm(temporary, { recursive: true, force: true });
  }
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const result = await runIframeSdkHostIntegration();
  if (result.stdout) process.stdout.write(`${result.stdout}\n`);
  if (result.stderr) process.stderr.write(`${result.stderr}\n`);
  process.stdout.write(
    `${JSON.stringify(
      {
        archivePath: result.archivePath,
        sdkEntry: result.sdkEntry,
        test: result.test,
      },
      null,
      2,
    )}\n`,
  );
}
