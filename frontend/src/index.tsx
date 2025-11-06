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

import { Provider } from "react-redux";
import "./styles.css";
import "./index.scss";
import { createRoot } from "react-dom/client";
import FredUi from "./app/App.tsx";
import { store } from "./common/store.tsx";
import { KeyCloakService } from "./security/KeycloakService.ts";
import { loadConfig } from "./common/config.tsx";
import "./i18n";
import "@fontsource/inter/100.css";
import "@fontsource/inter/200.css";
import "@fontsource/inter/300.css";
import "@fontsource/inter/400.css";
import "@fontsource/inter/500.css";
import "@fontsource/inter/600.css";
import { pdfjs } from "react-pdf";

pdfjs.GlobalWorkerOptions.workerSrc = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url).toString();

const startApp = async () => {
  console.info("Starting Fred UI...");
  try {
    await loadConfig(); // <-- await config loading FIRST
    console.info("Configuration loaded successfully");
    KeyCloakService.CallLogin(() => {
      createRoot(document.getElementById("root") as HTMLElement).render(
        <Provider store={store}>
          <FredUi />
        </Provider>,
      );
    });
  } catch (error) {
    console.error("Failed to load config:", error);
    // Optionally render a fatal error page
  }
};

startApp(); // <-- Start everything
