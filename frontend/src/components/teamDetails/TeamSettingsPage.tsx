import UploadFileIcon from "@mui/icons-material/UploadFile";
import { alpha, Box, Button, FormControlLabel, Paper, Switch, TextField, Typography, useTheme } from "@mui/material";
import { useEffect, useMemo } from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import { useDebounce } from "../../hooks/useDebounce";
import { Team } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation } from "../../slices/knowledgeFlow/knowledgeFlowApiEnhancements";

const teamSettingsSchema = z.object({
  description: z.string().max(180).optional(),
  is_private: z.boolean(),
});

type TeamSettingsFormData = z.infer<typeof teamSettingsSchema>;

export interface TeamSettingsPageProps {
  team?: Team;
}

export function TeamSettingsPage({ team }: TeamSettingsPageProps) {
  const { t } = useTranslation();
  const theme = useTheme();

  const [updateTeam] = useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation();

  const defaultValues = useMemo(
    () => ({
      description: team?.description || "",
      is_private: team?.is_private ?? false,
    }),
    [team?.id]
  );

  const { control, watch, reset } = useForm<TeamSettingsFormData>({
    resolver: zodResolver(teamSettingsSchema),
    defaultValues,
  });

  // Only reset form when switching to a different team
  useEffect(() => {
    reset({
      description: team?.description || "",
      is_private: team?.is_private ?? false,
    });
  }, [team?.id, reset]);

  const formValues = watch();
  const debouncedDescription = useDebounce(formValues.description, 500);
  const debouncedIsPrivate = useDebounce(formValues.is_private, 300);

  // Handle description updates
  useEffect(() => {
    if (!team?.id) return;
    if (debouncedDescription === team.description) return;

    updateTeam({
      teamId: team.id,
      teamUpdate: { description: debouncedDescription },
    });
  }, [debouncedDescription, team?.id, team?.description, updateTeam]);

  // Handle is_private updates
  useEffect(() => {
    if (!team?.id) return;
    if (debouncedIsPrivate === team.is_private) return;

    updateTeam({
      teamId: team.id,
      teamUpdate: { is_private: debouncedIsPrivate },
    });
  }, [debouncedIsPrivate, team?.id, team?.is_private, updateTeam]);

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
              src={team?.banner_image_url || ""}
              style={{ height: "6rem", borderRadius: theme.spacing(1), width: "450px", objectFit: "cover" }}
            />
          </Box>

          {/* Description */}
          <Controller
            name="description"
            control={control}
            render={({ field, fieldState }) => (
              <TextField
                {...field}
                variant="outlined"
                multiline
                minRows={3}
                label={t("teamSettingsPage.description.label")}
                placeholder={t("teamSettingsPage.description.placeholder")}
                inputProps={{ maxLength: 180 }}
                helperText={`${field.value?.length || 0}/180`}
                error={!!fieldState.error}
              />
            )}
          />

          {/* Private check */}
          <Controller
            name="is_private"
            control={control}
            render={({ field }) => (
              <FormControlLabel
                control={<Switch color="primary" checked={field.value} onChange={field.onChange} />}
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
            )}
          />

          <Box></Box>
        </Box>
      </Paper>
    </Box>
  );
}
