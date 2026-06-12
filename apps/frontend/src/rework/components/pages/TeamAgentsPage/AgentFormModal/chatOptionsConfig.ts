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

import type { ManagedAgentFieldSpec } from "../../../../../slices/controlPlane/controlPlaneOpenApi";

export const CHAT_OPTION_FIELD_KEYS = {
  attachFiles: "chat_options.attach_files",
  librariesBinding: "chat_options.libraries_binding",
  librariesSelection: "chat_options.libraries_selection",
  boundLibraryIds: "chat_options.bound_library_ids",
  searchPolicyEnabled: "chat_options.search_policy_enabled",
  searchPolicy: "chat_options.search_policy",
  searchRagScopeEnabled: "chat_options.search_rag_scope_enabled",
  searchRagScope: "chat_options.search_rag_scope",
} as const;

export const CHAT_OPTION_CONFIG_KEYS = Object.values(CHAT_OPTION_FIELD_KEYS);

export type ChatOptionConfigKey = (typeof CHAT_OPTION_CONFIG_KEYS)[number];
export type ChatRagScope = "corpus_only" | "hybrid" | "general_only";

export function isChatOptionConfigKey(value: string): value is ChatOptionConfigKey {
  return CHAT_OPTION_CONFIG_KEYS.includes(value as ChatOptionConfigKey);
}

export function isChatOptionField(field: ManagedAgentFieldSpec): boolean {
  return isChatOptionConfigKey(field.key);
}

export function serverCarriesChatOptions(fields: ManagedAgentFieldSpec[]): boolean {
  const serverScopedKeys = new Set<string>([
    CHAT_OPTION_FIELD_KEYS.librariesBinding,
    CHAT_OPTION_FIELD_KEYS.librariesSelection,
    CHAT_OPTION_FIELD_KEYS.searchPolicyEnabled,
    CHAT_OPTION_FIELD_KEYS.searchPolicy,
    CHAT_OPTION_FIELD_KEYS.searchRagScopeEnabled,
    CHAT_OPTION_FIELD_KEYS.searchRagScope,
  ]);
  return fields.some((field) => serverScopedKeys.has(field.key));
}
