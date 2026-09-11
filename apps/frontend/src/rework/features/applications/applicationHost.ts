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

export {
  ACCEPTED_APP_PROTOCOL_VERSIONS,
  FRED_APP_PROTOCOL_VERSION,
  parseApplicationFrameMessage,
} from "./applicationProtocol.ts";
export type { ApplicationFrameMessage, ApplicationHostMessage, FredApplicationContext } from "./applicationProtocol.ts";

export interface FredApplicationFrameTarget {
  src: string;
  targetOrigin: string;
}

/**
 * Resolve the catalog's configured UI prefix into an iframe target. The value
 * is deployment configuration rather than Fred source, so it is validated
 * before it can become a src: a `javascript:` or `data:` entry would otherwise
 * run in whatever origin the frame inherits. The target origin is derived from
 * the same value, which is what keeps a later move to a separate origin a
 * configuration change rather than a code change.
 */
export function applicationFrameTarget(
  application: ApplicationSummary,
  baseOrigin: string,
): FredApplicationFrameTarget | null {
  if (!application.ui_prefix) return null;

  let url: URL;
  try {
    url = new URL(application.ui_prefix, baseOrigin);
  } catch {
    return null;
  }
  if (url.protocol !== "http:" && url.protocol !== "https:") return null;
  return { src: url.href, targetOrigin: url.origin };
}

/**
 * The only authenticated transport an application reaches. Fred owns the
 * service root, team scope, bearer lifecycle, and retry/logout behavior; the
 * application owns only its relative resource path and ordinary payload.
 * It stays on the host side of the channel — an application is never handed a
 * token, so moving the frame to another origin changes nothing here.
 */
export type FredApplicationRequest = (
  relativePath: string,
  init?: Pick<RequestInit, "method" | "headers" | "body" | "signal">,
) => Promise<Response>;
