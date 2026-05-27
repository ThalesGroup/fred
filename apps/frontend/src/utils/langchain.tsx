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

// Messages are the inputs and outputs of ChatModels.
export interface BaseMessage {
  /**
   * The string contents of the message.
   */
  content: string | Array<string> | Record<string, any>;

  /**
   * Reserved for additional payload data associated with the message.
   * For example, for a message from an AI, this could include tool calls as
   * encoded by the model provider.
   */
  additional_kwargs: Record<string, any>;

  /**
   * Response metadata.
   * For example: response headers, logprobs, token counts.
   */
  response_metadata?: Record<string, any>;

  /**
   * The type of the message. Must be a string that is unique to the message type.
   * The purpose of this field is to allow for easy identification of the message type
   * when deserializing messages.
   */
  type: string;

  /**
   * An optional name for the message.
   * This can be used to provide a human-readable name for the message.
   * Usage of this field is optional, and whether it's used or not is up to the
   * model implementation.
   */
  name?: string;

  /**
   * An optional unique identifier for the message.
   * This should ideally be provided by the provider/model which created the message.
   */
  id?: string;
}

/**
 * Message for printing AI behavior.
 * The system message is usually passed in as the first of a sequence of input messages.
 */
export interface SystemMessage extends BaseMessage {
  /**
   * The type of the message (used for serialization). Defaults to "system".
   */
  type: "system";
}

export interface ErrorMessage extends BaseMessage {
  type: "error";
}

/**
 * Message from a human.
 * HumanMessages are messages that are passed in from a human to the model.
 */
export interface HumanMessage extends BaseMessage {
  /**
   * The type of the message (used for serialization). Defaults to "human".
   */
  type: "human";

  /**
   * Use to denote that a message is part of an example conversation.
   * At the moment, this is ignored by most models. Usage is discouraged.
   * Defaults to False.
   */
  example: boolean;
}

// Represents a request to call a tool.
export interface ToolCall {
  /**
   * The name of the tool to be called.
   */
  name: string;

  /**
   * The arguments to the tool call.
   */
  args: Record<string, any>;

  /**
   * An identifier associated with the tool call.
   * An identifier is needed to associate a tool call request with a tool
   * call result in events when multiple concurrent tool calls are made.
   */
  id?: string;

  /**
   * The type of the tool call. Defaults to "tool_call".
   */
  type?: "tool_call";
}

/**
 * Allowance for errors made by LLM.
 *
 * Here we add an `error` key to surface errors made during generation
 * (e.g., invalid JSON arguments.)
 */
export interface InvalidToolCall {
  /**
   * The name of the tool to be called.
   */
  name?: string;

  /**
   * The arguments to the tool call.
   */
  args?: string;

  /**
   * An identifier associated with the tool call.
   */
  id?: string;

  /**
   * An error message associated with the tool call.
   */
  error?: string;

  /**
   * The type of the invalid tool call. Defaults to "invalid_tool_call".
   */
  type?: "invalid_tool_call";
}

/**
 * Usage metadata for a message, such as token counts.
 *
 * This is a standard representation of token usage that is consistent across models.
 *
 * Example:
 *
 * {
 *   "input_tokens": 10,
 *   "output_tokens": 20,
 *   "total_tokens": 30
 * }
 */
export interface UsageMetadata {
  /**
   * Count of input (or prompt) tokens.
   */
  input_tokens: number;

  /**
   * Count of output (or completion) tokens.
   */
  output_tokens: number;

  /**
   * Total token count.
   */
  total_tokens: number;
}

/**
 * Message from an AI.
 *
 * AIMessage is returned from a chat model as a response to a prompt.
 *
 * This message represents the output of the model and consists of both
 * the raw output as returned by the model together standardized fields
 * (e.g., tool calls, usage metadata) added by the LangChain framework.
 */
export interface AIMessage extends BaseMessage {
  /**
   * The type of the message (used for serialization). Defaults to "ai".
   */
  type: "ai";

  /**
   * Use to denote that a message is part of an example conversation.
   *
   * At the moment, this is ignored by most models. Usage is discouraged.
   */
  example: boolean;

  /**
   * If provided, tool calls associated with the message.
   */
  tool_calls?: ToolCall[];

  /**
   * If provided, tool calls with parsing errors associated with the message.
   */
  invalid_tool_calls?: InvalidToolCall[];

  /**
   * If provided, usage metadata for a message, such as token counts.
   *
   * This is a standard representation of token usage that is consistent across models.
   */
  usage_metadata?: UsageMetadata;
}

/**
 * Message for passing the result of executing a tool back to a model.
 *
 * ToolMessages contain the result of a tool invocation. Typically, the result
 * is encoded inside the `content` field.
 *
 * The `tool_call_id` field is used to associate the tool call request with the
 * tool call response. This is useful in situations where a chat model is able
 * to request multiple tool calls in parallel.
 */
export interface ToolMessage extends BaseMessage {
  /**
   * Tool call that this message is responding to.
   */
  tool_call_id: string;

  /**
   * The type of the message (used for serialization). Defaults to "tool".
   */
  type: "tool";

  /**
   * Artifact of the Tool execution which is not meant to be sent to the model.
   *
   * Should only be specified if it is different from the message content, e.g., if only
   * a subset of the full tool output is being passed as message content but the full
   * output is needed in other parts of the code.
   *
   * Version added: 0.2.17
   */
  artifact?: any;

  /**
   * Status of the tool invocation.
   *
   * Version added: 0.2.24
   */
  status: "success" | "error";
}
