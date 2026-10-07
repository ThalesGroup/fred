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

const EXECUTE_STREAM_SUFFIX = "/agents/execute/stream";
const CANONICAL_PATH = /^\/[A-Za-z0-9._~/-]+$/;

export function runtimeExecuteStreamPath(candidate: string): string {
  if (
    !CANONICAL_PATH.test(candidate) ||
    candidate.includes("//") ||
    candidate.split("/").some((segment) => segment === "." || segment === "..") ||
    !candidate.endsWith(EXECUTE_STREAM_SUFFIX) ||
    candidate === EXECUTE_STREAM_SUFFIX
  ) {
    throw new Error("Invalid runtime execution URL");
  }

  const resolved = new URL(candidate, window.location.origin);
  if (resolved.origin !== window.location.origin || resolved.pathname !== candidate) {
    throw new Error("Invalid runtime execution URL");
  }
  return candidate;
}
