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

import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import Button from "@shared/atoms/Button/Button";
import TextInput from "@shared/atoms/TextInput/TextInput";
import Select from "@shared/molecules/Select/Select";
import ServiceNotice from "@shared/molecules/ServiceNotice/ServiceNotice";
import type { OptionModel } from "@models/Option.model.ts";
import { StatusPill } from "./EvaluationShared";
import { useListEvaluationsQuery } from "../../../../../../../slices/evaluation/evaluationApiEnhancements";
import styles from "./Evaluations.module.css";

interface EvaluationsProps {
  teamId: string;
  onNewEvaluation: () => void;
  onOpenEvaluation: (evaluationId: string, name: string) => void;
}

// One page holds enough to scan without scrolling forever; the server enforces its
// own ceiling (limit ≤ 200), so this stays well within it.
const PAGE_SIZE = 25;

type SortValue = "created_at:desc" | "created_at:asc" | "name:asc";

export default function Evaluations({ teamId, onNewEvaluation, onOpenEvaluation }: EvaluationsProps) {
  const { t } = useTranslation();

  const [search, setSearch] = useState("");
  const [debouncedSearch, setDebouncedSearch] = useState("");
  const [sort, setSort] = useState<SortValue>("created_at:desc");
  const [offset, setOffset] = useState(0);

  // Debounce the search box so each keystroke doesn't fire a request.
  useEffect(() => {
    const id = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(id);
  }, [search]);

  // Any change to the filter or sort invalidates the current page offset —
  // otherwise you could land on "page 5" of a result set that now has one page.
  useEffect(() => {
    setOffset(0);
  }, [debouncedSearch, sort]);

  const { data, isLoading, isError, isFetching } = useListEvaluationsQuery(
    { teamId, q: debouncedSearch || undefined, sort, offset, limit: PAGE_SIZE },
    { skip: !teamId },
  );

  const evaluations = data?.evaluations ?? [];
  const total = data?.total ?? 0;
  const pageCount = Math.max(1, Math.ceil(total / PAGE_SIZE));
  const currentPage = Math.floor(offset / PAGE_SIZE) + 1;

  const sortOptions: OptionModel<SortValue>[] = [
    { value: "created_at:desc", key: "newest", label: t("rework.evaluation.controls.sort.newest") },
    { value: "created_at:asc", key: "oldest", label: t("rework.evaluation.controls.sort.oldest") },
    { value: "name:asc", key: "name", label: t("rework.evaluation.controls.sort.name") },
  ];

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

      <div className={styles.toolbar}>
        <div className={styles.toolbarSearch}>
          <TextInput
            icon={{ category: "outlined", type: "search" }}
            placeholder={t("rework.evaluation.controls.searchEvaluations")}
            value={search}
            onChange={(e) => setSearch(e.target.value)}
          />
        </div>
        <Select<SortValue>
          size="medium"
          options={sortOptions}
          value={sort}
          onChange={(value) => setSort(value)}
          label={t("rework.evaluation.controls.sortLabel")}
        />
      </div>

      {isLoading && <p className={styles.muted}>{t("common.loading")}</p>}

      {!isLoading && evaluations.length === 0 && (
        <ServiceNotice icon="database" title={t("rework.evaluation.evaluations.empty")} centered />
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

      {!isLoading && total > PAGE_SIZE && (
        <div className={styles.pagination}>
          <span>{t("rework.evaluation.controls.page", { current: currentPage, total: pageCount })}</span>
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            disabled={offset === 0 || isFetching}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            {t("rework.evaluation.controls.prev")}
          </Button>
          <Button
            color="on-surface"
            variant="outlined"
            size="small"
            disabled={currentPage >= pageCount || isFetching}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            {t("rework.evaluation.controls.next")}
          </Button>
        </div>
      )}
    </div>
  );
}
