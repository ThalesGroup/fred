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
import { useLsQuery } from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";

interface FsRootMetaProps {
  /** Team-rooted base path for the area (its top level). */
  root: string;
  /** Optional nature prefix (e.g. "private · personal"); the count is appended after it. */
  nature?: string;
}

/**
 * Discreet nature marker for one /fs root row: an optional nature label plus a light count
 * ("empty" when the root has no entries). Keeps empty areas to a one-word mention rather
 * than a large empty block.
 */
export default function FsRootMeta({ root, nature }: FsRootMetaProps) {
  const { t } = useTranslation();
  const { data } = useLsQuery({ path: root });
  const count = Array.isArray(data) ? (data as unknown[]).length : 0;
  const countLabel = count === 0 ? t("rework.resources.roots.empty") : t("rework.resources.roots.fileCount", { count });
  return <>{nature ? `${nature} · ${countLabel}` : countLabel}</>;
}
