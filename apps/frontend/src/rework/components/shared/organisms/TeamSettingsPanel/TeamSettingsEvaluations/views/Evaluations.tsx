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

// The Evaluation list — the entry point of the two-noun model (RFC
// AGENT-EVALUATION §8.5). An Evaluation is the versioned, reusable case set;
// opening one shows its Runs. Creating one never starts a run.

import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import { StatusPill } from "./EvaluationShared";
import { useListEvaluationsEvaluationV1EvaluationsGetQuery } from "../../../../../../../slices/evaluation/evaluationOpenApi";
import styles from "./Evaluations.module.css";

interface EvaluationsProps {
  teamId: string;
  onNewEvaluation: () => void;
  onOpenEvaluation: (evaluationId: string, name: string) => void;
}

export default function Evaluations({ teamId, onNewEvaluation, onOpenEvaluation }: EvaluationsProps) {
  const { t } = useTranslation();

  const { data, isLoading, isError } = useListEvaluationsEvaluationV1EvaluationsGetQuery({ teamId }, { skip: !teamId });

  const evaluations = data?.evaluations ?? [];

  if (isError) {
    return (
      <div className={styles.page}>
        <ServiceNotice
          icon="cloud_off"
          title={t("rework.serviceNotice.evaluationService.title")}
          description={t("rework.serviceNotice.evaluationService.description")}
          centered
        />
      </div>
    );
  }

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <div>
          <h1 className={styles.title}>{t("rework.evaluation.evaluations.title")}</h1>
          <p className={styles.subtitle}>{t("rework.evaluation.evaluations.description")}</p>
        </div>
        <Button color="primary" variant="filled" size="medium" onClick={onNewEvaluation}>
          {t("rework.evaluation.evaluations.new")}
        </Button>
      </div>

      {isLoading && <p className={styles.muted}>{t("common.loading")}</p>}

      {!isLoading && evaluations.length === 0 && (
        <PageEmptyState
          icon="database"
          message={t("rework.evaluation.evaluations.empty")}
          action={{ label: t("rework.evaluation.evaluations.new"), onClick: onNewEvaluation }}
        />
      )}

      {!isLoading && evaluations.length > 0 && (
        <div className={styles.table} role="table">
          <div className={`${styles.row} ${styles.headerRow}`} role="row">
            <span>{t("rework.evaluation.evaluations.col.name")}</span>
            <span>{t("rework.evaluation.evaluations.col.version")}</span>
            <span>{t("rework.evaluation.evaluations.col.author")}</span>
            <span>{t("rework.evaluation.evaluations.col.origin")}</span>
            <span>{t("rework.evaluation.evaluations.col.cases")}</span>
            <span />
          </div>

          {evaluations.map((evaluation) => (
            <div
              key={evaluation.evaluation_id}
              className={`${styles.row} ${styles.bodyRow}`}
              role="row"
              tabIndex={0}
              onClick={() => onOpenEvaluation(evaluation.evaluation_id, evaluation.name)}
              onKeyDown={(e) => {
                if (e.key === "Enter") onOpenEvaluation(evaluation.evaluation_id, evaluation.name);
              }}
            >
              <div>
                <div className={styles.name}>{evaluation.name}</div>
                <div className={styles.mono}>{evaluation.evaluation_id.slice(0, 12)}</div>
              </div>
              <StatusPill label={evaluation.version} tone="info" />
              <span className={styles.muted}>{evaluation.author}</span>
              <span className={styles.muted}>{t(`rework.evaluation.evaluations.origin.${evaluation.origin}`)}</span>
              <span className={styles.muted}>
                {t("rework.evaluation.evaluations.caseCount", { count: evaluation.case_count })}
              </span>
              <div className={styles.actionsCell} onClick={(e) => e.stopPropagation()}>
                <Button
                  color="on-surface"
                  variant="outlined"
                  size="small"
                  onClick={() => onOpenEvaluation(evaluation.evaluation_id, evaluation.name)}
                >
                  {t("rework.evaluation.evaluations.openRuns")}
                </Button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
