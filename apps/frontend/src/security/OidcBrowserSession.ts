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

import { ErrorResponse, UserManager, type User } from "oidc-client-ts";

const REFRESH_TIMEOUT_MS = 8_000;
const TERMINAL_RENEWAL_ERRORS = new Set([
  "invalid_grant",
  "login_required",
  "interaction_required",
  "consent_required",
  "account_selection_required",
]);

/** Browser OIDC lifecycle kept behind the existing KeyCloakService facade. */
export class OidcBrowserSession {
  readonly manager: UserManager;
  private user: User | null = null;
  private generation = 0;
  private refreshInFlight: Promise<boolean> | null = null;
  private renewalReconciliation: Promise<void> = Promise.resolve();
  private invalidated = false;
  private readonly redirectUri: string;

  constructor(issuer: string, clientId: string, apiScope: string | undefined, redirectUri: string) {
    this.redirectUri = redirectUri;
    const scope = ["openid", "profile", "offline_access", apiScope].filter(Boolean).join(" ");
    this.manager = new UserManager({
      authority: issuer.replace(/\/+$/, ""),
      client_id: clientId,
      redirect_uri: redirectUri,
      silent_redirect_uri: redirectUri,
      post_logout_redirect_uri: redirectUri,
      response_type: "code",
      scope,
      disablePKCE: false,
      automaticSilentRenew: false,
      loadUserInfo: false,
      silentRequestTimeoutInSeconds: REFRESH_TIMEOUT_MS / 1000,
    });
    this.manager.events.addAccessTokenExpiring(() => {
      void this.ensureFreshToken(60);
    });
    this.manager.events.addUserUnloaded(() => {
      this.user = null;
    });
  }

  get token(): string | null {
    return this.invalidated || this.user?.expired ? null : (this.user?.access_token ?? null);
  }

  get refreshToken(): string | null {
    return this.invalidated ? null : (this.user?.refresh_token ?? null);
  }

  // Access tokens stay in oidc-client-ts's session store; Fred does not copy
  // them to its legacy localStorage key.
  get tokenParsed(): Record<string, unknown> | null {
    const token = this.token;
    if (!token) return null;
    try {
      const payload = token.split(".")[1];
      const bytes = Uint8Array.from(atob(payload.replace(/-/g, "+").replace(/_/g, "/")), (char) => char.charCodeAt(0));
      return JSON.parse(new TextDecoder().decode(bytes)) as Record<string, unknown>;
    } catch {
      return null;
    }
  }

  get tokenSecondsLeft(): number | null {
    if (this.invalidated) return 0;
    if (!this.user) return null;
    return this.user.expires_in ?? null;
  }

  async login(onAuthenticated: () => void): Promise<void> {
    const generation = this.generation;
    const query = new URLSearchParams(window.location.search);
    if (query.has("state") && (query.has("code") || query.has("error"))) {
      if (window.self !== window.top) {
        await this.manager.signinSilentCallback();
        return;
      }
      const user = await this.manager.signinRedirectCallback();
      if (generation !== this.generation || this.invalidated) {
        await this.manager.removeUser();
        return;
      }
      this.user = user;
      window.history.replaceState({}, "", this.redirectUri);
    } else if (query.has("state")) {
      await this.manager.signoutRedirectCallback();
      window.history.replaceState({}, "", this.redirectUri);
    }
    const restored = this.user ?? (await this.manager.getUser());
    if (generation !== this.generation || this.invalidated) return;
    this.user = restored;
    if (this.user?.expired && this.user.refresh_token) {
      await this.ensureFreshToken(0);
    }
    if (this.user?.access_token && !this.user.expired) {
      this.invalidated = false;
      onAuthenticated();
      return;
    }
    await this.manager.signinRedirect();
  }

  async logout(): Promise<void> {
    this.generation += 1;
    this.invalidated = true;
    this.user = null;
    try {
      await this.manager.signoutRedirect({ post_logout_redirect_uri: this.redirectUri });
    } catch (error) {
      await this.manager.removeUser();
      throw error;
    }
  }

  private reconcileRenewalState(): Promise<void> {
    // SDK responses write before our checks; serialize storage and timer repair.
    const reconcile = this.renewalReconciliation.then(async () => {
      if (this.invalidated || !this.user) {
        await this.manager.removeUser();
      } else {
        await this.manager.storeUser(this.user);
        await this.manager.getUser();
      }
    });
    this.renewalReconciliation = reconcile.catch(() => undefined);
    return reconcile;
  }

  async ensureFreshToken(minValidity = 30): Promise<boolean> {
    if (this.invalidated || !this.user) return false;
    if (minValidity > 0 && (this.user.expires_in ?? 0) > minValidity) return true;
    if (this.refreshInFlight) {
      const refreshed = await this.refreshInFlight;
      return refreshed && (minValidity <= 0 || (this.user?.expires_in ?? 0) > minValidity);
    }
    const generation = this.generation;
    let timeout: ReturnType<typeof setTimeout> | undefined;
    const refresh = Promise.race([
      this.manager.signinSilent().then(async (user) => {
        if (this.invalidated || generation !== this.generation) {
          await this.reconcileRenewalState();
          return null;
        }
        return user;
      }),
      new Promise<null>((resolve) => {
        timeout = setTimeout(() => {
          this.generation += 1;
          resolve(null);
        }, REFRESH_TIMEOUT_MS);
      }),
    ])
      .then(async (user) => {
        if (!user) return false;
        if (this.invalidated || generation !== this.generation) {
          await this.reconcileRenewalState();
          return false;
        }
        this.user = user;
        await this.reconcileRenewalState();
        if (this.invalidated || generation !== this.generation) {
          await this.reconcileRenewalState();
          return false;
        }
        return true;
      })
      .catch(async (error: unknown) => {
        if (
          generation === this.generation &&
          !this.invalidated &&
          error instanceof ErrorResponse &&
          TERMINAL_RENEWAL_ERRORS.has(error.error ?? "")
        ) {
          // Revoke immediately, even if removing the stored user fails.
          this.generation += 1;
          this.invalidated = true;
          this.user = null;
          await this.reconcileRenewalState().catch(() => undefined);
        }
        return false;
      })
      .finally(() => {
        if (timeout) clearTimeout(timeout);
        if (this.refreshInFlight === refresh) this.refreshInFlight = null;
      });
    this.refreshInFlight = refresh;
    const refreshed = await refresh;
    return refreshed && (minValidity <= 0 || (this.user?.expires_in ?? 0) > minValidity);
  }
}
