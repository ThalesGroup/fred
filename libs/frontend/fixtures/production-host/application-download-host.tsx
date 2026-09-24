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

import { createRoot } from "react-dom/client";
import { ApplicationContext } from "./application-download-mocks.tsx";
import TeamApplicationHostPage from "../../../../apps/frontend/src/rework/components/pages/TeamApplicationHostPage/TeamApplicationHostPage.tsx";

const root = document.getElementById("root");
if (!root) throw new Error("production-host fixture root is missing");

createRoot(root).render(
  <ApplicationContext.Provider value={{ darkMode: false }}>
    <TeamApplicationHostPage />
  </ApplicationContext.Provider>,
);
