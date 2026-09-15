import assert from "node:assert/strict";
import { appendFile, cp, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";

const args = process.argv.slice(2);
const command = args[0];
const contract = JSON.parse(
  await readFile(process.env.FRED_RECOVERY_CLI_CONTRACT, "utf8"),
);
const evidence = JSON.parse(
  await readFile(process.env.FRED_RECOVERY_CLI_EVIDENCE, "utf8"),
);
assert(
  ["127.0.0.1", "::1", "localhost"].includes(
    new URL(contract.registry).hostname,
  ),
  "controlled npm fixture requires a loopback registry",
);
assert.equal(
  process.env.NODE_AUTH_TOKEN,
  undefined,
  "controlled npm fixture must not receive a publishing credential",
);
const commandLog = process.env.FRED_RECOVERY_CLI_COMMAND_LOG;
const publishedState = process.env.FRED_RECOVERY_CLI_PUBLISHED_STATE;

async function log(value) {
  await appendFile(commandLog, `${JSON.stringify(value)}\n`);
}

function roleForCoordinate(coordinate) {
  return Object.entries(contract.packages).find(
    ([, selected]) => `${selected.name}@${selected.version}` === coordinate,
  )?.[0];
}

function roleForArchive(archivePath) {
  return Object.entries(evidence.packages).find(
    ([, candidate]) => candidate.filename === path.basename(archivePath),
  )?.[0];
}

if (command === "pack") {
  const coordinate = args[1];
  const role = roleForCoordinate(coordinate);
  assert(role, `unexpected controlled pack coordinate ${coordinate}`);
  const destination = args[args.indexOf("--pack-destination") + 1];
  const candidate = evidence.packages[role];
  await cp(
    path.join(process.env.FRED_RECOVERY_CLI_ARCHIVE_ROOT, candidate.filename),
    path.join(destination, candidate.filename),
  );
  await log({ command: "pack", role });
  process.stdout.write(
    `${JSON.stringify([{ filename: candidate.filename }])}\n`,
  );
} else if (command === "install" && args.includes("--package-lock-only")) {
  const manifest = JSON.parse(
    await readFile(path.join(process.cwd(), "package.json"), "utf8"),
  );
  const packages = { "": { dependencies: manifest.dependencies } };
  for (const [name, version] of Object.entries(manifest.dependencies ?? {})) {
    const role = Object.entries(contract.packages).find(
      ([, selected]) => selected.name === name && selected.version === version,
    )?.[0];
    assert(role, `unexpected controlled install dependency ${name}@${version}`);
    packages[`node_modules/${name}`] = {
      version,
      resolved: `${contract.registry}${name}/-/${role}.tgz`,
      integrity: evidence.packages[role].integrity,
    };
  }
  await writeFile(
    path.join(process.cwd(), "package-lock.json"),
    `${JSON.stringify({ lockfileVersion: 3, packages })}\n`,
  );
  await log({ command: "lock" });
} else if (command === "ci") {
  const manifest = JSON.parse(
    await readFile(path.join(process.cwd(), "package.json"), "utf8"),
  );
  for (const [name, version] of Object.entries(manifest.dependencies ?? {})) {
    const packageRoot = path.join(
      process.cwd(),
      "node_modules",
      ...name.split("/"),
    );
    await mkdir(packageRoot, { recursive: true });
    await writeFile(
      path.join(packageRoot, "package.json"),
      `${JSON.stringify({ name, version })}\n`,
    );
  }
  await log({ command: "ci" });
} else if (command === "ls") {
  const manifest = JSON.parse(
    await readFile(path.join(process.cwd(), "package.json"), "utf8"),
  );
  process.stdout.write(
    `${JSON.stringify({
      dependencies: Object.fromEntries(
        Object.entries(manifest.dependencies ?? {}).map(([name, version]) => [
          name,
          { version },
        ]),
      ),
    })}\n`,
  );
  await log({ command: "ls" });
} else if (command === "audit" && args[1] === "signatures") {
  await log({ command: "audit-signatures" });
} else if (command === "whoami") {
  await log({ command: "whoami" });
  process.stdout.write("marc.fawaz\n");
} else if (command === "publish") {
  const role = roleForArchive(args[1]);
  assert(role, `unexpected controlled publish archive ${args[1]}`);
  await log({ command: "publish", role });
  const state = JSON.parse(await readFile(publishedState, "utf8"));
  state[role] = true;
  await writeFile(publishedState, `${JSON.stringify(state)}\n`);
  if (process.env.FRED_RECOVERY_CLI_FAIL_PUBLISH === role) {
    process.stderr.write(`controlled ${role} publication failure\n`);
    process.exitCode = 1;
  }
} else {
  throw new Error(`unexpected controlled npm command: ${args.join(" ")}`);
}
