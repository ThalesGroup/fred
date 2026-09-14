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

import { normalizeApplicationRelativePath } from "./applicationProtocol.ts";

export { normalizeApplicationRelativePath } from "./applicationProtocol.ts";

export function applicationRouteBasePath(teamId: string, applicationId: string): string {
  return `/team/${encodeURIComponent(teamId)}/apps/${encodeURIComponent(applicationId)}`;
}

/**
 * The one destination an application may ask the host to open.
 *
 * It takes no caller-supplied path: the team comes from the host's own route
 * and the surface is fixed here, so the set of places a frame can send the
 * user is decided in review rather than at runtime. The agents surface is the
 * target rather than a conversation, because a chat route needs an agent
 * instance id the application has no business knowing.
 */
export function applicationChatRouteTarget(teamId: string): string {
  return `/team/${encodeURIComponent(teamId)}/agents`;
}

/**
 * Resume one conversation the caller already owns.
 *
 * Never call this with an id straight off the wire: the host resolves the
 * agent instance from its own session listing, so both segments here come
 * from data the caller is entitled to rather than from the frame.
 */
/**
 * Start a fresh conversation with one of the team's agents.
 *
 * The instance id comes from the host's own listing, never from the frame —
 * same rule as the resume target below.
 */
export function applicationNewChatTarget(teamId: string, agentInstanceId: string): string {
  return `/team/${encodeURIComponent(teamId)}/managed-chat/${encodeURIComponent(agentInstanceId)}`;
}

export function applicationChatSessionTarget(teamId: string, agentInstanceId: string, sessionId: string): string {
  const base = `/team/${encodeURIComponent(teamId)}/managed-chat/${encodeURIComponent(agentInstanceId)}`;
  return `${base}?session=${encodeURIComponent(sessionId)}`;
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
