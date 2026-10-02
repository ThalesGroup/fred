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

import {
  Button,
  Checkbox,
  Dialog,
  TextArea,
  InlineDrawer,
  IconButton,
  Select,
  type SelectOption,
} from "@fred-oss/ui";

const badButton = (
  // @ts-expect-error xs is intentionally unsupported by the packaged Button.
  <Button color="primary" variant="filled" size="xs">
    Bad
  </Button>
);
const badIconButton = (
  <IconButton
    variant="icon"
    // @ts-expect-error xs is intentionally unsupported by the packaged IconButton.
    size="xs"
    icon={{ type: "close" }}
    aria-label="Bad"
  />
);

const badOption: SelectOption<number> = {
  key: "bad",
  value: 1,
  label: "Bad",
  // @ts-expect-error Package options support only the approved Outlined glyph inventory.
  icon: { type: "customAgent" },
};
const badSelect = (
  <Select
    // @ts-expect-error Generic Select onChange receives the option value type, not an unrelated string.
    options={[{ key: "one", value: 1, label: "One" }]}
    size="medium"
    onChange={(value: string) => value}
  />
);
const badDialog = (
  // @ts-expect-error Action-oriented Dialog requires a caller-owned confirm label.
  <Dialog open title="Bad" onConfirm={() => {}} onCancel={() => {}}>
    Bad
  </Dialog>
);
const badCheckbox = (
  // @ts-expect-error Native checked state is Boolean.
  <Checkbox checked="yes" />
);

export {
  badButton,
  badIconButton,
  badOption,
  badSelect,
  badDialog,
  badCheckbox,
};

import {
  StatusBadge,
  ServiceNotice,
  PageEmptyState,
  Switch,
  DataTable,
  KpiStatCard,
  TablePagination,
  ToastProvider,
  type DataTableColumn,
} from "@fred-oss/ui";

// @ts-expect-error Tones are a closed domain-neutral union.
const badBadge = <StatusBadge label="Bad" tone="completed" />;
// @ts-expect-error Custom application icons are outside the package.
const badNotice = <ServiceNotice icon="customAgent" title="Bad" />;
// @ts-expect-error Unsupported material glyphs are rejected.
const badEmpty = <PageEmptyState icon="imaginary_icon" message="Bad" />;
// @ts-expect-error Only implemented switch sizes are supported.
const badSwitch = <Switch size="large" />;
const badColumn: DataTableColumn<{ id: number }> = {
  label: "Bad",
  // @ts-expect-error Row renderers retain their generic row type.
  cellRenderer: (row: string) => row,
};
const badTable = (
  // @ts-expect-error Table row keys are string or number, never an arbitrary object.
  <DataTable data={[{ id: 1 }]} columns={[]} rowKey={(row) => row} />
);
const badPagination = (
  <TablePagination
    totalItems={1}
    currentPage={0}
    pageCount={1}
    rowsPerPage={1}
    // @ts-expect-error Numeric pagination options cannot contain string values.
    rowsPerPageOptions={[{ key: "bad", label: "Bad", value: "one" }]}
    onFirst={() => {}}
    onPrev={() => {}}
    onNext={() => {}}
    onLast={() => {}}
  />
);
const badToast = (
  <ToastProvider
    // @ts-expect-error Copy receives text, not an event or numeric value.
    onCopy={(value: number) => {
      void value;
    }}
  >
    Bad
  </ToastProvider>
);
export {
  badBadge,
  badNotice,
  badEmpty,
  badSwitch,
  badColumn,
  badTable,
  badPagination,
  badToast,
};

const badRowActivation = (
  <DataTable<{ id: string }>
    data={[]}
    columns={[]}
    // @ts-expect-error The row callback retains the table row type.
    onRowClick={(row: number) => void row}
  />
);
const badKpiTone = (
  <KpiStatCard
    label="Bad"
    // @ts-expect-error KPI tones share the supported status vocabulary.
    tone="purple"
    isLoading={false}
    isError={false}
  />
);
export { badRowActivation, badKpiTone };

const badRemDrawer = (
  // @ts-expect-error Resizable drawers require pixel widths, not relative CSS units.
  <InlineDrawer
    open
    onClose={() => {}}
    title="Bad"
    width="30rem"
    resizable={{ persistKey: "bad" }}
  />
);
const badPercentDrawer = (
  // @ts-expect-error Percentage widths cannot seed persisted pixel widths.
  <InlineDrawer
    open
    onClose={() => {}}
    title="Bad"
    width="50%"
    resizable={{ persistKey: "bad" }}
  />
);
const badViewportDrawer = (
  // @ts-expect-error Viewport widths cannot seed persisted pixel widths.
  <InlineDrawer
    open
    onClose={() => {}}
    title="Bad"
    width="30vw"
    resizable={{ persistKey: "bad" }}
  />
);
export { badRemDrawer, badPercentDrawer, badViewportDrawer };

const uncontrolledTextArea = (
  // @ts-expect-error TextArea requires a controlled value for its character counter.
  <TextArea label="Notes" defaultValue="abc" maxLength={100} />
);
const missingTextAreaValue = (
  // @ts-expect-error Empty controlled TextAreas must use value="".
  <TextArea label="Notes" maxLength={100} />
);
export { uncontrolledTextArea, missingTextAreaValue };

const selectableTableWithoutKeys = (
  // @ts-expect-error Selection requires stable row keys for page-wide actions.
  <DataTable data={[{ id: 1 }]} columns={[]} selectable />
);
export { selectableTableWithoutKeys };

export function dynamicSelectionContract(selectable: boolean) {
  const missingKeys = (
    // @ts-expect-error A dynamic selection flag also requires stable keys.
    <DataTable data={[{ id: 1 }]} columns={[]} selectable={selectable} />
  );
  const keyed = (
    <DataTable
      data={[{ id: 1 }]}
      columns={[]}
      selectable={selectable}
      rowKey={(row) => row.id}
    />
  );
  const nonSelectable = (
    <DataTable data={[{ id: 1 }]} columns={[]} selectable={false} />
  );
  return { missingKeys, keyed, nonSelectable };
}

// @ts-expect-error Switch always renders a checkbox; callers cannot override its type.
export const badSwitchType = <Switch type="text" />;
