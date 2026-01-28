import InfoOutlinedIcon from "@mui/icons-material/InfoOutlined";
import WebAssetOffIcon from "@mui/icons-material/WebAssetOff";
import { Box, Tooltip, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { EmptyState } from "../EmptyState";
import { AppCard } from "./AppCard";

// todo: get App type genrated slice
export interface App {
  name: string;
  description: string;
  url: string;
}
// todo: get from backed
const apps: App[] = [];

export function TeamAppsPage() {
  const { t } = useTranslation();
  return (
    <Box sx={{ px: 2, pb: 2 }}>
      {/* Header */}
      <Box sx={{ display: "flex", alignItems: "center", height: "3rem", gap: 0.75, px: 1 }}>
        <Typography variant="body2" color="textSecondary">
          {t("teamAppsPage.headerSubtitle")}
        </Typography>
        <Tooltip
          title={t("teamAppsPage.headerInfoTooltip")}
          placement="top"
          slotProps={{
            popper: {
              modifiers: [
                {
                  name: "offset",
                  options: {
                    offset: [0, -12],
                  },
                },
              ],
            },
          }}
        >
          <InfoOutlinedIcon fontSize="small" color="disabled" />
        </Tooltip>
      </Box>

      {/* Empty state */}
      {apps.length === 0 && (
        <EmptyState
          title={t("teamAppsPage.noAppTitle")}
          description={t("teamAppsPage.noAppDescription")}
          icon={<WebAssetOffIcon />}
        />
      )}

      {/* Cards */}
      {apps.length > 0 && (
        <Box sx={{ display: "grid", gap: 2, gridTemplateColumns: "repeat(auto-fill, minmax(280px, 1fr))" }}>
          {[...apps].map((app) => (
            <AppCard app={app} />
          ))}
        </Box>
      )}
    </Box>
  );
}
