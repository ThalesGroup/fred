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

import type { ComponentType } from "react";
import type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";

/** Host API version understood by this Fred frontend build. */
export const FRED_APPLICATION_HOST_API_VERSION = "1" as const;

/**
 * The only authenticated transport an application module receives. Fred owns
 * the service root, team scope, bearer lifecycle, and retry/logout behavior;
 * modules own only their relative resource path and ordinary request payload.
 */
export type FredApplicationRequest = (
  relativePath: string,
  init?: Pick<RequestInit, "method" | "headers" | "body" | "signal">,
) => Promise<Response>;

export interface FredApplicationPageProps {
  application: ApplicationSummary;
  context: {
    team: {
      id: string;
      name: string;
      isPersonal: boolean;
    };
    route: {
      basePath: string;
      subPath: string;
      navigate: (relativePath: string, options?: { replace?: boolean }) => void;
    };
    locale: string;
    request: FredApplicationRequest;
  };
}

/** One build-time, statically allowlisted application module. */
export interface FredApplicationRegistration {
  id: string;
  version: string;
  hostApiVersion: typeof FRED_APPLICATION_HOST_API_VERSION;
  contractDigest: string;
  load: () => Promise<{ default: ComponentType<FredApplicationPageProps> }>;
}

// Re-export the generated wire type through the public facade. Application
// modules never import Fred's generated API client or any other private source.
export type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
