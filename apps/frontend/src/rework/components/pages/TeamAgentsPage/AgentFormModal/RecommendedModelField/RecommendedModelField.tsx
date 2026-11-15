// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { useTranslation } from "react-i18next";
import Select, { type SelectOption } from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { modelChoiceKey, parseModelChoice } from "@rework/features/capabilities/modelChoice";
import { useSpaceModelsQuery, type ModelOfferKey } from "../../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./RecommendedModelField.module.css";

interface RecommendedModelFieldProps {
  teamId?: string;
  value: ModelOfferKey | null;
  onChange: (value: ModelOfferKey | null) => void;
  disabled?: boolean;
}

/** The same space projection drives configuration and fresh turn admission. */
export function RecommendedModelField({ teamId, value, onChange, disabled }: RecommendedModelFieldProps) {
  const { t } = useTranslation();
  const query = useSpaceModelsQuery({ spaceId: teamId ?? "" }, { skip: !teamId, refetchOnMountOrArgChange: true });
  if (query.isError)
    return <ServiceNotice icon="cloud_off" title={t("rework.teams.formAgent.fields.recommendedModel.loadError")} />;
  const models = query.currentData?.models;
  const selected = value ? modelChoiceKey(value) : "";
  const rows = models?.offers.filter((offer) => offer.selectable) ?? [];
  const unavailable = value !== null && !rows.some((offer) => modelChoiceKey(offer.key) === selected);
  const options: SelectOption<string>[] = [
    {
      key: "default",
      value: "",
      label: t("rework.teams.formAgent.fields.recommendedModel.teamDefault"),
      description: models?.default
        ? `${models.default.upstream_model_id} (${models.default.source_id})`
        : t("rework.spaceModels.noDefault"),
    },
    ...rows.map((offer) => ({
      key: modelChoiceKey(offer.key),
      value: modelChoiceKey(offer.key),
      label: `${offer.metadata?.display_name ?? offer.key.upstream_model_id} (${offer.key.source_id})`,
    })),
    ...(unavailable
      ? [
          {
            key: selected,
            value: selected,
            label: `${value.upstream_model_id} (${value.source_id}) - ${t("rework.spaceModels.unavailable")}`,
            disabled: true,
          },
        ]
      : []),
  ];
  return (
    <div className={styles.field}>
      <Select
        size="medium"
        label={t("rework.teams.formAgent.fields.recommendedModel.label")}
        value={selected}
        options={options}
        onChange={(next) => onChange(next ? parseModelChoice(next) : null)}
        disabled={disabled || !models || query.isFetching}
      />
      <p className={styles.hint}>{t("rework.spaceModels.agentHint")}</p>
    </div>
  );
}
