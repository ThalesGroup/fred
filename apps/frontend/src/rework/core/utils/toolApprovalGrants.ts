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

const PREFIX = "chat.tool-approvals.v1:";

export interface ToolApprovalGrantScope {
  userId: string | null;
  agentInstanceId: string;
  sessionId: string;
}

function storageKey(scope: ToolApprovalGrantScope): string | null {
  if (!scope.userId || !scope.agentInstanceId || !scope.sessionId) return null;
  return PREFIX + JSON.stringify([scope.userId, scope.agentInstanceId, scope.sessionId]);
}

function validToolName(value: unknown): value is string {
  return typeof value === "string" && value.length > 0 && value.length <= 256 && value === value.trim();
}

export function readToolApprovalGrants(scope: ToolApprovalGrantScope): string[] {
  const key = storageKey(scope);
  if (!key) return [];
  try {
    const raw = localStorage.getItem(key);
    if (!raw || raw.length > 32768) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed) || parsed.length > 256 || !parsed.every(validToolName)) return [];
    return parsed;
  } catch {
    return [];
  }
}

export function rememberToolApprovalGrants(scope: ToolApprovalGrantScope, toolNames: string[]): boolean {
  const key = storageKey(scope);
  if (!key || toolNames.length === 0 || !toolNames.every(validToolName)) return false;
  try {
    const names = new Set([...readToolApprovalGrants(scope), ...toolNames]);
    localStorage.setItem(key, JSON.stringify([...names]));
    return true;
  } catch {
    return false;
  }
}

export function hasToolApprovalGrants(scope: ToolApprovalGrantScope, toolNames: string[]): boolean {
  if (toolNames.length === 0 || !toolNames.every(validToolName)) return false;
  const grants = new Set(readToolApprovalGrants(scope));
  return toolNames.every((name) => grants.has(name));
}

export function clearToolApprovalGrants(scope: ToolApprovalGrantScope): void {
  const key = storageKey(scope);
  if (!key) return;
  try {
    localStorage.removeItem(key);
  } catch {
    // Browser storage is best effort; the deleted session ID cannot be reused.
  }
}
