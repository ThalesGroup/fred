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

/** Fixed gateway routes; SQL registration and access belong to Control Plane. */
export function loadApplicationProxyConfig(controlPlaneUpstream) {
  if (process.env.FRONTEND_APPLICATIONS_JSON !== undefined || process.env.FRONTEND_ENABLE_APPLICATIONS !== undefined) {
    throw new Error(
      "Applications are managed via Admin > Applications; remove FRONTEND_APPLICATIONS_JSON and FRONTEND_ENABLE_APPLICATIONS",
    );
  }
  return Object.fromEntries(
    ["apps", "app-services"].map((prefix) => [
      `^/${prefix}(?:[/?]|$)`,
      { target: controlPlaneUpstream, changeOrigin: true, secure: true, timeout: 180000, proxyTimeout: 180000 },
    ]),
  );
}
