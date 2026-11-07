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

import type { WikiPageDetail } from "../../../slices/controlPlane/controlPlaneOpenApi";

/**
 * What the editor opens on for the rules page.
 *
 * The starting draft is offered only before the team has ever saved this page —
 * `revision_id` is null until the first write, which is exactly that condition.
 * Emptiness is NOT the test: a page saved empty was emptied on purpose, and
 * handing the template back would undo that decision every time it is reopened.
 *
 * Nothing is written until the editor saves, so a team that never opens this
 * page keeps no rules at all — and agents are told about rules the team
 * actually wrote, never about a default nobody chose.
 */
export function rulesDraft(detail: WikiPageDetail, template: string): string {
  return detail.revision_id ? detail.content_md : template;
}
