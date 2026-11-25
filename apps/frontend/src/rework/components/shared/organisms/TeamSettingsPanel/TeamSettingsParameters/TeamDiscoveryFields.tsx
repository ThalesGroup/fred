// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Select from "@shared/molecules/Select/Select";
import type { TeamJoiningMode, TeamVisibility } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";

/** Visibility and joining mode of a team or project, shared by its settings and project creation. */
export default function TeamDiscoveryFields({
  project,
  visibility,
  joiningMode,
  disabled,
  onVisibilityChange,
  onJoiningModeChange,
}: {
  project: boolean;
  visibility?: TeamVisibility;
  joiningMode?: TeamJoiningMode;
  disabled: boolean;
  onVisibilityChange: (value: TeamVisibility) => void;
  onJoiningModeChange: (value: TeamJoiningMode) => void;
}) {
  const { t } = useTranslation();
  const label = (teamKey: string, projectKey: string) =>
    t(project ? `rework.projectParameters.${projectKey}` : teamKey);
  return (
    <>
      <Select<TeamVisibility>
        size="medium"
        label={label("rework.teamDiscovery.visibility", "visibility")}
        value={visibility}
        disabled={disabled}
        options={(["hidden", "visible"] as const).map((value) => ({
          key: value,
          value,
          label: label(`rework.teamDiscovery.${value}`, value),
        }))}
        onChange={onVisibilityChange}
      />
      <Select<TeamJoiningMode>
        size="medium"
        label={t("rework.teamDiscovery.joiningMode")}
        value={joiningMode}
        disabled={disabled}
        options={(["invite_only", "open"] as const).map((value) => ({
          key: value,
          value,
          label: value === "open" ? label("rework.teamDiscovery.open", "open") : t(`rework.teamDiscovery.${value}`),
        }))}
        onChange={onJoiningModeChange}
      />
      {visibility === "hidden" && joiningMode === "open" && (
        <span>{label("rework.teamDiscovery.hiddenOpenHint", "hiddenOpenHint")}</span>
      )}
    </>
  );
}
