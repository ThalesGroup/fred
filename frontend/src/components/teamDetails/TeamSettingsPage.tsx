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

import { zodResolver } from "@hookform/resolvers/zod";
import UploadFileIcon from "@mui/icons-material/UploadFile";
import {
  alpha,
  Box,
  Button,
  CircularProgress,
  FormControlLabel,
  Paper,
  Switch,
  TextField,
  Typography,
  useTheme,
} from "@mui/material";
import { useEffect, useMemo, useRef } from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";
import { useDebounce } from "../../hooks/useDebounce";
import {
  useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation,
  useUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostMutation,
} from "../../slices/knowledgeFlow/knowledgeFlowApiEnhancements";
import { Team } from "../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useToast } from "../ToastProvider";
import { TeamBanner } from "../teams/TeamVisuals";

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
  const { showError, showSuccess } = useToast();

  const [updateTeam] = useUpdateTeamKnowledgeFlowV1TeamsTeamIdPatchMutation();
  const [uploadBanner, { isLoading: isUploadingBanner }] =
    useUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPostMutation();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Constants for validation
  const MAX_BANNER_SIZE = 5 * 1024 * 1024; // 5MB
  const ALLOWED_TYPES = ["image/jpeg", "image/png", "image/webp"];

  const defaultValues = useMemo(
    () => ({
      description: team?.description || "",
      is_private: team?.is_private ?? false,
    }),
    [team?.id],
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

  // Handle banner upload
  const handleBannerUpload = async (event: React.ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0];
    if (!file || !team?.id) return;

    // Client-side validation
    if (!ALLOWED_TYPES.includes(file.type)) {
      showError({
        summary: t("teamSettingsPage.teamBanner.invalidType"),
        detail: "",
      });
      return;
    }

    if (file.size > MAX_BANNER_SIZE) {
      showError({
        summary: t("teamSettingsPage.teamBanner.tooLarge"),
        detail: "",
      });
      return;
    }

    try {
      await uploadBanner({
        teamId: team.id,
        bodyUploadTeamBannerKnowledgeFlowV1TeamsTeamIdBannerPost: { file },
      }).unwrap();

      showSuccess({
        summary: t("teamSettingsPage.teamBanner.uploadSuccess"),
        detail: "",
      });
      // RTK Query will automatically invalidate and refetch team data
    } catch (error) {
      console.error("Banner upload error:", error);
      showError({
        summary: t("teamSettingsPage.teamBanner.uploadError"),
        detail: "",
      });
    } finally {
      // Reset file input
      if (fileInputRef.current) fileInputRef.current.value = "";
    }
  };

  return (
    <Box sx={{ px: 2, pb: 2, display: "flex", height: "100%" }}>
      <Paper sx={{ borderRadius: 2, flex: 1, display: "flex", justifyContent: "center" }}>
        <Box sx={{ maxWidth: "600px", display: "flex", flexDirection: "column", gap: 2, py: 2 }}>
          {/* Banner */}
          <Box sx={{ display: "flex", alignItems: "center", gap: 2 }}>
            <Box sx={{ display: "flex", flexDirection: "column", gap: 1, px: 2 }}>
              <Typography variant="body2" color="textSecondary" sx={{ textWrap: "nowrap" }}>
                {t("teamSettingsPage.teamBanner.label")}
              </Typography>

              {/* Hidden file input */}
              <input
                type="file"
                ref={fileInputRef}
                accept="image/jpeg,image/png,image/webp"
                style={{ display: "none" }}
                onChange={handleBannerUpload}
              />

              <Button
                variant="outlined"
                startIcon={isUploadingBanner ? <CircularProgress size={20} /> : <UploadFileIcon />}
                onClick={() => fileInputRef.current?.click()}
                disabled={isUploadingBanner}
              >
                {t("teamSettingsPage.teamBanner.buttonLabel")}
              </Button>
            </Box>

            {/* Banner Preview */}
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
                slotProps={{
                  htmlInput: { maxLength: 180 },
                }}
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
