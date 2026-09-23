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

// Retrieves the .pptx template one agent instance already carries.
//
// This file is the ONE place the frontend knows where an agent's config assets
// live. The path is the runtime's convention (`AgentConfigAssetsAdapter`), which
// the SDK deliberately keeps private from capabilities, so it is mirrored here
// once and pinned on BOTH sides: this module's test and the Python test over
// `_config_path` assert the same literal, so changing either alone fails a suite
// instead of 404-ing in the browser.
// Full rationale: openspec/changes/add-ppt-filler-template-download/design.md.

import { KeyCloakService } from "../../../../security/KeycloakService";
import { personalTeamId } from "@shared/utils/teamId";
import { downloadAuthed } from "../../../../utils/downloadUtils";

/** Mirrors `PPT_FILLER_TEMPLATE_KEY`: one template per instance, fixed key. */
export const PPT_FILLER_TEMPLATE_KEY = "ppt_filler_template.pptx";

/**
 * Percent-encodes each segment the way the runtime's own KF client does
 * (`quote(path, safe="/")`): `encodeURI` would leave `#`, `?` and `&` raw, and
 * the `/fs/download/{path:path}` route carries a real `token` query param — a
 * raw `?` in an id would silently truncate the path into a query string.
 */
function encodePath(segments: string[]): string {
  return segments.map(encodeURIComponent).join("/");
}

/**
 * Where the runtime stored this instance's config assets. Bearer-protected and
 * team-membership-gated by Knowledge Flow, so the caller's own token authorizes
 * the read — no platform identity, no extra rule.
 *
 * `teamId` may be the bare `"personal"` route alias; KF checks ReBAC against the
 * canonical `personal-<uid>`, so the alias is resolved here. Only the BARE
 * alias: an id that is already canonical is passed through untouched, as the
 * repo's other two `/fs` call sites do — rebuilding it from the session's uid
 * would discard a correct id to re-derive it, and yield `personal-` if the uid
 * were ever unavailable.
 */
export function storedTemplateUrl(teamId: string, agentInstanceId: string): string {
  const fsTeamId = teamId === "personal" ? personalTeamId(KeyCloakService.GetUserId() ?? "") : teamId;
  const path = encodePath(["teams", fsTeamId, "agents", agentInstanceId, "config", PPT_FILLER_TEMPLATE_KEY]);
  return `/knowledge-flow/v1/fs/download/${path}`;
}

/**
 * The uploaded file's own name was never stored, so every template would
 * otherwise land as `ppt_filler_template.pptx` — identical for every agent.
 * Naming it after the agent keeps two downloads apart.
 */
export function templateFileName(agentDisplayName?: string): string {
  const cleaned = (agentDisplayName ?? "")
    .replace(/[^\p{L}\p{N} ._-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim()
    .replace(/\.pptx$/i, "")
    .trim();
  return cleaned ? `${cleaned}.pptx` : PPT_FILLER_TEMPLATE_KEY;
}

/**
 * Raised when the agent's config carries a template but the file is gone.
 * Duplicating an agent produces exactly that: the copy inherits the slide
 * schema (the pod's save path passes a no-upload edit straight through) while
 * the bytes stay with the original. The administrator needs "upload it again",
 * not "download failed".
 */
export class StoredTemplateMissingError extends Error {}

export async function downloadStoredTemplate(
  teamId: string,
  agentInstanceId: string,
  agentDisplayName?: string,
): Promise<void> {
  try {
    await downloadAuthed(storedTemplateUrl(teamId, agentInstanceId), templateFileName(agentDisplayName));
  } catch (err) {
    // `fetchAuthedBlob` reports the status in its message and nothing else.
    if (err instanceof Error && /\(404\)/.test(err.message)) {
      throw new StoredTemplateMissingError(err.message);
    }
    throw err;
  }
}
