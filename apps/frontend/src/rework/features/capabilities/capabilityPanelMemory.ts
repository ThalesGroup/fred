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

// Which capability panels were left open, per conversation — what
// `CapabilitySidePanelHost` restores from. Closed is the default, so every
// access can degrade to "not open" rather than throw: the degraded answer is
// the default answer. localStorage, like the drawer width already stored there
// — a UI preference, not conversation content. Rationale: COMPONENT-UX.md.

const STORAGE_KEY = "capability-panel:open";
const MAX_ENTRIES = 50;

/** `${sessionId}|${capabilityId}:${widget}` — one open panel in one conversation. */
const entryFor = (sessionId: string, panelKey: string): string => `${sessionId}|${panelKey}`;

// Insertion order is LRU order, oldest first: delete-then-push on write keeps
// the array's head the least recently used entry.
function read(): string[] {
  try {
    const parsed: unknown = JSON.parse(localStorage.getItem(STORAGE_KEY) ?? "[]");
    return Array.isArray(parsed) ? parsed.filter((v): v is string => typeof v === "string") : [];
  } catch {
    return [];
  }
}

function write(entries: string[]): void {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(entries.slice(-MAX_ENTRIES)));
  } catch {
    // Best-effort: a full or blocked storage just means panels stop being
    // restored, which is the default behaviour anyway — never an error.
  }
}

export function rememberPanelOpen(sessionId: string, panelKey: string): void {
  const entry = entryFor(sessionId, panelKey);
  write([...read().filter((v) => v !== entry), entry]);
}

export function rememberPanelClosed(sessionId: string, panelKey: string): void {
  const entry = entryFor(sessionId, panelKey);
  const entries = read();
  if (entries.includes(entry)) write(entries.filter((v) => v !== entry));
}

export function wasPanelOpen(sessionId: string, panelKey: string): boolean {
  return read().includes(entryFor(sessionId, panelKey));
}
