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
import { useCreateMigrationSnapshotMutation, useImportMigrationSnapshotMutation } from "./migrationApi";
import type { ImportReport, SnapshotManifest } from "./migrationTypes";

// Mirrors control_plane_backend EXPORT_TABLES — shown so the admin knows what
// the bundle contains before exporting.
const EXPORTED_TABLES = ["tag", "metadata", "resource", "mcp-server", "teammetadata", "users", "agent"];

export default function MigrationPage() {
  const { roles } = useAuth();
  const isAdmin = roles.includes("admin");

  const [label, setLabel] = useState("");
  const [exportManifest, setExportManifest] = useState<SnapshotManifest | null>(null);
  const [savedFilename, setSavedFilename] = useState("");
  const [createSnapshot, { isLoading: isExporting, error: exportError }] = useCreateMigrationSnapshotMutation();

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
    setExportManifest(null);
    // Fetch a presigned object-storage URL and hand off the download to the
    // browser, instead of streaming the zip through control-plane-backend:
    // a streamed response (chunked, no Content-Length) was getting killed by
    // an intermediary in front of the ingress well before any timeout kicked in.
    const response = await createSnapshot({ label: label.trim() || undefined }).unwrap();
    const link = document.createElement("a");
    link.href = response.download_url;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setExportManifest(response.manifest);
    setSavedFilename(response.object_key.split("/").pop() ?? "kea-snapshot.zip");
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
        Source: <strong>kea</strong> · Bundles durable platform state into one timestamped <code>.zip</code>, uploaded
        to object storage and downloaded via a presigned link.
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
          Export failed. Check that you have the admin role and that the control-plane backend is reachable.
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
