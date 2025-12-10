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

import { Box, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { useTheme } from "@mui/material/styles";

interface DocumentDataSearchProps {
  search: string;
  setSearch: (value: string) => void;
}

export const DocumentDataSearch = (
  { search, setSearch } : DocumentDataSearchProps
) => {
  const { t } = useTranslation();
  const theme = useTheme();

  return (
    <Box
      sx={{
        mb: 1,
        display: "flex",
        flexDirection: { xs: "column", md: "row" },
        gap: 1.5,
      }}
    >
      <Box sx={{ flex: 1 }}>
        <Typography variant="caption" color="text.secondary">
          {t("dataHub.searchHelp", "Filter documents by name or source")}
        </Typography>
        <Box
          component="input"
          type="text"
          value={search}
          onChange={(e: React.ChangeEvent<HTMLInputElement>) => setSearch(e.target.value)}
          placeholder={t("dataHub.searchPlaceholder", "Search documents...")}
          style={{
            marginTop: 4,
            width: "100%",
            padding: "6px 8px",
            borderRadius: 4,
            border: `1px solid ${theme.palette.divider}`,
            fontSize: "0.8rem",
            fontFamily: "inherit",
          }}
        />
      </Box>
    </Box>
  );
}