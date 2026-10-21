// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { expect, it } from "vitest";
import type { FailureCode, Summary } from "../../../slices/controlPlane/controlPlaneOpenApi";
import { managerProcessingErrors, managerProcessingFailure } from "./managerDocuments";
it("reports persisted manager failure stages without depending on the uploader task feed", () => {
  const processing: Summary = {
    id: "attempt",
    document_id: "doc",
    profile: "fast",
    stage: "extraction",
    status: "failed",
    error_code: "deadline_exceeded",
    created_at: "2026-10-19",
    completed_at: "2026-10-19",
    retry_of: null,
    revision: 3,
    chunks: 0,
    vectors: 0,
    rows: null,
  };
  expect(managerProcessingErrors(processing, (key) => key)).toEqual({
    extraction: "rework.documentStorage.processingErrors.deadline_exceeded",
  });
  expect(managerProcessingErrors({ ...processing, error_code: "private upstream diagnostic" }, (key) => key)).toEqual({
    extraction: "rework.documentStorage.processingErrors.worker_failed",
  });
  expect(managerProcessingErrors({ ...processing, status: "running" }, (key) => key)).toBeUndefined();
});

const failures: Record<FailureCode, true> = {
  unsupported_input: true,
  access_changed: true,
  integrity_failure: true,
  extraction_failed: true,
  preview_failed: true,
  indexing_failed: true,
  capacity_exceeded: true,
  worker_failed: true,
  deadline_exceeded: true,
  delivery_unknown: true,
};
it.each(Object.keys(failures))("preserves the stable failure %s for directory and import cards", (code) => {
  expect(managerProcessingFailure(code, (key) => key)).toBe(`rework.documentStorage.processingErrors.${code}`);
});
