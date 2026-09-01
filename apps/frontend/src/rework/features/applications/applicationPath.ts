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

const SCHEME = /^[a-z][a-z\d+.-]*:/i;

function fullyDecodeSegment(rawSegment: string): string {
  let decoded = rawSegment;

  // Every successful percent-decode removes at least one encoded layer. Bound
  // the loop by the input length so even adversarial nesting cannot loop.
  for (let iteration = 0; iteration <= rawSegment.length; iteration += 1) {
    try {
      // The browser-facing input must be valid on its first layer. On later
      // layers, however, a decoded `%25` is ordinary literal data. Escape
      // only those newly produced bare percent signs while continuing to
      // decode valid sibling escapes; otherwise a malformed sibling can hide
      // an encoded traversal sequence from the validator.
      const decodable = iteration === 0 ? decoded : decoded.replace(/%(?![0-9A-Fa-f]{2})/g, "%25");
      const next = decodeURIComponent(decodable);
      if (next === decoded) return decoded;
      decoded = next;
    } catch {
      // Malformed UTF-8 or malformed caller-provided percent encoding is never
      // valid path data.
      throw new TypeError("Application paths must use valid percent-encoding at every layer");
    }
  }

  throw new TypeError("Application path encoding is too deeply nested");
}

/**
 * Validate an application-owned path while preserving its original encoding.
 * Returning the original value is intentional: decoding is only a security
 * check and must not change the bytes the application service receives.
 * Every caller now feeds this strings posted by another document, so this is
 * what stops a frame driving Fred's router or proxy outside its own subtree.
 */
export function normalizeApplicationRelativePath(relativePath: string): string {
  if (typeof relativePath !== "string") {
    throw new TypeError("Application paths must be strings");
  }
  if (relativePath.includes("#")) {
    throw new TypeError("Application paths cannot contain fragments");
  }

  const queryIndex = relativePath.indexOf("?");
  const pathname = queryIndex === -1 ? relativePath : relativePath.slice(0, queryIndex);

  if (pathname.startsWith("/") || pathname.startsWith("\\") || SCHEME.test(pathname)) {
    throw new TypeError("Application paths must be relative");
  }

  for (const segment of pathname.split("/")) {
    const decoded = fullyDecodeSegment(segment);
    if (decoded === "." || decoded === ".." || decoded.includes("/") || decoded.includes("\\")) {
      throw new TypeError("Application paths cannot escape their assigned root");
    }
    if (decoded.includes("\0")) {
      throw new TypeError("Application paths cannot contain null bytes");
    }
  }

  return relativePath;
}

export function applicationRouteBasePath(teamId: string, applicationId: string): string {
  return `/team/${encodeURIComponent(teamId)}/apps/${encodeURIComponent(applicationId)}`;
}

export function applicationServiceUrl(applicationId: string, teamId: string, relativePath: string): string {
  const normalized = normalizeApplicationRelativePath(relativePath);
  const queryIndex = normalized.indexOf("?");
  const pathname = queryIndex === -1 ? normalized : normalized.slice(0, queryIndex);
  const query = queryIndex === -1 ? "" : normalized.slice(queryIndex);
  const root = `/app-services/${encodeURIComponent(applicationId)}/teams/${encodeURIComponent(teamId)}`;
  return `${root}/${pathname}${query}`;
}

export function applicationRouteTarget(basePath: string, relativePath: string): string {
  const normalized = normalizeApplicationRelativePath(relativePath);
  const queryIndex = normalized.indexOf("?");
  const pathname = queryIndex === -1 ? normalized : normalized.slice(0, queryIndex);
  const query = queryIndex === -1 ? "" : normalized.slice(queryIndex);
  return pathname ? `${basePath}/${pathname}${query}` : `${basePath}${query}`;
}
