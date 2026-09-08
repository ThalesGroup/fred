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

export const APPLICATION_UI_PREFIX: "/apps";
export const APPLICATION_SERVICE_PREFIX: "/app-services";

export interface ApplicationRegistration {
  app_id: string;
  ui_upstream: string;
  service_upstream: string | null;
  service_required: boolean;
}

export interface ApplicationProxyTarget {
  target: string;
  changeOrigin: true;
  secure: true;
  rewrite: (requestPath: string) => string;
}

export interface ApplicationProxyConfig {
  proxy: Record<string, ApplicationProxyTarget>;
  classifyRequest: (requestUrl: string) => "proxy" | 404 | 503 | null;
}

export function parseApplicationRegistrations(registrationsJson?: string): ApplicationRegistration[];

export function rewriteApplicationUiPath(requestPath: string, applicationId: string): string;

export function rewriteApplicationServicePath(requestPath: string, applicationId: string): string;

export function parseApplicationsEnabled(rawValue?: string): boolean;

export function loadApplicationProxyConfig(options: {
  registrationsJson?: string;
  requireServiceUpstreams?: boolean;
  enabled?: boolean;
}): ApplicationProxyConfig;
