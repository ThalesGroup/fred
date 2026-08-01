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

// Pure helpers shared by the two managed-agent runtime stream consumers: the chat
// SSE hook (`core/hooks/useChatSse`) and the hook-free pipeline self-test path
// (`features/pipeline/actions`). Kept dependency-free (no React, RTK Query, or
// Keycloak) so both paths share one frame reader and one context-merge rule and
// cannot drift apart when runtime event handling changes.

import type { RuntimeContext, TeamOperationRouteRule } from "../../../slices/runtime/runtimeOpenApi";

/**
 * Iterate the JSON `data:` frames of a runtime/ingestion SSE response body.
 *
 * Buffers chunks, splits on the SSE record boundary (`\n\n`), takes the first
 * `data: ` line of each record, and yields the parsed JSON. `[DONE]` sentinels
 * and empty frames are skipped; non-JSON frames (heartbeats, comments) are
 * ignored, with the raw payload handed to `onParseError` when provided so a
 * caller can log a genuine anomaly without coupling this helper to a logger.
 *
 * Generic over the frame shape: chat passes its `AnyRuntimeEvent` union, the
 * pipeline path uses the default `Record<string, unknown>`.
 */
export async function* parseSseFrames<T = Record<string, unknown>>(
  body: ReadableStream<Uint8Array>,
  onParseError?: (raw: string) => void,
): AsyncGenerator<T> {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buf = "";
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const blocks = buf.split("\n\n");
      buf = blocks.pop() ?? "";
      for (const block of blocks) {
        const dataLine = block.split("\n").find((l) => l.startsWith("data: "));
        const raw = dataLine?.slice(6).trim();
        if (!raw || raw === "[DONE]") continue;
        try {
          yield JSON.parse(raw) as T;
        } catch {
          onParseError?.(raw);
        }
      }
    }
  } finally {
    reader.releaseLock();
  }
}

/**
 * Fold the prepared `context_prompt_text` (resolved by control-plane
 * prepare-execution) onto a base runtime context. The key is only set when a
 * value is present, so an absent prompt never overwrites the context with null.
 *
 * Typed against the generated `RuntimeContext`, so a rename of the field on the
 * runtime contract breaks both stream consumers at compile time instead of only
 * the chat path.
 */
export function mergeContextPromptText(
  base: Partial<RuntimeContext>,
  contextPromptText: string | null | undefined,
): RuntimeContext {
  return {
    ...base,
    ...(contextPromptText != null ? { context_prompt_text: contextPromptText } : {}),
  };
}

/**
 * Fold the team's routing-policy snapshot (resolved by control-plane
 * prepare-execution from its stored `TeamRoutingPolicy`,
 * `TEAM-ROUTING-POLICY-RFC.md` §8.2) onto a base runtime context — same
 * "resolved once per session, forwarded unchanged per turn" contract as
 * `mergeContextPromptText` above, same reason: a key is only set when a
 * value is present, so an absent policy never overwrites the context with
 * null/empty.
 *
 * Typed against the generated `RuntimeContext`, so a rename of either field
 * on the runtime contract breaks both stream consumers at compile time
 * instead of only the chat path.
 */
export function mergeRoutingPolicy(
  base: Partial<RuntimeContext>,
  chatDefaultProfileId: string | null | undefined,
  operationRouteRules: TeamOperationRouteRule[] | null | undefined,
): RuntimeContext {
  return {
    ...base,
    ...(chatDefaultProfileId != null ? { chat_default_profile_id: chatDefaultProfileId } : {}),
    ...(operationRouteRules != null && operationRouteRules.length > 0
      ? { operation_route_rules: operationRouteRules }
      : {}),
  };
}

/**
 * Fold the platform reasoning activation (resolved by control-plane
 * prepare-execution, `MODEL-REASONING-ENABLEMENT-RFC.md` §5.5) onto a base
 * runtime context — same "resolved once per session, forwarded unchanged per
 * turn" contract as the two helpers above.
 *
 * Kept separate from `mergeRoutingPolicy` on purpose: this is not routing.
 * Routing decides WHICH model answers; this decides whether that model reasons.
 * The two are independent axes and folding them into one helper would suggest
 * otherwise.
 *
 * Unlike the helpers above, an EMPTY list is forwarded rather than omitted.
 * Empty is meaningful here — "no model reasons" — and it costs nothing to be
 * explicit about it, where reading an absent key as "unrestricted" (the
 * `usable_model_ids` convention) would be exactly backwards. The runtime treats
 * absent and empty identically, so this is belt and braces, not a behaviour.
 */
export function mergeReasoningActivation(
  base: Partial<RuntimeContext>,
  reasoningEnabledModelIds: string[] | null | undefined,
): RuntimeContext {
  return {
    ...base,
    ...(reasoningEnabledModelIds != null ? { reasoning_enabled_model_ids: reasoningEnabledModelIds } : {}),
  };
}
