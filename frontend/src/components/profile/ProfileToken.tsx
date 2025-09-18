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

import { Box, Card, CardContent, Grid2, Stack, Typography, useTheme } from "@mui/material";
import CodeIcon from "@mui/icons-material/Code";
import { useTranslation } from "react-i18next";

interface ProfileTokenProps {
  tokenParsed: any;
}

export function ProfileToken({ tokenParsed }: ProfileTokenProps) {
  const theme = useTheme();
  const { t } = useTranslation();

  return (
    // Right-anchored container to match ProfileCard
    <Grid2 size={{ xs: 12 }} display="flex" justifyContent={{ xs: "stretch", md: "flex-end" }} px={{ xs: 1.5, md: 3 }}>
      <Card
        variant="outlined"
        sx={{
          ml: { md: "auto" }, // stick to the right on md+
          width: "100%",
          maxWidth: 980, // align width with ProfileCard
          borderRadius: 3,
          bgcolor: "transparent", // no paper fill
          boxShadow: "none",
          borderColor: "divider",
        }}
      >
        <CardContent sx={{ py: { xs: 2, md: 3 }, px: { xs: 2, md: 3 } }}>
          {/* Compact section header */}
          <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 1.5 }}>
            <CodeIcon fontSize="small" />
            <Typography variant="overline" color="text.secondary" sx={{ letterSpacing: 0.6, fontWeight: 600 }}>
              {t("profile.token.title")}
            </Typography>
          </Stack>

          {/* Monospace token box */}
          <Box
            sx={{
              border: `1px solid ${theme.palette.divider}`,
              borderRadius: 1.5,
              p: 1.5,
              maxHeight: 380,
              overflowY: "auto",
              overflowX: "auto",
              bgcolor: theme.palette.mode === "dark" ? "rgba(255,255,255,0.03)" : "rgba(0,0,0,0.03)", // very subtle surface
              "&::-webkit-scrollbar": { width: 8, height: 8 },
              "&::-webkit-scrollbar-thumb": { borderRadius: 4 },
            }}
          >
            <pre
              style={{
                margin: 0,
                whiteSpace: "pre",
                fontFamily:
                  'ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, "Liberation Mono", "Courier New", monospace',
                fontSize: "0.78rem",
                lineHeight: 1.5,
              }}
            >
              {tokenParsed ? JSON.stringify(tokenParsed, null, 2) : t("profile.token.none")}
            </pre>
          </Box>
        </CardContent>
      </Card>
    </Grid2>
  );
}
