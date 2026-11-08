// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import { useTranslation } from "react-i18next";
import Select from "@shared/molecules/Select/Select";
import { useMySpacesQuery } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";

interface PromptSpaceSelectProps {
  value: string | undefined;
  onChange: (spaceId: string) => void;
  disabled: boolean;
}

export function PromptSpaceSelect({ value, onChange, disabled }: PromptSpaceSelectProps) {
  const { t } = useTranslation();
  const context = useMySpacesQuery(undefined, { refetchOnMountOrArgChange: true });
  const spaces = context.isError ? [] : (context.currentData ?? []);
  return (
    <Select
      size="medium"
      label={t("rework.selftest.families.prompts.spaceLabel")}
      placeholder={t("rework.selftest.families.prompts.spacePlaceholder")}
      emptyMessage={t("rework.selftest.families.prompts.spaceEmpty")}
      error={context.isError ? t("rework.selftest.families.prompts.spaceUnavailable") : undefined}
      value={value}
      onChange={onChange}
      disabled={disabled || context.isFetching || context.isError}
      options={spaces.map((space) => ({
        key: space.id,
        value: space.id,
        label: `${spaces.find((item) => item.id === space.organization_id)?.name ?? space.organization_id} / ${space.name}`,
        description: `${t(`rework.userSettings.spaceKinds.${space.kind}`)} | ${space.id}`,
        section: space.organization_id,
      }))}
    />
  );
}
