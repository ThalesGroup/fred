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
// Endpoints are injected onto the existing controlPlaneApi (reusing its auth
// baseQuery) so nothing in the generated OpenAPI slices is touched.
// ---------------------------------------------------------------------------

import { controlPlaneApi } from "../slices/controlPlane/controlPlaneApi";
import type { ImportReport, SnapshotRequest, SnapshotResponse } from "./migrationTypes";

export const migrationApi = controlPlaneApi.injectEndpoints({
  endpoints: (build) => ({
    createMigrationSnapshot: build.mutation<SnapshotResponse, SnapshotRequest>({
      query: (body) => ({
        url: "/control-plane/v1/admin/migration/snapshot",
        method: "POST",
        body,
      }),
    }),
    importMigrationSnapshot: build.mutation<ImportReport, File>({
      query: (file) => {
        const formData = new FormData();
        formData.append("file", file);
        return {
          url: "/control-plane/v1/admin/migration/import",
          method: "POST",
          body: formData,
        };
      },
    }),
  }),
  overrideExisting: false,
});

export const { useCreateMigrationSnapshotMutation, useImportMigrationSnapshotMutation } = migrationApi;
