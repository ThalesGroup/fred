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

const defaultRequestTimeoutMilliseconds = 10_000;
const defaultVisibilityAttempts = 6;
const defaultVisibilityDelayMilliseconds = 5_000;

export function exactCoordinateIdentity(coordinate) {
  assert.equal(typeof coordinate, "string", "registry coordinate is required");
  const separator = coordinate.lastIndexOf("@");
  assert(separator > 0, `invalid registry coordinate ${coordinate}`);
  const identity = {
    name: coordinate.slice(0, separator),
    version: coordinate.slice(separator + 1),
  };
  assert(
    identity.name && identity.version,
    `invalid registry coordinate ${coordinate}`,
  );
  assert(
    !/[/?#\\\s]/.test(identity.version),
    `invalid registry coordinate ${coordinate}`,
  );
  return identity;
}

function approvedRegistryRoot(registry) {
  const selected = new URL(registry);
  const loopback = ["127.0.0.1", "::1", "localhost"].includes(
    selected.hostname,
  );
  assert(
    selected.protocol === "https:" ||
      (selected.protocol === "http:" && loopback),
    "registry metadata requires HTTPS or a loopback test registry",
  );
  assert.equal(
    selected.username || selected.password,
    "",
    "registry metadata URL credentials are disallowed",
  );
  assert.equal(
    selected.search,
    "",
    "registry metadata URL query is disallowed",
  );
  assert.equal(
    selected.hash,
    "",
    "registry metadata URL fragment is disallowed",
  );
  assert.equal(
    selected.pathname,
    "/",
    "registry metadata URL must be an origin root",
  );
  return selected;
}

export function exactVersionMetadataUrl({ coordinate, registry }) {
  const selected = approvedRegistryRoot(registry);
  const { name, version } = exactCoordinateIdentity(coordinate);
  const encodedName = encodeURIComponent(name)
    .replace(/^%40/, "@")
    .replaceAll("%2F", "%2f");
  const endpoint = new URL(
    `${encodedName}/${encodeURIComponent(version)}`,
    selected,
  );
  assert.equal(
    endpoint.origin,
    selected.origin,
    "registry metadata endpoint escaped the approved registry",
  );
  return endpoint;
}

export function packageMetadataUrl({ coordinate, registry }) {
  const selected = approvedRegistryRoot(registry);
  const { name } = exactCoordinateIdentity(coordinate);
  const encodedName = encodeURIComponent(name)
    .replace(/^%40/, "@")
    .replaceAll("%2F", "%2f");
  const endpoint = new URL(encodedName, selected);
  assert.equal(
    endpoint.origin,
    selected.origin,
    "registry package metadata endpoint escaped the approved registry",
  );
  return endpoint;
}

export function assertExactPublishedMetadata(metadata, candidate) {
  assert(
    metadata && typeof metadata === "object" && !Array.isArray(metadata),
    `${candidate.coordinate} registry metadata is malformed`,
  );
  const expected = exactCoordinateIdentity(candidate.coordinate);
  assert.equal(
    metadata.name,
    expected.name,
    `${candidate.coordinate} metadata name differs`,
  );
  assert.equal(
    metadata.version,
    expected.version,
    `${candidate.coordinate} metadata version differs`,
  );
  assert.equal(
    metadata.dist?.integrity,
    candidate.integrity,
    `${candidate.coordinate} registry integrity differs`,
  );
  return metadata;
}

export async function fetchExactPackageMetadata({
  coordinate,
  registry,
  candidate,
  fetchMetadata = fetch,
  requestTimeoutMilliseconds = defaultRequestTimeoutMilliseconds,
}) {
  assert.equal(
    candidate?.coordinate,
    coordinate,
    "candidate coordinate differs",
  );
  assert.match(
    candidate?.integrity ?? "",
    /^sha512-[A-Za-z0-9+/]+={0,2}$/,
    `${coordinate} candidate integrity is missing or malformed`,
  );
  assert(
    Number.isSafeInteger(requestTimeoutMilliseconds) &&
      requestTimeoutMilliseconds > 0,
    "registry metadata request timeout must be a positive integer",
  );
  const endpoint = exactVersionMetadataUrl({ coordinate, registry });
  let response;
  try {
    response = await fetchMetadata(endpoint, {
      headers: { accept: "application/json" },
      redirect: "manual",
      signal: AbortSignal.timeout(requestTimeoutMilliseconds),
    });
  } catch (error) {
    throw new Error(`${coordinate} exact-version metadata request failed`, {
      cause: error,
    });
  }
  if (response.url) {
    const actual = new URL(response.url);
    assert.equal(
      actual.href,
      endpoint.href,
      `${coordinate} registry metadata response URL differs`,
    );
  }
  if (response.status === 404) return null;
  assert(
    response.status < 300 || response.status >= 400,
    `${coordinate} registry metadata redirect is disallowed`,
  );
  assert.equal(
    response.ok,
    true,
    `${coordinate} exact-version metadata request failed with HTTP ${response.status}`,
  );
  let metadata;
  try {
    metadata = await response.json();
  } catch (error) {
    throw new Error(`${coordinate} registry metadata is malformed JSON`, {
      cause: error,
    });
  }
  return assertExactPublishedMetadata(metadata, candidate);
}

export async function fetchPackageMetadata({
  coordinate,
  registry,
  candidate,
  fetchMetadata = fetch,
  requestTimeoutMilliseconds = defaultRequestTimeoutMilliseconds,
}) {
  assert.equal(
    candidate?.coordinate,
    coordinate,
    "candidate coordinate differs",
  );
  assert.match(
    candidate?.integrity ?? "",
    /^sha512-[A-Za-z0-9+/]+={0,2}$/,
    `${coordinate} candidate integrity is missing or malformed`,
  );
  assert(
    Number.isSafeInteger(requestTimeoutMilliseconds) &&
      requestTimeoutMilliseconds > 0,
    "registry metadata request timeout must be a positive integer",
  );
  const endpoint = packageMetadataUrl({ coordinate, registry });
  let response;
  try {
    response = await fetchMetadata(endpoint, {
      headers: { accept: "application/json" },
      redirect: "manual",
      signal: AbortSignal.timeout(requestTimeoutMilliseconds),
    });
  } catch (error) {
    throw new Error(`${coordinate} package metadata request failed`, {
      cause: error,
    });
  }
  if (response.url)
    assert.equal(
      new URL(response.url).href,
      endpoint.href,
      `${coordinate} package metadata response URL differs`,
    );
  if (response.status === 404) return null;
  assert(
    response.status < 300 || response.status >= 400,
    `${coordinate} package metadata redirect is disallowed`,
  );
  assert.equal(
    response.ok,
    true,
    `${coordinate} package metadata request failed with HTTP ${response.status}`,
  );
  let metadata;
  try {
    metadata = await response.json();
  } catch (error) {
    throw new Error(`${coordinate} package metadata is malformed JSON`, {
      cause: error,
    });
  }
  const { name, version } = exactCoordinateIdentity(coordinate);
  assert(
    metadata && typeof metadata === "object" && !Array.isArray(metadata),
    `${coordinate} package metadata is malformed`,
  );
  assert.equal(
    metadata.name,
    name,
    `${coordinate} package metadata name differs`,
  );
  assert(
    metadata.versions &&
      typeof metadata.versions === "object" &&
      !Array.isArray(metadata.versions),
    `${coordinate} package metadata versions are malformed`,
  );
  assertExactPublishedMetadata(metadata.versions[version], candidate);
  return metadata;
}

export async function waitForPackageMetadata({
  coordinate,
  registry,
  candidate,
  inspectRegistry = fetchPackageMetadata,
  visibilityAttempts = defaultVisibilityAttempts,
  visibilityDelayMilliseconds = defaultVisibilityDelayMilliseconds,
  waitForVisibility = (delay) =>
    new Promise((resolve) => setTimeout(resolve, delay)),
}) {
  assert(
    Number.isSafeInteger(visibilityAttempts) && visibilityAttempts > 0,
    "package metadata visibility attempts must be a positive integer",
  );
  assert(
    Number.isSafeInteger(visibilityDelayMilliseconds) &&
      visibilityDelayMilliseconds >= 0,
    "package metadata visibility delay must be a non-negative integer",
  );
  for (let attempt = 1; attempt <= visibilityAttempts; attempt += 1) {
    const metadata = await inspectRegistry({ coordinate, registry, candidate });
    if (metadata) return metadata;
    if (attempt < visibilityAttempts)
      await waitForVisibility(visibilityDelayMilliseconds);
  }
  throw new Error(
    `${coordinate} package-wide metadata visibility retries exhausted after ${visibilityAttempts} reads`,
  );
}

export async function waitForExactPackageMetadata({
  candidate,
  registry,
  inspectRegistry = fetchExactPackageMetadata,
  visibilityAttempts = defaultVisibilityAttempts,
  visibilityDelayMilliseconds = defaultVisibilityDelayMilliseconds,
  waitForVisibility = (delay) =>
    new Promise((resolve) => setTimeout(resolve, delay)),
}) {
  const coordinate = candidate?.coordinate;
  assert(coordinate, "candidate coordinate is required");
  assert(
    Number.isSafeInteger(visibilityAttempts) && visibilityAttempts > 0,
    "exact metadata visibility attempts must be a positive integer",
  );
  assert(
    Number.isSafeInteger(visibilityDelayMilliseconds) &&
      visibilityDelayMilliseconds >= 0,
    "exact metadata visibility delay must be a non-negative integer",
  );
  for (let attempt = 1; attempt <= visibilityAttempts; attempt += 1) {
    const metadata = await inspectRegistry({ coordinate, registry, candidate });
    if (metadata) return assertExactPublishedMetadata(metadata, candidate);
    if (attempt < visibilityAttempts)
      await waitForVisibility(visibilityDelayMilliseconds);
  }
  throw new Error(
    `${coordinate} exact-version metadata visibility retries exhausted after ${visibilityAttempts} reads`,
  );
}
