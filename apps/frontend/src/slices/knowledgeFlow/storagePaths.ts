/**
 * Central helpers for knowledge-flow storage path handling.
 *
 * Agent config storage lives under: agents/{agentId}/config/{key}
 * Agent-user storage: agents/{agentId}/users/{userId}/{key}
 * User storage: users/{userId}/{key}
 */

export const agentConfigPrefix = (agentId: string) => `agents/${agentId}/config/`;

export function stripAgentConfigPrefix(fullPath: string, agentId: string): string {
  const prefix = agentConfigPrefix(agentId);
  if (fullPath.startsWith(prefix)) {
    return fullPath.slice(prefix.length);
  }
  return fullPath;
}
