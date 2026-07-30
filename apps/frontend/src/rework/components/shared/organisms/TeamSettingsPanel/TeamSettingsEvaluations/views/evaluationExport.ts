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

import { downloadFile } from "../../../../../../../utils/downloadUtils";
import type {
  EvaluationCaseResponse,
  RunReportResponse,
} from "../../../../../../../slices/evaluation/evaluationOpenApi";

// Bumped only when the exported envelope shape changes, so a consumer (a human or
// an AI agent reading the dump) can tell which layout to expect. Independent of the
// backend's own RunReportResponse.schema_version, which travels inside the payload.
const CASE_EXPORT_SCHEMA_VERSION = "1";

/** A single case exported as a self-describing, versioned envelope. */
export interface EvaluationCaseExport {
  schema_version: string;
  kind: "evaluation_case";
  exported_at: string;
  case: EvaluationCaseResponse;
}

function saveJson(payload: unknown, filename: string): void {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  downloadFile(blob, filename);
}

/**
 * Download one case as a typed, versioned JSON file — the shareable equivalent of
 * the existing clipboard copy, but wrapped so the raw EvaluationCaseResponse isn't
 * mistaken for a bare, unversioned blob.
 */
export function downloadCaseJson(caseData: EvaluationCaseResponse): void {
  const envelope: EvaluationCaseExport = {
    schema_version: CASE_EXPORT_SCHEMA_VERSION,
    kind: "evaluation_case",
    exported_at: new Date().toISOString(),
    case: caseData,
  };
  saveJson(envelope, `evaluation-case-${caseData.case_id}.json`);
}

/**
 * Download the whole run as a JSON file. The backend's run report is already a
 * self-contained, versioned record (schema_version, evaluation, all cases,
 * metric_averages, and the analysis when available), so it is exported as-is —
 * no re-wrapping needed.
 */
export function downloadRunReportJson(report: RunReportResponse): void {
  saveJson(report, `evaluation-run-${report.run.run_id}.json`);
}
