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

import type { ApplicationSummary } from "../../../slices/controlPlane/controlPlaneOpenApi.ts";
import { FRED_APPLICATION_HOST_API_VERSION, type FredApplicationRegistration } from "./applicationHost.ts";

export type ApplicationResolution =
  | { status: "ready"; registration: FredApplicationRegistration }
  | {
      status:
        | "missing-module"
        | "registration-id-mismatch"
        | "unsupported-host-version"
        | "version-mismatch"
        | "contract-mismatch";
    };

/**
 * Match an authorized control-plane summary to this build's static registry.
 * This function never invokes the loader: catalog authorization and every
 * compatibility check finish before application code can execute.
 */
export function resolveApplicationRegistration(
  application: ApplicationSummary,
  registry: Readonly<Record<string, FredApplicationRegistration>>,
): ApplicationResolution {
  if (!Object.prototype.hasOwnProperty.call(registry, application.id)) {
    return { status: "missing-module" };
  }

  const registration = registry[application.id];
  if (registration.id !== application.id) return { status: "registration-id-mismatch" };
  if (
    application.host_api_version !== FRED_APPLICATION_HOST_API_VERSION ||
    registration.hostApiVersion !== FRED_APPLICATION_HOST_API_VERSION
  ) {
    return { status: "unsupported-host-version" };
  }
  if (registration.version !== application.version) return { status: "version-mismatch" };
  if (registration.contractDigest !== application.contract_digest) return { status: "contract-mismatch" };
  return { status: "ready", registration };
}

export function hasCompatibleApplication(
  applications: readonly ApplicationSummary[] | undefined,
  registry: Readonly<Record<string, FredApplicationRegistration>>,
): boolean {
  return (
    applications?.some((application) => resolveApplicationRegistration(application, registry).status === "ready") ??
    false
  );
}

export class ApplicationModuleLoadError extends Error {
  constructor() {
    super("Application module could not be loaded");
    this.name = "ApplicationModuleLoadError";
  }
}

export async function loadApplicationModule(registration: FredApplicationRegistration) {
  try {
    return await registration.load();
  } catch {
    // Do not preserve an upstream error message: a module error can contain
    // application data, and Fred diagnostics need only the failure class/id.
    throw new ApplicationModuleLoadError();
  }
}
