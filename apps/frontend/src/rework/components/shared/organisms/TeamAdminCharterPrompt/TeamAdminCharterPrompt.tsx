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

import { useCallback, useState } from "react";
import { useTranslation } from "react-i18next";
import { Dialog } from "@shared/molecules/Dialog/Dialog";
import TeamAdminCharterContent from "@shared/molecules/TeamAdminCharterContent/TeamAdminCharterContent.tsx";
import {
  useAcceptTeamAdminCharterMutation,
  useTeamAdminCharterStatusQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements.ts";

/** Asks a team admin to accept the charter when the app loads. "Later" only closes it
 *  until the next load: the server keeps admin-only permissions off until acceptance. */
export default function TeamAdminCharterPrompt() {
  const { t } = useTranslation();
  const { data: status } = useTeamAdminCharterStatusQuery();
  const [acceptCharter, { isLoading }] = useAcceptTeamAdminCharterMutation();
  const [dismissed, setDismissed] = useState(false);
  const [endReached, setEndReached] = useState(false);
  const handleEndReached = useCallback(() => setEndReached(true), []);

  if (!status?.required || dismissed) return null;

  return (
    <Dialog
      open
      title={t("rework.teamAdminCharter.title")}
      confirmLabel={t("rework.teamAdminCharter.accept")}
      cancelLabel={t("rework.teamAdminCharter.later")}
      confirmDisabled={!endReached || isLoading}
      onConfirm={() => void acceptCharter()}
      onCancel={() => setDismissed(true)}
      maxWidth={660}
    >
      <TeamAdminCharterContent onEndReached={handleEndReached} />
    </Dialog>
  );
}
