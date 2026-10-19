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

import { downloadAuthed } from "../../../common/downloadAuthed";
import type { ExportConversationFileApiArg } from "../../../slices/runtime/runtimeOpenApi";

/** Binary response: use the generated request contract with the session's captured runtime route. */
export function downloadConversationFile(baseUrl: string, args: ExportConversationFileApiArg, signal: AbortSignal) {
  const query = new URLSearchParams({ path: args.path, format: args.format ?? "docx" });
  if (args.teamId) query.set("team_id", args.teamId);
  const url = `${baseUrl}/agents/sessions/${encodeURIComponent(args.sessionId)}/filesystem/export?${query}`;
  const stem =
    args.path
      .split("/")
      .pop()!
      .replace(/\.[^.]+$/, "")
      .replace(/[^a-zA-Z0-9_.-]/g, "_") || "document";
  return downloadAuthed(url, `${stem}.${args.format ?? "docx"}`, signal);
}
