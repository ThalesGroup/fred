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
  InlineDrawer,
  TextArea,
  ToastProvider,
  type DataTableColumn,
  type SortState,
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
const badSelection = (
  <DataTable
    data={[{ id: 1 }]}
    columns={[]}
    rowKey={(row) => row.id}
    // @ts-expect-error Row selection is not part of the hosted table contract.
    selectable
  />
);
const badDrawerLayout = (
  // @ts-expect-error Push, resize and floating layouts stay FRED-internal.
  <InlineDrawer open title="Bad" onClose={() => {}} layout="push" />
);
export {
  badBadge,
  badNotice,
  badEmpty,
  badSwitch,
  badColumn,
  badTable,
  badSelection,
  badDrawerLayout,
};

const badRowActivation = (
  <DataTable<{ id: string }>
    data={[]}
    columns={[]}
    rowKey={(row) => row.id}
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
const uncontrolledTextArea = (
  // @ts-expect-error Hosted TextArea is controlled: value and onChange are required.
  <TextArea label="Notes" maxLength={50} />
);
const badToastCopy = (
  // @ts-expect-error The copy action is not part of the hosted toast contract.
  <ToastProvider copyLabel="Copy">Bad</ToastProvider>
);
const ascending: SortState = { columnLabel: "Id", direction: "asc" };
const loneSortState = (
  // @ts-expect-error Controlled sorting requires sortState and onSortChange together.
  <DataTable data={[{ id: 1 }]} columns={[]} sortState={ascending} />
);
export {
  badRowActivation,
  badKpiTone,
  uncontrolledTextArea,
  badToastCopy,
  loneSortState,
};

const invalidDialogScroll = (
  // @ts-expect-error Only body or child-owned scrolling is supported.
  <Dialog
    open
    title="Bad"
    confirmLabel="Done"
    scrollMode="none"
    onConfirm={() => {}}
    onCancel={() => {}}
  >
    Text
  </Dialog>
);
export { invalidDialogScroll };
