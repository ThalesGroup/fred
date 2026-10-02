// Copyright Thales 2026
// Licensed under the Apache License, Version 2.0.
import { useState } from "react";
import { createPortal } from "react-dom";
import {
  Breadcrumb,
  DataTable,
  Disclosure,
  Dialog,
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
const identityRows = [{ id: 2 }, { id: 1 }, { id: 3 }];
export function HostedComponents() {
  const [text, setText] = useState("");
  const [enabled, setEnabled] = useState(false);
  const [selected, setSelected] = useState(false);
  const [keys, setKeys] = useState<ReadonlySet<string | number>>(new Set());
  const [submissions, setSubmissions] = useState(0);
  const [activations, setActivations] = useState(0);
  const [uploads, setUploads] = useState(0);
  const [file, setFile] = useState("");
  const [nestedDialog, setNestedDialog] = useState(false);
  const [notesError, setNotesError] = useState(false);
  const [drawer, setDrawer] = useState(false);
  const [drawerGeneration, setDrawerGeneration] = useState(0);
  const [overlay, setOverlay] = useState(false);
  const [overlayDialog, setOverlayDialog] = useState(false);
  const [wideOverlay, setWideOverlay] = useState(false);
  const [lowerClicks, setLowerClicks] = useState(0);
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
        error={notesError ? "Invalid evaluation notes" : undefined}
        explanation="Describe the evaluation"
      />
      <button type="button" onClick={() => setNotesError((value) => !value)}>
        Toggle notes error
      </button>
      <form data-native-notes>
        <TextArea label="Native notes" defaultValue="Bonjour" maxLength={50} />
        <button type="reset">Reset native notes</button>
      </form>
      <Switch
        className="consumer-switch"
        aria-label="Enable evaluation"
        checked={enabled}
        onChange={(event) => setEnabled(event.currentTarget.checked)}
      />
      <Switch
        className="consumer-switch"
        aria-label="Disabled switch"
        disabled
      />
      <ProgressBar
        theme="primary"
        current={3}
        max={10}
        aria-label="Evaluation progress"
      />
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
        onFile={(value) => {
          setFile(value.name);
          setUploads((count) => count + 1);
        }}
      />
      <output data-upload data-upload-count={uploads}>
        {file}
      </output>
      <ServiceNotice
        icon="cloud_off"
        title="Service unavailable"
        description="Caller-owned explanation"
      />
      <form
        onSubmit={(event) => {
          event.preventDefault();
          setSubmissions((count) => count + 1);
        }}
      >
        <PageEmptyState
          icon="description"
          message="No evaluations"
          action={{
            label: "Create evaluation",
            onClick: () => setSelected(true),
          }}
        />
      </form>
      <output data-submissions>{submissions}</output>
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
          onRowClick={() => setActivations((count) => count + 1)}
          pageSize={20}
          labels={{
            selectAllOnPage: "Select visible records",
            selectRow: "Select record",
            activateRow: "Open record",
            pagination: labels,
          }}
        />
      </div>
      <output data-activations>{activations}</output>
      <div data-identity-table>
        <DataTable
          data={identityRows}
          pageSize={2}
          columns={[
            {
              label: "Identity",
              sortable: true,
              sortValue: (row) => row.id,
              cellRenderer: (row) => (
                <input
                  aria-label={`Draft ${row.id}`}
                  defaultValue={`Record ${row.id}`}
                />
              ),
            },
          ]}
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
          <button type="button" onClick={() => setOverlay(true)}>
            Open detail above drawer
          </button>
          <button type="button" onClick={() => setNestedDialog(true)}>
            Open nested dialog
          </button>
          <Dialog
            open={nestedDialog}
            title="Nested confirmation"
            confirmLabel="Confirm"
            onConfirm={() => setNestedDialog(false)}
            onCancel={() => setNestedDialog(false)}
          >
            <input aria-label="Nested value" />
          </Dialog>
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
      <button type="button" onClick={() => setWideOverlay(true)}>
        Open wide overlay
      </button>
      <InlineDrawer
        title="Wide overlay"
        open={wideOverlay}
        width="700px"
        onClose={() => setWideOverlay(false)}
      >
        <button
          type="button"
          data-lower-action
          onClick={() => setLowerClicks((value) => value + 1)}
        >
          Lower action {lowerClicks}
        </button>
        <button type="button" onClick={() => setOverlay(true)}>
          Open narrow overlay
        </button>
      </InlineDrawer>
      <InlineDrawer
        width="480px"
        title="Hosted overlay"
        open={overlay}
        onClose={() => setOverlay(false)}
      >
        <span>Overlay content</span>
        {overlay &&
          createPortal(
            <div>
              <button type="button">Portal first</button>
              <button type="button">Portal last</button>
            </div>,
            document.querySelector(".fred-ui")!,
          )}
        <details>
          <summary>Editor details</summary>
          <span>Details</span>
        </details>
        <button type="button" onClick={() => setOverlayDialog(true)}>
          Open overlay dialog
        </button>
        <div
          contentEditable
          suppressContentEditableWarning
          role="textbox"
          aria-label="Overlay editor"
        >
          Editable
        </div>
        <Dialog
          open={overlayDialog}
          title="Overlay confirmation"
          confirmLabel="Confirm"
          onConfirm={() => setOverlayDialog(false)}
          onCancel={() => setOverlayDialog(false)}
        >
          <input aria-label="Overlay dialog field" />
        </Dialog>
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
