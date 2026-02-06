import PlayCircleOutlineIcon from "@mui/icons-material/PlayCircleOutline";
import { Box, Button, Paper, Typography } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { App } from "./TeamAppsPage";
export interface AppCardProps {
  app: App;
}
export function AppCard({ app }: AppCardProps) {
  const { t } = useTranslation();
  return (
    <Paper elevation={2} sx={{ borderRadius: 2 }}>
      <Box
        sx={{
          px: 2,
          pt: 1.5,
          pb: 2,
          display: "flex",
          flexDirection: "column",
          alignItems: "stretch",
          gap: 2,
          borderRadius: 2,
          userSelect: "none",
          height: "100%",
        }}
      >
        <Box sx={{ display: "flex", flexDirection: "column", alignItems: "stretch", gap: 1, flexGrow: 1 }}>
          {/* Name */}
          <Typography variant="h6">{app.name}</Typography>

          {/* Description */}
          <Typography
            variant="body2"
            color="textSecondary"
            sx={{
              flexGrow: 1,
              lineClamp: 3,
              overflow: "hidden",
              textOverflow: "ellipsis",
              display: "-webkit-box",
              WebkitBoxOrient: "vertical",
              WebkitLineClamp: 3,
              height: "3.7rem",
            }}
          >
            {app.description}
          </Typography>
        </Box>

        {/* Start button */}
        <Button variant="outlined" startIcon={<PlayCircleOutlineIcon />} component={Link} to={app.url} target="_blank">
          {t("appCard.launch")}
        </Button>
      </Box>
    </Paper>
  );
}
