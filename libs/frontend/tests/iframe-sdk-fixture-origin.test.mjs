import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";
import test from "node:test";

import ts from "typescript";

import { workspaceRoot } from "../scripts/pack-design-tokens.mjs";

const source = await readFile(
  path.join(
    workspaceRoot,
    "fixtures/iframe-sdk-consumer/src/fixture-origin.ts",
  ),
  "utf8",
);
const compiled = ts.transpileModule(source, {
  fileName: "fixture-origin.ts",
  reportDiagnostics: true,
  compilerOptions: {
    module: ts.ModuleKind.ESNext,
    target: ts.ScriptTarget.ES2022,
  },
});
assert.deepEqual(compiled.diagnostics, []);
const fixtureOrigins = await import(
  `data:text/javascript;base64,${Buffer.from(compiled.outputText).toString("base64")}`
);

function search(applicationOrigin, attackerOrigin) {
  const parameters = new URLSearchParams({
    applicationOrigin,
    attackerOrigin,
  });
  return `?${parameters}`;
}

test("constructs fixed fixture paths from three distinct dynamic loopback ports", () => {
  const origins = fixtureOrigins.readFixtureOrigins(
    "http://127.0.0.1:41001",
    search("http://127.0.0.1:41002", "http://127.0.0.1:41003"),
  );
  assert.deepEqual(origins, {
    applicationOrigin: "http://127.0.0.1:41002",
    applicationPort: 41002,
    attackerOrigin: "http://127.0.0.1:41003",
    attackerPort: 41003,
    hostOrigin: "http://127.0.0.1:41001",
    hostPort: 41001,
  });
  assert.equal(
    fixtureOrigins.applicationFixtureUrl(origins).href,
    "http://127.0.0.1:41002/child.html?hostOrigin=http%3A%2F%2F127.0.0.1%3A41001",
  );
  assert.equal(
    fixtureOrigins.applicationFixtureUrl(origins, 100).href,
    "http://127.0.0.1:41002/child.html?hostOrigin=http%3A%2F%2F127.0.0.1%3A41001&connectionTimeoutMs=100",
  );
  assert.equal(
    fixtureOrigins.attackerFixtureUrl(origins).href,
    "http://127.0.0.1:41003/attacker.html?targetOrigin=http%3A%2F%2F127.0.0.1%3A41002",
  );
});

for (const [name, value] of [
  ["JavaScript scheme", "javascript:alert(1)"],
  ["data scheme", "data:text/html,unsafe"],
  ["file scheme", "file:///tmp/unsafe"],
  ["HTTPS scheme", "https://127.0.0.1:41002"],
  ["protocol-relative URL", "//127.0.0.1:41002"],
  ["external host", "http://example.com:41002"],
  ["misleading hostname", "http://127.0.0.1.example.com:41002"],
  ["credentials", "http://user@127.0.0.1:41002"],
  ["unexpected path", "http://127.0.0.1:41002/child.html"],
  ["unexpected query", "http://127.0.0.1:41002?next=unsafe"],
  ["unexpected fragment", "http://127.0.0.1:41002#unsafe"],
  ["missing port", "http://127.0.0.1"],
  ["zero port", "http://127.0.0.1:0"],
  ["out-of-range port", "http://127.0.0.1:65536"],
  ["non-canonical port", "http://127.0.0.1:041002"],
  ["surrounding whitespace", " http://127.0.0.1:41002 "],
]) {
  test(`rejects ${name} before producing fixture destinations`, () => {
    assert.throws(
      () =>
        fixtureOrigins.readFixtureOrigins(
          "http://127.0.0.1:41001",
          search(value, "http://127.0.0.1:41003"),
        ),
      /fixture application origin/,
    );
  });
}

test("rejects missing, duplicate, unknown, and colliding configuration", () => {
  const hostOrigin = "http://127.0.0.1:41001";
  for (const configuredSearch of [
    "?applicationOrigin=http%3A%2F%2F127.0.0.1%3A41002",
    "?applicationOrigin=http%3A%2F%2F127.0.0.1%3A41002&applicationOrigin=http%3A%2F%2F127.0.0.1%3A41004&attackerOrigin=http%3A%2F%2F127.0.0.1%3A41003",
    `${search("http://127.0.0.1:41002", "http://127.0.0.1:41003")}&extra=1`,
  ]) {
    assert.throws(
      () => fixtureOrigins.readFixtureOrigins(hostOrigin, configuredSearch),
      /required exactly once/,
    );
  }
  for (const configuredSearch of [
    search(hostOrigin, "http://127.0.0.1:41003"),
    search("http://127.0.0.1:41002", "http://127.0.0.1:41002"),
  ]) {
    assert.throws(
      () => fixtureOrigins.readFixtureOrigins(hostOrigin, configuredSearch),
      /must be distinct/,
    );
  }
});

test("rejects unsafe attacker and host origins through the same validation", () => {
  assert.throws(
    () =>
      fixtureOrigins.readFixtureOrigins(
        "http://127.0.0.1:41001",
        search("http://127.0.0.1:41002", "javascript:alert(1)"),
      ),
    /fixture attacker origin/,
  );
  assert.throws(
    () =>
      fixtureOrigins.readFixtureOrigins(
        "http://example.com:41001",
        search("http://127.0.0.1:41002", "http://127.0.0.1:41003"),
      ),
    /fixture host origin/,
  );
});
