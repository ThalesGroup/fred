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
import IconButton from "@shared/atoms/IconButton/IconButton.tsx";
import styles from "./ResourcePagination.module.css";

interface ResourcePaginationProps {
  offset: number;
  limit: number;
  total: number;
  onPrev: () => void;
  onNext: () => void;
}

/** Offset/limit/total pagination: "page x / y" with prev/next, disabled at the ends. */
export function ResourcePagination({ offset, limit, total, onPrev, onNext }: ResourcePaginationProps) {
  const { t } = useTranslation();
  const page = Math.floor(offset / limit) + 1;
  const pageCount = Math.max(1, Math.ceil(total / limit));
  const atStart = offset <= 0;
  const atEnd = offset + limit >= total;

  return (
    <div className={styles.pagination}>
      <IconButton
        color="on-surface"
        variant="icon"
        size="xs"
        icon={{ category: "outlined", type: "chevron_left" }}
        aria-label={t("rework.resources.pagination.prev")}
        disabled={atStart}
        onClick={onPrev}
      />
      <span className={styles.label}>{t("rework.resources.pagination.page", { page, pageCount })}</span>
      <IconButton
        color="on-surface"
        variant="icon"
        size="xs"
        icon={{ category: "outlined", type: "chevron_right" }}
        aria-label={t("rework.resources.pagination.next")}
        disabled={atEnd}
        onClick={onNext}
      />
    </div>
  );
}
