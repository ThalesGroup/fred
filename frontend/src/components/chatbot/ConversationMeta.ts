// Copyright Thales 2025
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

/**
 * This module centralizes the conversation metadata structure used across the chatbot components.
 */

import type { SessionPreferencesPayload } from "../../slices/agentic/agenticOpenApi.ts";
import type { RuntimeContext } from "../../slices/agentic/agenticOpenApi.ts";
import type { SearchPolicyName } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi.ts";

type SearchRagScope = NonNullable<RuntimeContext["search_rag_scope"]>;

export type ConversationMetaInput = {
  sessionId?: string;
  effectiveSessionId?: string;
  agentName?: string;
  agentSupportsAttachments: boolean;
  isSessionPrefsReady: boolean;
  deepSearchEnabled: boolean;
  attachmentCount: number;
  selectedChatContextIds?: string[];
  documentLibraryIds?: string[];
  promptResourceIds?: string[];
  templateResourceIds?: string[];
  librariesSelectionEnabled: boolean;
  librariesCount: number;
  searchPolicy?: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  sessionPreferences?: SessionPreferencesPayload;
};

export type ConversationMeta = {
  sessionId?: string;
  effectiveSessionId?: string;
  agentName?: string;
  agentSupportsAttachments: boolean;
  isSessionPrefsReady: boolean;
  deepSearchEnabled: boolean;
  attachments: {
    count: number;
  };
  chatContext: {
    selectedIds: string[];
    selectedCount: number;
  };
  libraries: {
    selectionEnabled: boolean;
    selectedCount: number;
    selectedIds: string[];
  };
  prompts: {
    selectedCount: number;
    selectedIds: string[];
  };
  templates: {
    selectedCount: number;
    selectedIds: string[];
  };
  searchPolicy?: SearchPolicyName;
  searchRagScope?: SearchRagScope;
  sessionPreferences?: SessionPreferencesPayload;
};

export const createConversationMeta = (input: ConversationMetaInput): ConversationMeta => {
  const selectedChatContextIds = input.selectedChatContextIds ?? [];
  const documentLibraryIds = input.documentLibraryIds ?? [];
  const promptResourceIds = input.promptResourceIds ?? [];
  const templateResourceIds = input.templateResourceIds ?? [];

  return {
    sessionId: input.sessionId,
    effectiveSessionId: input.effectiveSessionId,
    agentName: input.agentName,
    agentSupportsAttachments: input.agentSupportsAttachments,
    isSessionPrefsReady: input.isSessionPrefsReady,
    deepSearchEnabled: input.deepSearchEnabled,
    attachments: {
      count: input.attachmentCount,
    },
    chatContext: {
      selectedIds: [...selectedChatContextIds],
      selectedCount: selectedChatContextIds.length,
    },
    libraries: {
      selectionEnabled: input.librariesSelectionEnabled,
      selectedCount: input.librariesCount,
      selectedIds: [...documentLibraryIds],
    },
    prompts: {
      selectedCount: promptResourceIds.length,
      selectedIds: [...promptResourceIds],
    },
    templates: {
      selectedCount: templateResourceIds.length,
      selectedIds: [...templateResourceIds],
    },
    searchPolicy: input.searchPolicy,
    searchRagScope: input.searchRagScope,
    sessionPreferences: input.sessionPreferences,
  };
};
