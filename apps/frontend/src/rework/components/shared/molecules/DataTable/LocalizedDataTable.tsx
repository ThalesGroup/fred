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
import DataTable, { type DataTableProps } from "./DataTable.tsx";
export type { DataTableColumn, ServerPagination, SortState, SortDirection, DataTableRowSize } from "./DataTable.tsx";

export default function LocalizedDataTable<T>(props: DataTableProps<T>) {
  const { t } = useTranslation();
  return (
    <DataTable
      {...props}
      labels={{
        selectAllOnPage: t("dataTable.selection.selectAllOnPage"),
        selectRow: t("dataTable.selection.selectRow"),
        pagination: {
          totalItems: (count) => t("dataTable.pagination.totalItems", { count }),
          itemsPerPage: t("dataTable.pagination.itemsPerPage"),
          pageNumber: (page, pageCount) => t("dataTable.pagination.pageNumber", { page, pageCount }),
          first: t("dataTable.pagination.first"),
          prev: t("dataTable.pagination.prev"),
          next: t("dataTable.pagination.next"),
          last: t("dataTable.pagination.last"),
        },
        ...props.labels,
      }}
    />
  );
}
