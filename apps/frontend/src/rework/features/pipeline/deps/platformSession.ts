// Copyright Thales 2026
// SPDX-License-Identifier: Apache-2.0
import { enhancedControlPlaneApi } from "../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../security/KeycloakService";
import type { PlatformSessionDeps } from "../scenarios/platformScenario";
import { FRESH, type ApiDispatch } from "./api";

export function platformSessionDeps(dispatch: ApiDispatch): PlatformSessionDeps {
  return {
    frontendConfig: () =>
      dispatch(enhancedControlPlaneApi.endpoints.frontendConfig.initiate(undefined, FRESH)).unwrap(),
    tokenClaims: () => KeyCloakService.GetTokenParsed() ?? null,
    serverDate: async () => {
      const response = await fetch("/control-plane/v1/healthz", {
        credentials: "omit",
        cache: "no-store",
        redirect: "error",
        signal: AbortSignal.timeout(15000),
      });
      if (!response.ok) throw new Error("The server clock response is unavailable.");
      const header = response.headers.get("Date");
      return header ? new Date(header) : null;
    },
    now: () => Date.now(),
  };
}
