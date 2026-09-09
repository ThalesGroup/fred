import { fileURLToPath } from "node:url";
import { mkdir, rm } from "node:fs/promises";
import path from "node:path";

import { run } from "./process.mjs";

const scriptDirectory = path.dirname(fileURLToPath(import.meta.url));
const workspaceRoot = path.resolve(scriptDirectory, "..");
const fixtureRoot = path.join(workspaceRoot, "fixtures/react-consumer");
export const consumerCache = path.join(
  workspaceRoot,
  "target/react-consumer-cache",
);

export async function provisionReactConsumer() {
  await rm(consumerCache, { recursive: true, force: true });
  await mkdir(consumerCache, { recursive: true });
  await run(
    "npm",
    [
      "ci",
      "--ignore-scripts",
      "--no-audit",
      "--no-fund",
      "--cache",
      consumerCache,
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
    cache: consumerCache,
    lockfile: path.join(fixtureRoot, "package-lock.json"),
  };
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  process.stdout.write(
    `${JSON.stringify(await provisionReactConsumer(), null, 2)}\n`,
  );
}
