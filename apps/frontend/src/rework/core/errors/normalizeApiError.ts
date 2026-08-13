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

type ApiErrorKind = "network" | "forbidden" | "conflict" | "validation" | "unknown";

export interface NormalizedApiError {
  kind: ApiErrorKind;
  status?: number;
  detail?: string;
}

type RecordLike = Record<string, unknown>;

const isRecord = (value: unknown): value is RecordLike => {
  return typeof value === "object" && value !== null;
};

const asString = (value: unknown): string | undefined => {
  return typeof value === "string" && value.trim().length > 0 ? value : undefined;
};

const getDetailFromData = (data: unknown): string | undefined => {
  if (!isRecord(data)) return undefined;

  const directDetail = asString(data.detail);
  if (directDetail) return directDetail;

  // FastAPI's own default validation-error body (any route whose request model
  // is validated by FastAPI itself, not re-raised by app code as a plain-string
  // HTTPException) puts a list of pydantic error objects under `detail` --
  // distinct from the app-level `errors` shape below. Report the first one
  // rather than falling back to a generic message.
  if (Array.isArray(data.detail)) {
    for (const entry of data.detail) {
      if (!isRecord(entry)) continue;
      const message = asString(entry.msg) || asString(entry.message);
      if (message) return message;
    }
  }

  const errors = data.errors;
  if (!Array.isArray(errors)) return undefined;

  for (const entry of errors) {
    if (!isRecord(entry)) continue;
    const message = asString(entry.detail) || asString(entry.message);
    if (message) return message;
  }

  return undefined;
};

const kindFromStatus = (status: number): ApiErrorKind => {
  if (status === 403) return "forbidden";
  if (status === 409) return "conflict";
  if (status === 400 || status === 422) return "validation";
  return "unknown";
};

export function normalizeApiError(error: unknown): NormalizedApiError {
  if (!isRecord(error)) {
    return { kind: "unknown" };
  }

  if (!("status" in error)) {
    // RTK Query's `.unwrap()` rejects with a plain SerializedError
    // ({name, message, stack}) -- not a real Error instance -- whenever the
    // query/mutation throws before producing a FetchBaseQueryError. Surface
    // its message instead of silently dropping it. A real Error is left
    // alone: callers that reach here with one are treating it as an
    // unexpected failure and often prefer their own contextual fallback
    // over leaking a raw exception message.
    if (error instanceof Error) {
      return { kind: "unknown" };
    }
    return { kind: "unknown", detail: asString(error.message) };
  }

  const statusValue = error.status;

  if (typeof statusValue === "string") {
    if (statusValue === "FETCH_ERROR" || statusValue === "TIMEOUT_ERROR") {
      return {
        kind: "network",
        detail: asString((error as RecordLike).error),
      };
    }
    return { kind: "unknown", detail: asString((error as RecordLike).error) };
  }

  if (typeof statusValue !== "number") {
    return { kind: "unknown" };
  }

  return {
    kind: kindFromStatus(statusValue),
    status: statusValue,
    detail: getDetailFromData((error as RecordLike).data),
  };
}
