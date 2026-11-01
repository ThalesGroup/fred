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

import { useRef } from "react";
import { useTranslation } from "react-i18next";
import { useApiErrorToast } from "@core/hooks/useApiErrorToast.ts";
import {
  useAddPromptFavoriteMutation,
  useRemovePromptFavoriteMutation,
} from "../../../slices/controlPlane/controlPlaneApiEnhancements";

/** Stars or unstars a prompt of `spaceId` for the caller. The listings update
 *  after the acknowledged write; failures are surfaced without local divergence. */
export function usePromptFavoriteToggle(spaceId: string | undefined) {
  const { t } = useTranslation();
  const { notifyApiError } = useApiErrorToast();
  const [addFavorite] = useAddPromptFavoriteMutation();
  const [removeFavorite] = useRemovePromptFavoriteMutation();
  // A second click before the first answers would race it on the server.
  const inFlight = useRef(new Set<string>());

  return async (prompt: { prompt_id: string; is_favorite?: boolean }) => {
    if (!spaceId || inFlight.current.has(prompt.prompt_id)) return;
    inFlight.current.add(prompt.prompt_id);
    const arg = { spaceId, promptId: prompt.prompt_id };
    try {
      await (prompt.is_favorite ? removeFavorite(arg) : addFavorite(arg)).unwrap();
    } catch (error) {
      notifyApiError(error, {
        summary: t("rework.teams.prompts.favorite.errorSummary"),
        fallbackDetail: t("rework.teams.prompts.favorite.errorDetail"),
      });
    } finally {
      inFlight.current.delete(prompt.prompt_id);
    }
  };
}
