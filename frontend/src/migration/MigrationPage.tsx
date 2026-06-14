// Copyright Thales 2025
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

// ---------------------------------------------------------------------------
// KEA MIGRATION (one-shot, throwaway-on-kea) — isolated feature folder.
// Minimal platform-admin page: export a kea snapshot (download) and import one
// back (upload). Self-guards on the "admin" role; backend enforces require_admin.
// ---------------------------------------------------------------------------

import UploadFileIcon from "@mui/icons-material/UploadFile";
import {
  Alert,
  Box,
  Button,
  Chip,
  CircularProgress,
  Divider,
  Paper,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import { useState } from "react";

import { useAuth } from "../security/AuthContext";
import { KeyCloakService } from "../security/KeycloakService";
import { downloadFile } from "../utils/downloadUtils";
import { useImportMigrationSnapshotMutation } from "./migrationApi";
import type { ImportReport, SnapshotManifest } from "./migrationTypes";

// Direct-stream export: pull the zip through the kea API (same-origin) so the
// browser never needs to reach object storage — required for cross-infra
// migrations. Kept as a plain fetch to avoid putting a Blob in the Redux store.
const SNAPSHOT_DOWNLOAD_URL = "/control-plane/v1/admin/migration/snapshot/download";

// Mirrors control_plane_backend EXPORT_TABLES — shown so the admin knows what
// the bundle contains before exporting.
const EXPORTED_TABLES = ["tag", "metadata", "resource", "mcp-server", "teammetadata", "users", "agent"];

export default function MigrationPage() {
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const [label, setLabel] = useState("");
  const [exportManifest, setExportManifest] = useState<SnapshotManifest | null>(null);
  const [savedFilename, setSavedFilename] = useState("");
  const [isExporting, setIsExporting] = useState(false);
  const [exportError, setExportError] = useState<string | null>(null);

  const [file, setFile] = useState<File | null>(null);
  const [importReport, setImportReport] = useState<ImportReport | null>(null);
  const [importSnapshot, { isLoading: isImporting, error: importError }] = useImportMigrationSnapshotMutation();

  if (!isAdmin) {
    return (
      <Box sx={{ p: 4, maxWidth: 720, mx: "auto" }}>
        <Alert severity="error">This page is restricted to platform administrators.</Alert>
      </Box>
    );
  }

  const handleExport = async () => {
    setExportError(null);
    setExportManifest(null);
    setIsExporting(true);
    try {
      const token = KeyCloakService.GetToken();
      const res = await fetch(SNAPSHOT_DOWNLOAD_URL, {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          ...(token ? { Authorization: `Bearer ${token}` } : {}),
        },
        body: JSON.stringify({ label: label.trim() || undefined }),
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);

      const header = res.headers.get("X-Migration-Manifest");
      const manifest: SnapshotManifest | null = header ? JSON.parse(atob(header)) : null;
      const disposition = res.headers.get("Content-Disposition") ?? "";
      const filename = disposition.match(/filename="?([^"]+)"?/)?.[1] ?? "kea-snapshot.zip";

      downloadFile(await res.blob(), filename);
      setExportManifest(manifest);
      setSavedFilename(filename);
    } catch (e) {
      setExportError(e instanceof Error ? e.message : "export failed");
    } finally {
      setIsExporting(false);
    }
  };

  const handleImport = async () => {
    if (!file) return;
    setImportReport(null);
    const report = await importSnapshot(file).unwrap();
    setImportReport(report);
  };

  return (
    <Box sx={{ p: 4, maxWidth: 720, mx: "auto" }}>
      <Typography variant="h5" gutterBottom>
        Platform Migration · Export
      </Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 3 }}>
        Source: <strong>kea</strong> · Bundles durable platform state into one timestamped <code>.zip</code> streamed
        directly through the API to your machine.
      </Typography>

      <Paper variant="outlined" sx={{ p: 3, mb: 3 }}>
        <Typography variant="subtitle2" gutterBottom>
          What gets exported
        </Typography>
        <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
          {EXPORTED_TABLES.map((t) => (
            <Chip key={t} label={t} size="small" />
          ))}
        </Stack>
        <Typography variant="body2" color="text.secondary">
          Plus OpenFGA tuples (store <code>kea</code>), the Keycloak realm export (users + groups), and team banner
          content.
        </Typography>

        <Divider sx={{ my: 2 }} />

        <TextField
          label="Label (optional)"
          placeholder="e.g. pre-swift-test"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          size="small"
          fullWidth
          helperText="Embedded in the filename: kea-snapshot-<label>-<timestamp>.zip"
          sx={{ mb: 2 }}
        />

        <Button
          variant="contained"
          onClick={handleExport}
          disabled={isExporting}
          startIcon={isExporting ? <CircularProgress size={18} color="inherit" /> : undefined}
        >
          {isExporting ? "Creating snapshot…" : "Create & download snapshot"}
        </Button>
      </Paper>

      {exportError ? (
        <Alert severity="error" sx={{ mb: 2 }}>
          Export failed ({exportError}). Check that you have the admin role and that the control-plane backend is
          reachable.
        </Alert>
      ) : null}

      {exportManifest ? (
        <Paper variant="outlined" sx={{ p: 3 }}>
          <Alert severity="success" sx={{ mb: 2 }}>
            Downloaded <code>{savedFilename}</code>
          </Alert>

          <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap">
            {Object.entries(exportManifest.tables).map(([table, count]) => (
              <Chip key={table} label={`${table}: ${count}`} size="small" variant="outlined" />
            ))}
            <Chip label={`tuples: ${exportManifest.tuple_count}`} size="small" variant="outlined" />
            <Chip label={`realm: ${exportManifest.realm_exported ? "yes" : "no"}`} size="small" variant="outlined" />
            <Chip label={`banners: ${exportManifest.content_keys.length}`} size="small" variant="outlined" />
          </Stack>
        </Paper>
      ) : null}

      <Divider sx={{ my: 4 }} />

      <Typography variant="h6" gutterBottom>
        Import (restore into this kea)
      </Typography>
      <Alert severity="warning" sx={{ mb: 2 }}>
        Writes to this instance's database and OpenFGA store (upsert). Intended for a fresh/empty kea — not a populated
        instance you care about.
      </Alert>

      <Paper variant="outlined" sx={{ p: 3 }}>
        <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 2 }}>
          <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
            Choose .zip
            <input
              type="file"
              accept=".zip,application/zip"
              hidden
              onChange={(e) => {
                setFile(e.target.files?.[0] ?? null);
                setImportReport(null);
              }}
            />
          </Button>
          <Typography variant="body2" color="text.secondary">
            {file ? file.name : "No file selected"}
          </Typography>
        </Stack>

        <Button
          variant="contained"
          color="warning"
          onClick={handleImport}
          disabled={!file || isImporting}
          startIcon={isImporting ? <CircularProgress size={18} color="inherit" /> : undefined}
        >
          {isImporting ? "Importing…" : "Import snapshot"}
        </Button>

        {importError ? (
          <Alert severity="error" sx={{ mt: 2 }}>
            Import failed. Check the file is a kea snapshot zip and you have the admin role.
          </Alert>
        ) : null}

        {importReport ? (
          <Box sx={{ mt: 2 }}>
            <Alert severity="success" sx={{ mb: 2 }}>
              Imported from <code>{importReport.source_platform}</code>
            </Alert>
            <Stack direction="row" spacing={1} useFlexGap flexWrap="wrap" sx={{ mb: 1 }}>
              {Object.entries(importReport.tables).map(([table, count]) => (
                <Chip key={table} label={`${table}: ${count}`} size="small" variant="outlined" />
              ))}
              <Chip label={`tuples written: ${importReport.tuples_written}`} size="small" variant="outlined" />
              <Chip label={`tuples skipped: ${importReport.tuples_skipped}`} size="small" variant="outlined" />
              <Chip label={`content: ${importReport.content_restored}`} size="small" variant="outlined" />
            </Stack>
            {importReport.warnings.length > 0 ? (
              <Alert severity="warning">
                {importReport.warnings.map((w, idx) => (
                  <div key={idx}>{w}</div>
                ))}
              </Alert>
            ) : null}
          </Box>
        ) : null}
      </Paper>
    </Box>
  );
}
