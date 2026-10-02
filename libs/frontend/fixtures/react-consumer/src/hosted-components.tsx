// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.
import { useState } from "react";
import {
  Breadcrumb,
  DataTable,
  Disclosure,
  FileDropzone,
  IndicatorDot,
  InlineDrawer,
  KpiStatCard,
  PageEmptyState,
  PageHeader,
  ProgressBar,
  SelectableCard,
  ServiceNotice,
  StatusBadge,
  Switch,
  TablePagination,
  TextArea,
  Toast,
  ToastProvider,
  useToast,
} from "@fred-oss/ui";
import type {
  BreadcrumbProps,
  BreadcrumbSegment,
  DataTableColumn,
  DataTableLabels,
  DataTableProps,
  DataTableRowSize,
  DisclosureProps,
  FileDropzoneProps,
  IndicatorDotProps,
  IndicatorStatus,
  InlineDrawerProps,
  InlineDrawerResizeSpec,
  KpiStatCardProps,
  PageEmptyStateAction,
  PageEmptyStateProps,
  PageHeaderProps,
  ProgressBarProps,
  SelectableCardProps,
  ServerPagination,
  ServiceNoticeProps,
  SortDirection,
  SortState,
  StatusBadgeProps,
  StatusBadgeTone,
  SwitchProps,
  SwitchSize,
  TablePaginationLabels,
  TablePaginationProps,
  TextAreaProps,
  ToastActions,
  ToastContextValue,
  ToastData,
  ToastInput,
  ToastProps,
  ToastProviderProps,
  ToastSeverity,
} from "@fred-oss/ui";

