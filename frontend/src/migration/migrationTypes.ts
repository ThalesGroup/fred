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
// Mirrors control_plane_backend/migration/snapshot.py. Do NOT merge into swift
// as-is; on swift this whole folder is recreated as the official import/export.
// ---------------------------------------------------------------------------

export interface SnapshotManifest {
  format_version: number;
  source_platform: string;
  created_at: string;
  tables: Record<string, number>;
  tuple_count: number;
  realm_exported: boolean;
  content_keys: string[];
}

export interface SnapshotResponse {
  object_key: string;
  download_url: string;
  manifest: SnapshotManifest;
}

export interface SnapshotRequest {
  label?: string;
}

export interface ImportReport {
  source_platform: string;
  tables: Record<string, number>;
  tuples_written: number;
  tuples_skipped: number;
  content_restored: number;
  warnings: string[];
}
