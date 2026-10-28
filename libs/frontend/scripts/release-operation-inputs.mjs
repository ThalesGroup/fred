// Copyright Thales 2026
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import assert from "node:assert/strict";

export const registryRoot = "https://registry.npmjs.org/";
export const releasePackageNames = Object.freeze([
  "design-tokens",
  "ui",
  "iframe-sdk",
]);

const channelPattern = /^[a-z0-9][a-z0-9._-]*$/;
const exactVersionPattern =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?(?:\+[0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)?$/;
const partialRangePattern = /^(0|[1-9]\d*)(?:\.(0|[1-9]\d*))?$/;
const wildcardIdentifier = String.raw`(?:[xX]|0|[1-9]\d*)`;
const prerelease = String.raw`([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*)`;
const wildcardMajorPartialPattern = new RegExp(
  String.raw`^[xX](?:\.${wildcardIdentifier})?$`,
);
const wildcardMajorFullPattern = new RegExp(
  String.raw`^[xX]\.${wildcardIdentifier}\.${wildcardIdentifier}(?:-${prerelease})?$`,
);
const majorWildcardRangePattern = /^(0|[1-9]\d*)\.[xX]$/;
const majorWildcardFullPattern = new RegExp(
  String.raw`^(0|[1-9]\d*)\.[xX]\.${wildcardIdentifier}(?:-${prerelease})?$`,
);
const minorWildcardRangePattern =
  /^(0|[1-9]\d*)\.(0|[1-9]\d*)\.[xX](?:-([0-9A-Za-z-]+(?:\.[0-9A-Za-z-]+)*))?$/;

function safeNumericIdentifier(value) {
  return Number.isSafeInteger(Number(value));
}

export function isExactSemanticVersion(value) {
  const match = exactVersionPattern.exec(value);
  if (!match || !match.slice(1, 4).every(safeNumericIdentifier)) return false;
  return !(match[4] ?? "")
    .split(".")
    .filter((identifier) => /^\d+$/.test(identifier))
    .some((identifier) => identifier.length > 1 && identifier.startsWith("0"));
}

function validPrerelease(value) {
  return !(value ?? "")
    .split(".")
    .filter((identifier) => /^\d+$/.test(identifier))
    .some((identifier) => identifier.length > 1 && identifier.startsWith("0"));
}

// This is the dependency-free authorization guard for the intersection of npm
// tag syntax and node-semver ranges. The shared command repeats the decision
// with semver.validRange after dependencies are installed.
export function isSemanticVersionRangeLikeTag(value) {
  const candidate = value.startsWith("v") ? value.slice(1) : value;
  if (isExactSemanticVersion(candidate)) return true;
  if (wildcardMajorPartialPattern.test(candidate)) return true;
  const wildcardMajorFull = wildcardMajorFullPattern.exec(candidate);
  if (wildcardMajorFull) return validPrerelease(wildcardMajorFull[1]);
  const partial = partialRangePattern.exec(candidate);
  if (partial) {
    const identifiers = partial.slice(1).filter(Boolean);
    return (
      identifiers.every(safeNumericIdentifier) &&
      Number(identifiers.at(-1)) < Number.MAX_SAFE_INTEGER
    );
  }
  const majorWildcard = majorWildcardRangePattern.exec(candidate);
  if (majorWildcard)
    return (
      safeNumericIdentifier(majorWildcard[1]) &&
      Number(majorWildcard[1]) < Number.MAX_SAFE_INTEGER
    );
  const majorWildcardFull = majorWildcardFullPattern.exec(candidate);
  if (majorWildcardFull)
    return (
      safeNumericIdentifier(majorWildcardFull[1]) &&
      Number(majorWildcardFull[1]) < Number.MAX_SAFE_INTEGER &&
      validPrerelease(majorWildcardFull[2])
    );
  const minorWildcard = minorWildcardRangePattern.exec(candidate);
  return Boolean(
    minorWildcard &&
    minorWildcard.slice(1, 3).every(safeNumericIdentifier) &&
    Number(minorWildcard[2]) < Number.MAX_SAFE_INTEGER &&
    validPrerelease(minorWildcard[3]),
  );
}

function capturedValue(name, environment) {
  const value = environment[`FRED_RELEASE_${name}`] ?? "";
  assert.equal(typeof value, "string", `${name} must be text`);
  assert(!/[\r\n]/.test(value), `${name} must be a single line`);
  return value;
}

export function approvedRegistry(registry) {
  const url = new URL(registry);
  const loopback = ["127.0.0.1", "::1", "localhost"].includes(url.hostname);
  assert(
    url.protocol === "https:" || (url.protocol === "http:" && loopback),
    "registry must use HTTPS or loopback HTTP",
  );
  assert.equal(
    url.username || url.password,
    "",
    "registry credentials in URL are forbidden",
  );
  assert(url.pathname.endsWith("/"), "registry path must end with a slash");
  assert.equal(
    url.search || url.hash,
    "",
    "registry query and fragment are forbidden",
  );
  return url;
}

export function parseDryRun(value) {
  if (["", "0", "false", "no"].includes(value)) return false;
  if (["1", "true", "yes"].includes(value)) return true;
  throw new Error("DRY_RUN must be empty, 0, false, no, 1, true, or yes");
}

export function readReleaseInputs({ environment = process.env, operation }) {
  const packageName = capturedValue("PACKAGE", environment);
  const releaseDirectory = capturedValue("RELEASE_DIR", environment);
  const authMode = capturedValue("AUTH_MODE", environment) || "local";
  const dryRun = parseDryRun(capturedValue("DRY_RUN", environment));
  const registry = capturedValue("REGISTRY", environment) || registryRoot;
  const version = capturedValue("VERSION", environment);
  const channel = capturedValue("CHANNEL", environment);
  assert(
    releasePackageNames.includes(packageName),
    `PACKAGE must be exactly one of: ${releasePackageNames.join(", ")}`,
  );
  assert(
    ["local", "token", "oidc"].includes(authMode),
    "AUTH_MODE must be local, token, or oidc",
  );
  approvedRegistry(registry);
  if (version)
    assert(
      isExactSemanticVersion(version),
      "VERSION must be an exact semantic version",
    );
  if (channel) {
    assert(channelPattern.test(channel), "CHANNEL is invalid");
    assert(
      !isSemanticVersionRangeLikeTag(channel),
      "CHANNEL must not be a semantic-version range",
    );
  }
  if (operation === "promote") {
    assert(version, "VERSION must be an exact semantic version");
    assert(channel, "CHANNEL is invalid");
  }
  return {
    authMode,
    channel,
    dryRun,
    packageName,
    registry,
    releaseDirectory: releaseDirectory || undefined,
    version,
  };
}
