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

import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import { useToast } from "../../../components/ToastProvider.tsx";

interface NotifyApiErrorOptions {
  summary: string;
  fallbackDetail: string;
  forbiddenDetail?: string;
  conflictDetail?: string;
  validationDetail?: string;
  networkDetail?: string;
}

export function useApiErrorToast() {
  const { showError } = useToast();

  const notifyApiError = (error: unknown, options: NotifyApiErrorOptions) => {
    const normalized = normalizeApiError(error);

    const defaultByKind = {
      forbidden: options.forbiddenDetail || options.fallbackDetail,
      conflict: options.conflictDetail || options.fallbackDetail,
      validation: options.validationDetail || options.fallbackDetail,
      network: options.networkDetail || options.fallbackDetail,
      unknown: options.fallbackDetail,
    };

    showError({
      summary: options.summary,
      detail: normalized.detail || defaultByKind[normalized.kind],
    });
  };

  return { notifyApiError };
}
