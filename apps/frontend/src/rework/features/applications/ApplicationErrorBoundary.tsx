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

interface ApplicationErrorBoundaryProps {
  applicationId: string;
  children: ReactNode;
  fallback: ReactNode;
}

interface ApplicationErrorBoundaryState {
  failed: boolean;
}

/** Contains a failure in the host surface Fred renders around one application. */
export class ApplicationErrorBoundary extends Component<ApplicationErrorBoundaryProps, ApplicationErrorBoundaryState> {
  state: ApplicationErrorBoundaryState = { failed: false };

  static getDerivedStateFromError(): ApplicationErrorBoundaryState {
    return { failed: true };
  }

  componentDidCatch(_error: unknown, _info: ErrorInfo) {
    // Deliberately omit the original error/message: anything reaching this
    // boundary may carry application data. The id is enough to diagnose which
    // hosted application failed without logging its payload.
    console.error(`[applications] render failure for ${this.props.applicationId}`);
  }

  render() {
    return this.state.failed ? this.props.fallback : this.props.children;
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
