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

import { Box, Divider, Paper, Stack, Typography } from "@mui/material";
import { DocumentData } from "../components/documents/data/DocumentData.tsx";
import { useTranslation } from "react-i18next";

export default function DataHub() {
  const { t } = useTranslation();

  return (
    <Box p={2} sx={{ display: "flex", justifyContent: "center" }}>
      <Paper sx={{ p: 2, width: "min(1100px, 100%)" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center">
          <Typography variant="h6">{t("dataHub.title")}</Typography>
        </Stack>
        <Divider sx={{ my: 1.5 }} />
        <DocumentData />
      </Paper>
    </Box>
  );
}
