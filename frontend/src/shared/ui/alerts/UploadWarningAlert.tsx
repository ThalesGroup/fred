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

import { Alert } from "@mui/material";
import type { AlertProps } from "@mui/material";
import { useLocalizedUploadWarning } from "../../../hooks/useLocalizedUploadWarning";

export type UploadWarningAlertProps = Omit<AlertProps, "children" | "severity">;

/**
 * Render the platform-configured upload warning banner when one is available.
 *
 * Why: upload-related screens should share one alert component so the banner
 * stays visually consistent while locale resolution remains centralized.
 *
 * How to use: place this component where an upload warning should appear and
 * pass standard MUI alert props like `sx` for local layout adjustments.
 *
 * Example:
 * <UploadWarningAlert sx={{ mt: 1.5 }} />
 */
export const UploadWarningAlert = (props: UploadWarningAlertProps) => {
  const { uploadWarning, uploadWarningMessage } = useLocalizedUploadWarning();

  if (!uploadWarning || !uploadWarningMessage) {
    return null;
  }

  return (
    <Alert severity={uploadWarning.severity ?? "info"} {...props}>
      {uploadWarningMessage}
    </Alert>
  );
};
