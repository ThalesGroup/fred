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

// The spreadsheet capability's UI plugin: the `spreadsheet_preview` chat card and
// the read-only preview pane (lazy, so its chunk loads on first open).

import { lazy } from "react";
import type { CapabilityUiPlugin } from "../types";
import { CAPABILITY_ID, PANE_WIDGET } from "./types";
import { SpreadsheetCardRenderer } from "./SpreadsheetCardRenderer";
import { useHasSpreadsheet } from "./useSpreadsheetPreview";

const SpreadsheetPane = lazy(async () => ({ default: (await import("./SpreadsheetPane")).SpreadsheetPane }));

export const spreadsheetCapability: CapabilityUiPlugin = {
  id: CAPABILITY_ID,
  partRenderers: { spreadsheet_preview: SpreadsheetCardRenderer },
  sidePanels: {
    [PANE_WIDGET]: {
      Component: SpreadsheetPane,
      icon: "table_chart",
      useHasContent: useHasSpreadsheet,
      ownsHeader: true,
    },
  },
};