// Every added public type must resolve from the installed archive.
export type HostedContracts = [
  BreadcrumbProps,
  BreadcrumbSegment,
  DataTableColumn<Row>,
  DataTableLabels,
  DataTableProps<Row>,
  DataTableRowSize,
  DisclosureProps,
  FileDropzoneProps,
  IndicatorDotProps,
  IndicatorStatus,
  InlineDrawerProps,
  InlineDrawerResizeSpec,
  KpiStatCardProps,
  PageEmptyStateAction,
  PageEmptyStateProps,
  PageHeaderProps,
  ProgressBarProps,
  SelectableCardProps,
  ServerPagination,
  ServiceNoticeProps,
  SortDirection,
  SortState,
  StatusBadgeProps,
  StatusBadgeTone,
  SwitchProps,
  SwitchSize,
  TablePaginationLabels,
  TablePaginationProps,
  TextAreaProps,
  ToastActions,
  ToastContextValue,
  ToastData,
  ToastInput,
  ToastProps,
  ToastProviderProps,
  ToastSeverity,
];
type Row = { id: number; name: string };
const rows: Row[] = Array.from({ length: 25 }, (_, index) => ({
  id: index + 1,
  name: `Row ${index + 1}`,
}));
const columns: DataTableColumn<Row>[] = [
  {
    label: "Record",
    cellRenderer: (row) => row.name,
    sortable: true,
    sortValue: (row) => row.id,
  },
];
const labels: Partial<TablePaginationLabels> = {
  totalItems: (count) => `${count} records`,
  pageNumber: (page, pageCount) => `${page}/${pageCount}`,
  first: "Start records",
  prev: "Previous records",
  next: "Next records",
  last: "End records",
};
function ToastTriggers() {
  const toast = useToast();
  return (
    <>
      <button
        type="button"
        onClick={() => {
          toast.showError({
            summary: "Hosted error",
            detail: "Copy this detail",
          });
          toast.showError({ summary: "Second error" });
        }}
      >
        Show hosted errors
      </button>
      <button
        type="button"
        onClick={() =>
          toast.showInfo({ summary: "Timed notification", duration: 500 })
        }
      >
        Show timed toast
      </button>
    </>
  );
}
export function HostedComponents() {
  const [text, setText] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [selected, setSelected] = useState(false);
  const [keys, setKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [file, setFile] = useState("");
  const [drawer, setDrawer] = useState(false);
  const [drawerGeneration, setDrawerGeneration] = useState(0);
  const [overlay, setOverlay] = useState(false);
  const [copied, setCopied] = useState("");
  const [standalone, setStandalone] = useState(true);
  const [page, setPage] = useState(0);
  return (
    <section aria-label="Hosted application components" data-hosted>
      <PageHeader
        title="Hosted evaluations"
        subtitle="Neutral components"
        breadcrumb={
          <Breadcrumb
            segments={[
              { label: "Home", onClick: () => setSelected(false) },
              { label: "Evaluations" },
            ]}
          />
        }
      />
      <TextArea
        id="evaluation-notes"
        label="Evaluation notes"
        value={text}
        onChange={(event) => setText(event.currentTarget.value)}
        maxLength={50}
      />
      <Switch
        aria-label="Enable evaluation"
        checked={enabled}
        onChange={(event) => setEnabled(event.currentTarget.checked)}
      />
      <Switch aria-label="Disabled switch" disabled />
      <ProgressBar theme="primary" current={3} max={10} />
      <IndicatorDot status="active" label="Evaluation active" />
      <Disclosure title="Case details">
        <span>Expanded case content</span>
      </Disclosure>
      <SelectableCard
        selected={selected}
        title="Choose suite"
        description="A reusable suite"
        onSelect={() => setSelected((value) => !value)}
      />
      <FileDropzone
        accept=".json"
        hint="Upload suite"
        onFile={(value) => setFile(value.name)}
      />
      <output data-upload>{file}</output>
      <ServiceNotice
        icon="cloud_off"
        title="Service unavailable"
        description="Caller-owned explanation"
      />
      <PageEmptyState
        icon="description"
        message="No evaluations"
        action={{
          label: "Create evaluation",
          onClick: () => setSelected(true),
        }}
      />
      {(["success", "error", "warning", "info", "neutral"] as const).map(
        (tone) => (
          <div key={tone} data-badge={tone}>
            <StatusBadge tone={tone} label={tone} />
          </div>
        ),
      )}
      <KpiStatCard
        label="Completed runs"
        value={12}
        delta={2}
        isLoading={false}
        isError={false}
      />
      <KpiStatCard
        label="Loading runs"
        isLoading
        isError={false}
        loadingLabel="Fetching runs"
      />
      <KpiStatCard
        label="Failed runs"
        isLoading={false}
        isError
        errorLabel="Could not fetch runs"
      />
      <KpiStatCard
        label="Unavailable runs"
        unavailable
        isLoading={false}
        isError={false}
        noDataLabel="No run data"
      />
      <div className="hosted-table">
        <DataTable
          columns={columns}
          data={rows}
          selectable
          rowKey={(row) => row.id}
          selectedKeys={keys}
          onSelectionChange={setKeys}
          pageSize={20}
          labels={{
            selectAllOnPage: "Select visible records",
            selectRow: "Select record",
            pagination: labels,
          }}
        />
      </div>
      <output data-selection>{keys.size}</output>
      <TablePagination
        totalItems={3}
        currentPage={page}
        pageCount={3}
        rowsPerPage={1}
        rowsPerPageOptions={[{ key: "one", value: 1, label: "One" }]}
        onFirst={() => setPage(0)}
        onPrev={() => setPage(page - 1)}
        onNext={() => setPage(page + 1)}
        onLast={() => setPage(2)}
        labels={{
          next: "Standalone next",
          pageNumber: (number) => `Standalone ${number}`,
        }}
      />
      <button type="button" onClick={() => setDrawer(true)}>
        Open push drawer
      </button>
      <div className="hosted-drawer">
        <InlineDrawer
          key={drawerGeneration}
          title="Hosted drawer"
          open={drawer}
          onClose={() => setDrawer(false)}
          layout="push"
          width="320px"
          resizable={{ persistKey: "hosted-fixture", maxViewportFraction: 0.8 }}
        >
          <span>Drawer content</span>
        </InlineDrawer>
      </div>
      <button
        type="button"
        onClick={() => setDrawerGeneration((value) => value + 1)}
      >
        Remount drawer
      </button>
      <button type="button" onClick={() => setOverlay(true)}>
        Open overlay drawer
      </button>
      <InlineDrawer
        title="Hosted overlay"
        open={overlay}
        onClose={() => setOverlay(false)}
      >
        <span>Overlay content</span>
      </InlineDrawer>
      <ToastProvider
        onCopy={setCopied}
        copyLabel="Copy notification"
        dismissLabel="Dismiss notification"
      >
        <ToastTriggers />
      </ToastProvider>
      <output data-copied>{copied}</output>
      {standalone && (
        <Toast
          id={100}
          severity="success"
          summary="Direct toast"
          duration={null}
          exiting={false}
          onClose={() => setStandalone(false)}
          onExited={() => {}}
          dismissLabel="Dismiss direct toast"
        />
      )}
    </section>
  );
}
