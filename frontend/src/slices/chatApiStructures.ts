export type MessageSender = "user" | "assistant" | "system";
export type MessageType = "human" | "ai" | "system" | "tool";

export interface FredMetadata {
  node?: string,
  agentic_flow?: string,
  expert_description?: string,
  task_number?: string,
  task?: string,
}

export interface ChatTokenUsage {
  input_tokens: number;
  output_tokens: number;
  total_tokens: number;
}

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
  id: string;
  type: MessageType;
  sender: MessageSender;
  content: string;
  timestamp: string;
  session_id: string;
  rank?: number;
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
