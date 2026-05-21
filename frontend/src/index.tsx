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

import { StrictMode } from "react";
import { Provider } from "react-redux";
import "./styles.css";
import "./styles/utils.css";
import "./styles/index.css";
import "./index.scss";
import { createRoot } from "react-dom/client";
import FredUi from "./app/App.tsx";
import { BootstrapFailureScreen } from "./app/BootstrapFailureScreen.tsx";
import { store } from "./common/store.tsx";
import { KeyCloakService } from "./security/KeycloakService.ts";
import { getConfigLoadFailureDetails, loadConfig } from "./common/config.tsx";
import "./i18n";
import "@fontsource/inter/100.css";
import "@fontsource/inter/200.css";
import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";

/**
 * Renders one fatal startup screen when the application cannot bootstrap normally.
 *
 * Why: config bootstrap happens before the router and providers exist, so startup failures
 * must be surfaced directly from the entrypoint instead of relying on in-app error handling.
 *
 * How: call this only from the top-level `startApp()` catch block.
 */
const renderBootstrapFailure = (error: unknown) => {
  const container = document.getElementById("root");
  if (!container) {
    console.error("Unable to render bootstrap failure screen: missing #root container", error);
    return;
  }

  const root = createRoot(container);
  const failure = getConfigLoadFailureDetails(error);
  root.render(<BootstrapFailureScreen failure={failure} onRetry={() => window.location.reload()} />);
};

/**
 * Starts the frontend after config bootstrap succeeds.
 *
 * Why: the router basename, backend-driven UI properties, and auth bootstrap all depend on
 * `loadConfig()`, so rendering before that step would leave the app in an inconsistent state.
 *
 * How: await config first, then mount the normal React tree, or show a dedicated fallback page.
 *
 * Example:
 * `void startApp();`
 */
const startApp = async () => {
  console.info("Starting Fred UI...");
  try {
    await loadConfig(); // <-- await config loading FIRST
    console.info("Configuration loaded successfully");
    KeyCloakService.CallLogin(() => {
      const root = createRoot(document.getElementById("root"));
      root.render(
        <StrictMode>
          <Provider store={store}>
            <FredUi />
          </Provider>
        </StrictMode>,
      );
    });
  } catch (error) {
    console.error("Failed to load config:", error);
    renderBootstrapFailure(error);
  }
};

startApp(); // <-- Start everything
