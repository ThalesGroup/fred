// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0

import ConsumptionUsage, { type ConsumptionQuery } from "./ConsumptionUsage";
import { useTranslation } from "react-i18next";
import Disclosure from "@shared/atoms/Disclosure/Disclosure";
import SkillUsageTable from "@shared/molecules/SkillUsageTable/SkillUsageTable";

export default function PersonalUsage({
  organizationId,
  usage,
  skills,
  withSkills,
}: {
  organizationId?: string;
  usage: ConsumptionQuery;
  skills: ConsumptionQuery;
  withSkills: boolean;
}) {
  const { t } = useTranslation();
  if (!organizationId)
    return (
      <>
        <Disclosure title={t("rework.teamUsage.personalSectionTitle")} defaultOpen>
          <p role="status">{t("rework.personalAnalytics.organizationRequired")}</p>
        </Disclosure>
        {withSkills && (
          <Disclosure title={t("rework.teamUsage.personalSkillsSectionTitle")} defaultOpen>
            <p role="status">{t("rework.personalAnalytics.organizationRequired")}</p>
          </Disclosure>
        )}
      </>
    );
  const skillResult = !withSkills || skills.isError ? undefined : skills.currentData?.results.skills;
  const skillRows = skillResult?.rows.flatMap((row) =>
    row.dimensions.kind === "skill"
      ? [
          {
            skill_name: row.dimensions.name,
            user_count: BigInt(row.values["skills.user_loads"]),
            model_count: BigInt(row.values["skills.agent_loads"]),
            total: BigInt(row.values["skills.total_loads"]),
          },
        ]
      : [],
  );
  return (
    <>
      {withSkills && (
        <Disclosure title={t("rework.teamUsage.personalSkillsSectionTitle")} defaultOpen>
          <SkillUsageTable
            agentLabel={t("rework.personalAnalytics.agent")}
            data={skillRows ? { rows: skillRows, truncated: skillResult?.truncated } : undefined}
            isLoading={skills.isLoading || (skills.isFetching && !skillResult)}
            isError={skills.isError}
          />
          {!skills.isError && skillResult && <p>{t("rework.personalAnalytics.observed")}</p>}
        </Disclosure>
      )}
      <ConsumptionUsage title={t("rework.teamUsage.personalSectionTitle")} usage={usage} />
    </>
  );
}
