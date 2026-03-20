import { alpha, Box, Button, FormControlLabel, Paper, Switch, TextField, Typography, useTheme } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";
import { Team, useUpdateTeamMutation } from "../../slices/controlPlane/controlPlaneApi";
import { TeamBanner } from "../teams/TeamVisuals";

export interface TeamSettingsPageProps {
  team?: Team;
}

export function TeamSettingsPage({ team }: TeamSettingsPageProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  const [updateTeam, { isLoading, isSuccess, isError }] = useUpdateTeamMutation();
  const [description, setDescription] = useState(team?.description || "");
  const [isPrivate, setIsPrivate] = useState(team?.is_private ?? false);

  useEffect(() => {
    setDescription(team?.description || "");
    setIsPrivate(team?.is_private ?? false);
  }, [team?.id, team?.description, team?.is_private]);

  const hasChanges = useMemo(() => {
    return description !== (team?.description || "") || isPrivate !== (team?.is_private ?? false);
  }, [description, isPrivate, team?.description, team?.is_private]);

  const handleSave = async () => {
    if (!team?.id || !hasChanges || isLoading) return;
    try {
      await updateTeam({
        teamId: team.id,
        updateTeamRequest: {
          description,
          is_private: isPrivate,
        },
      }).unwrap();
    } catch {
      // Error state is exposed via `isError`.
    }
  };

  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <Paper sx={{ borderRadius: 2, flex: 1, display: "flex", justifyContent: "center" }}>
        <Box sx={{ maxWidth: "600px", display: "flex", flexDirection: "column", gap: 2, py: 2 }}>
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
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            variant="outlined"
            multiline
            minRows={3}
            label={t("teamSettingsPage.description.label")}
            slotProps={{ htmlInput: { maxLength: 180 } }}
            helperText={`${description.length}/180`}
          />

          <FormControlLabel
            control={<Switch color="primary" checked={isPrivate} onChange={(event) => setIsPrivate(event.target.checked)} />}
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

          <Box sx={{ display: "flex", justifyContent: "space-between", alignItems: "center", gap: 2 }}>
            <Box>
              {isError && (
                <Typography variant="body2" color="error.main">
                  {t("teamSettingsPage.saveError", "Failed to save team settings.")}
                </Typography>
              )}
              {isSuccess && !isError && (
                <Typography variant="body2" color="success.main">
                  {t("teamSettingsPage.saveSuccess", "Team settings saved.")}
                </Typography>
              )}
            </Box>
            <Button variant="contained" onClick={handleSave} disabled={!team?.id || !hasChanges || isLoading}>
              {isLoading ? t("teamSettingsPage.saving", "Saving...") : t("teamSettingsPage.save", "Save")}
            </Button>
          </Box>
        </Box>
      </Paper>
    </Box>
  );
}
