// src/types/prefs.ts

import { SearchPolicyName } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";

/** Global user settings shared by all conversations */
export type UserPrefs = {
  systemPrompt: string;
};

/**
 * Per-agent preferences you persist locally.
 * (Kept explicit for clarity; mirrors what you'll later send as runtime_context.)
 */
export type AgentPrefs = {
  selected_document_libraries_ids: string[]; // default: []
  search_policy: SearchPolicyName | null; // "hybrid" | "semantic" | "strict" | null
};

/** Per-session metadata (which agent is used by that session) */
export type SessionPrefs = {
  agentId: string; // the agent_name string
};
