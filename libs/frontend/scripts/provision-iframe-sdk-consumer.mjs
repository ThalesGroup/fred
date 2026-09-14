import { fileURLToPath } from "node:url";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";

import { run } from "./process.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDirectory, "..");
const fixtureRoot = path.join(workspaceRoot, "fixtures/iframe-sdk-consumer");
export const iframeSdkConsumerCache = path.join(
  workspaceRoot,
  "target/iframe-sdk-consumer-cache",
);

export async function provisionIframeSdkConsumer() {
  await rm(iframeSdkConsumerCache, { recursive: true, force: true });
  await mkdir(iframeSdkConsumerCache, { recursive: true });
  await run(
    "npm",
    [
      "ci",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--cache",
      iframeSdkConsumerCache,
    ],
    {
      cwd: fixtureRoot,
      env: {
        ...process.env,
        npm_config_audit: "false",
        npm_config_fund: "false",
      },
    },
  );
  await rm(path.join(fixtureRoot, "node_modules"), {
    recursive: true,
    force: true,
  });
  return {
    cache: iframeSdkConsumerCache,
    lockfile: path.join(fixtureRoot, "package-lock.json"),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await provisionIframeSdkConsumer(), null, 2)}\n`,
  );
}
