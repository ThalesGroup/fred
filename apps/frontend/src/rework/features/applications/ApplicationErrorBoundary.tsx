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

import { Component, type ErrorInfo, type ReactNode } from "react";
import type { RootOptions } from "react-dom/client";
import { ApplicationModuleLoadError } from "./applicationResolution.ts";

export type ApplicationBoundaryFailure = "module-load" | "render";

interface ApplicationErrorBoundaryProps {
  applicationId: string;
  children: ReactNode;
  fallback: (failure: ApplicationBoundaryFailure) => ReactNode;
}

interface ApplicationErrorBoundaryState {
  failure: ApplicationBoundaryFailure | null;
}

/** Contains both a rejected lazy import and an application's render failure. */
export class ApplicationErrorBoundary extends Component<ApplicationErrorBoundaryProps, ApplicationErrorBoundaryState> {
  state: ApplicationErrorBoundaryState = { failure: null };

  static getDerivedStateFromError(error: unknown): ApplicationErrorBoundaryState {
    return { failure: error instanceof ApplicationModuleLoadError ? "module-load" : "render" };
  }

  componentDidCatch(error: unknown, _info: ErrorInfo) {
    const failure = error instanceof ApplicationModuleLoadError ? "module-load" : "render";
    // Deliberately omit the original error/message: application errors can
    // include domain payloads. The id and failure class are enough to diagnose
    // which isolated module failed without leaking its data.
    console.error(`[applications] ${failure} failure for ${this.props.applicationId}`);
  }

  render() {
    return this.state.failure ? this.props.fallback(this.state.failure) : this.props.children;
  }
}

/**
 * Keep application failures on the boundary's sanitized diagnostic path while
 * preserving React's raw caught-error reporting for every other boundary.
 */
export const reportCaughtReactError: NonNullable<RootOptions["onCaughtError"]> = (error, errorInfo) => {
  if (errorInfo.errorBoundary instanceof ApplicationErrorBoundary) return;
  console.error(error);
};
