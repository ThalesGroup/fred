// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import TextArea from "@shared/atoms/TextArea/TextArea";
import { TEAM_DESCRIPTION_MAX_LENGTH, TEAM_DESCRIPTION_MIN_LENGTH } from "@core/utils/teamFields";

/** The required team or project description with its length rule, shared by settings and project creation. */
export default function TeamDescriptionField({
  project,
  value,
  disabled,
  invalid,
  onChange,
}: {
  project: boolean;
  value: string;
  disabled: boolean;
  /** Shows the length rule as an error. */
  invalid: boolean;
  onChange: (value: string) => void;
}) {
  const { t } = useTranslation();
  const label = (teamKey: string, projectKey: string) =>
    t(project ? `rework.projectParameters.${projectKey}` : teamKey);
  const length = t("rework.teamDescription.length", {
    min: TEAM_DESCRIPTION_MIN_LENGTH,
    max: TEAM_DESCRIPTION_MAX_LENGTH,
  });
  return (
    <TextArea
      label={label("rework.teamDescription.label", "description.label")}
      placeholder={label("rework.teamSettings.parameters.description.placeholder", "description.placeholder")}
      explanation={length}
      value={value}
      rows={7}
      required
      disabled={disabled}
      error={invalid ? length : undefined}
      onChange={(event) => onChange(event.target.value)}
    />
  );
}
