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

export type MessageSender = "user" | "assistant" | "system";
export type MessageType = "human" | "ai" | "system" | "tool";

export interface FredMetadata {
  node?: string;
  agentic_flow?: string;
  expert_description?: string;
  task_number?: string;
  task?: string;
}

export interface ChatTokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

export type ChatMessageSubtype = "final" | "thought" | "tool_result" | "plan" | "execution" | "observation" | "error" | "injected_context";

export interface ChatSource {
  document_uid: string;
  file_url?: string;
  file_name: string;
  agent_name: string;
  title: string;
  author: string;
  content: string;
  created: string;
  type: string;
  modified: string;
  score: number;
}

export interface ChatMessagePayload {
  exchange_id: string;
  type: MessageType;
  subtype?: ChatMessageSubtype;
  sender: MessageSender;
  content: string;
  timestamp: string;
  session_id: string;
  rank: number;
  metadata?: {
    model?: string;
    token_usage?: ChatTokenUsage;
    sources?: ChatSource[];
    fred?: FredMetadata;
    [key: string]: unknown;
  };
}

export interface SessionSchema {
  id: string;
  user_id: string;
  title: string;
  updated_at: string;
}

export interface StreamEvent {
  type: "stream";
  message: ChatMessagePayload;
}

export interface FinalEvent {
  type: "final";
  messages: ChatMessagePayload[];
  session: SessionSchema;
}

export interface ErrorEvent {
  type: "error";
  content: string;
  session_id?: string;
}

export type ChatEvent = StreamEvent | FinalEvent | ErrorEvent;

export const agentTypes = ["mcp"] as const;
export type AgentType = typeof agentTypes[number];

export const mcpTransports = ["sse"] as const;
export type McpTransport = typeof mcpTransports[number];

export interface McpServer {
  name: string;
  url: string;
  transport?: McpTransport; // default "sse"
  sse_read_timeout?: number;
}

export interface CreateAgentRequest {
  agent_type: AgentType;
  name: string;
  nickname?: string;
  description?: string;
  role?: string;
  base_prompt?: string;
  icon?: string;
  mcp_servers?: McpServer[];
  categories?: string[];
}

export interface CreateAgentResponse {
  success: boolean;
}
