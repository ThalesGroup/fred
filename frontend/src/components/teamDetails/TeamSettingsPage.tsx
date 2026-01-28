import UploadFileIcon from "@mui/icons-material/UploadFile";
import { alpha, Box, Button, FormControlLabel, Paper, Switch, TextField, Typography, useTheme } from "@mui/material";
import { useTranslation } from "react-i18next";
import { GroupSummary } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";

export interface TeamSettingsPageProps {
  team: GroupSummary;
}

export function TeamSettingsPage({ team }: TeamSettingsPageProps) {
  const { t } = useTranslation();
  const theme = useTheme();
  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <Paper sx={{ borderRadius: 2, flex: 1, display: "flex", justifyContent: "center" }}>
        <Box sx={{ maxWidth: "600px", display: "flex", flexDirection: "column", gap: 2, py: 2 }}>
          {/* Banner */}
          <Box sx={{ display: "flex", alignItems: "center" }}>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1, px: 2 }}>
              <Typography variant="body2" color="textSecondary" sx={{ textWrap: "nowrap" }}>
                {t("teamSettingsPage.teamBanner.label")}
              </Typography>
              <Button variant="outlined" startIcon={<UploadFileIcon />}>
                {t("teamSettingsPage.teamBanner.buttonLabel")}
              </Button>
            </Box>
            {/* Banner Preview */}
            <img
              src={team.banner_image_url}
              style={{ height: "6rem", borderRadius: theme.spacing(1), width: "450px", objectFit: "cover" }}
            />
          </Box>

          {/* Description */}
          {/* todo: set max char at 180 + display number of char in helper text */}
          <TextField
            variant="outlined"
            multiline
            minRows={3}
            label={t("teamSettingsPage.description.label")}
            placeholder={t("teamSettingsPage.description.placeholder")}
            inputProps={{ maxLength: 180 }}
            // todo:
            // helperText={`${description.length}/180`}
          />

          {/* Private check */}
          <FormControlLabel
            value="Toto"
            control={<Switch color="primary" />}
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

          <Box></Box>
        </Box>
      </Paper>
    </Box>
  );
}
