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

export interface ApplicationServiceProxyTarget {
  target: string;
  changeOrigin: true;
  secure: true;
  rewrite: (requestPath: string) => string;
}

export interface ApplicationServiceProxyConfig {
  proxy: Record<string, ApplicationServiceProxyTarget>;
  classifyRequest: (requestUrl: string) => "proxy" | 404 | 503 | null;
}

export function rewriteApplicationServicePath(requestPath: string, applicationId: string): string;

export function parseApplicationServicesEnabled(rawValue?: string): boolean;

export function loadApplicationServiceProxyConfig(options: {
  contractPath: string;
  mappingsJson?: string;
  requireRequiredMappings?: boolean;
  enabled?: boolean;
}): ApplicationServiceProxyConfig;
