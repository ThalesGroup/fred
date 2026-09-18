import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import path from "node:path";

export function assertChangelogVersion(text, version) {
  const headings = [
    ...text.matchAll(/^## (\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?)\s*$/gm),
  ];
  assert.equal(
    headings.filter((match) => match[1] === version).length,
    1,
    `changelog must have one exact entry for ${version}`,
  );
  const entry = headings.find((match) => match[1] === version);
  const next = headings.find((match) => match.index > entry.index);
  const body = text.slice(
    entry.index + entry[0].length,
    next?.index ?? text.length,
  );
  assert(
    /^Review: approved\s*$/m.test(body),
    `${version} changelog entry is unreviewed`,
  );
  assert(
    /^Changes: \S.+$/m.test(body),
    `${version} changelog changes are missing`,
  );
  return { version, reviewed: true };
}

export async function assertMemberChangelog(root, member, version) {
  const text = await readFile(
    path.join(root, member.workspace, "CHANGELOG.md"),
    "utf8",
  );
  return assertChangelogVersion(text, version);
}
