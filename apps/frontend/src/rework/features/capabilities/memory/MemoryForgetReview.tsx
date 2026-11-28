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
import { useTranslation } from "react-i18next";
import { useAgentMemoryQuery } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import type { CapabilityHitlRendererProps } from "../types";
import styles from "./MemoryRememberReview.module.css";
import { useChatAgentScope } from "./useChatAgentScope";

/** The forget gate's arguments hold only the note id: the approval card looks
 * the note up so the person sees which note would go. */
export function MemoryForgetReview({ call }: CapabilityHitlRendererProps) {
  const { t } = useTranslation();
  const { spaceId, agentInstanceId } = useChatAgentScope();
  let noteId: string | null = null;
  try {
    const args = JSON.parse(call.args_preview ?? "") as { note_id?: unknown };
    noteId = typeof args.note_id === "string" ? args.note_id : null;
  } catch {
    noteId = null;
  }
  const { currentData } = useAgentMemoryQuery(
    { spaceId: spaceId ?? "", agentInstanceId: agentInstanceId ?? "" },
    { skip: !spaceId || !agentInstanceId || !noteId },
  );
  const content = currentData?.notes.find((note) => note.note_id === noteId)?.content;
  if (!content) return null;
  return <span className={styles.note}>{t("capability.memory.approval.forget", { content })}</span>;
}
