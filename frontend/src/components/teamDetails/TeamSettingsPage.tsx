import { alpha, Box, FormControlLabel, Paper, Switch, TextField, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { Team } from "../../slices/controlPlane/controlPlaneApi";
import { TeamBanner } from "../teams/TeamVisuals";

export interface TeamSettingsPageProps {
  team?: Team;
}

export function TeamSettingsPage({ team }: TeamSettingsPageProps) {
  const { t } = useTranslation();
  const theme = useTheme();

  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <Paper sx={{ borderRadius: 2, flex: 1, display: "flex", justifyContent: "center" }}>
        <Box sx={{ maxWidth: "600px", display: "flex", flexDirection: "column", gap: 2, py: 2 }}>
          <Typography variant="body2" color="warning.main">
            {t(
              "teamSettingsPage.readOnlyNotice",
              "Team settings update is temporarily disabled while migration to control-plane is completed.",
            )}
          </Typography>

          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1, px: 2 }}>
              <Typography variant="body2" color="textSecondary" sx={{ textWrap: "nowrap" }}>
                {t("teamSettingsPage.teamBanner.label")}
              </Typography>
            </Box>

            <Box sx={{ position: "relative" }}>
              <TeamBanner
                teamName={team?.name}
                imageUrl={team?.banner_image_url}
                alt={t("teamSettingsPage.teamBanner.alt")}
                height="6rem"
                width="450px"
                borderRadius={theme.spacing(1)}
              />
            </Box>
          </Box>

          <TextField
            value={team?.description || ""}
            variant="outlined"
            multiline
            minRows={3}
            label={t("teamSettingsPage.description.label")}
            slotProps={{
              htmlInput: { maxLength: 180, readOnly: true },
            }}
            helperText={`${team?.description?.length || 0}/180`}
            disabled
          />

          <FormControlLabel
            control={<Switch color="primary" checked={team?.is_private ?? false} disabled />}
            label={t("teamSettingsPage.private.label")}
            labelPlacement="start"
            sx={{
              width: "100%",
              background: alpha(theme.palette.text.primary, 0.08),
              justifyContent: "space-between",
              ml: 0,
              pl: 2,
              pr: 1,
              py: 0.5,
              borderRadius: 2,
            }}
          />
        </Box>
      </Paper>
    </Box>
  );
}
