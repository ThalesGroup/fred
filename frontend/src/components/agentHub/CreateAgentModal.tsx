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
import {
  Autocomplete,
  Box,
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  Switch,
  TextField,
  Typography,
} from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import React from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

// OpenAPI-generated types & hook
import {
  CreateAgentRequest,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery as useListDeclaredAgentClassPathsQuery,
  useListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery as useListReactProfilesQuery,
} from "../../slices/agentic/agenticOpenApi";

import { KeyCloakService } from "../../security/KeycloakService";
import { useToast } from "../ToastProvider";

const DEFAULT_REACT_PROFILE_ID = "generic_assistant";
const LEGACY_V1_REACT_CLASS_PATH = "agentic_backend.core.agents.basic_react_agent.BasicReActAgent";

const createSimpleAgentSchema = (t: (key: string, options?: any) => string) =>
  z.object({
    name: z.string().min(1, { message: t("validation.required") }),
    type: z.enum(["basic", "a2a_proxy"]),
    creation_mode: z.enum(["basic", "profile", "legacy_v1", "class"]),
    profile_id: z.string().optional(),
    a2a_base_url: z.union([
      z.literal(""),
      z
        .string()
        .trim()
        .refine(
          (val) => {
            try {
              new URL(val);
              return true;
            } catch {
              return false;
            }
          },
          { message: t("common.invalidUrl") },
        ),
    ]),
    a2a_token: z.string().optional(),
    class_path: z.string().optional(),
  });

type FormData = z.infer<ReturnType<typeof createSimpleAgentSchema>>;

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  initialType?: "basic" | "a2a_proxy";
  disableTypeToggle?: boolean;
  teamId?: string;
}

export const CreateAgentModal: React.FC<CreateAgentModalProps> = ({
  open,
  onClose,
  onCreated,
  initialType = "basic",
  disableTypeToggle = false,
  teamId,
}) => {
  const { t } = useTranslation();
  const schema = createSimpleAgentSchema(t);
  const { showError, showSuccess } = useToast();
  const userRoles = KeyCloakService.GetUserRoles();
  const isAdmin = userRoles.includes("admin");
  const [createAgent, { isLoading }] = useCreateAgentAgenticV1AgentsCreatePostMutation();

  const {
    control,
    handleSubmit,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      type: initialType,
      creation_mode: "basic",
      profile_id: DEFAULT_REACT_PROFILE_ID,
      a2a_base_url: "",
      a2a_token: "",
      class_path: "",
    },
  });
  const watchType = useWatch({ control, name: "type", defaultValue: initialType });
  const watchCreationMode = useWatch({ control, name: "creation_mode", defaultValue: "basic" });
  const watchProfileId = useWatch({ control, name: "profile_id", defaultValue: DEFAULT_REACT_PROFILE_ID });
  const isA2aType = watchType === "a2a_proxy";
  const isProfileCreation = !isA2aType && watchCreationMode === "profile";
  const isLegacyV1Creation = !isA2aType && watchCreationMode === "legacy_v1";
  const isClassCreation = isAdmin && !isA2aType && watchCreationMode === "class";
  const { data: reactProfiles = [], isFetching: isProfilesLoading } = useListReactProfilesQuery(undefined, {
    skip: isA2aType,
  });
  const { data: declaredClassPaths = [], isFetching: isClassPathLoading } = useListDeclaredAgentClassPathsQuery(
    undefined,
    {
      skip: !isAdmin || isA2aType || !isClassCreation,
    },
  );
  const selectedProfile = reactProfiles.find((profile) => profile.profile_id === watchProfileId) ?? null;

  const submit = async (data: FormData) => {
    if (data.type === "a2a_proxy" && !data.a2a_base_url) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.a2aBaseUrlRequired"),
      });
      return;
    }

    if (data.type !== "a2a_proxy" && data.creation_mode === "profile" && !data.profile_id?.trim()) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.profileRequired"),
      });
      return;
    }

    if (data.type !== "a2a_proxy" && data.creation_mode === "class" && !data.class_path?.trim()) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.classPathRequired"),
      });
      return;
    }

    const req: CreateAgentRequest = {
      name: data.name.trim(),
      type: data.type,
      team_id: teamId,
      a2a_base_url: data.type === "a2a_proxy" ? data.a2a_base_url?.trim() || undefined : undefined,
      a2a_token: data.type === "a2a_proxy" ? data.a2a_token?.trim() || undefined : undefined,
      class_path:
        data.type !== "a2a_proxy"
          ? data.creation_mode === "class"
            ? data.class_path?.trim() || undefined
            : data.creation_mode === "legacy_v1"
              ? LEGACY_V1_REACT_CLASS_PATH
              : undefined
          : undefined,
      profile_id:
        data.type !== "a2a_proxy" && data.creation_mode === "profile"
          ? data.profile_id?.trim() || undefined
          : undefined,
    };

    try {
      await createAgent({ createAgentRequest: req }).unwrap();
      onCreated();
      reset();
      onClose();
      showSuccess({
        summary: t("agentHub.success.summary"),
        detail: t("agentHub.success.detail"),
      });
    } catch (e: any) {
      showError({
        title: t("agentHub.errors.creationFailedSummary"),
        summary: t("agentHub.errors.creationFailedSummary"),
        detail: e?.data?.detail || e.message || e.toString(),
      });
      console.error("Create agent failed:", e);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{isA2aType ? t("agentHub.registerA2A") : t("agentHub.createAgent")}</DialogTitle>
      <DialogContent dividers>
        {/* Note: The <form> element is required for handleSubmit, but we'll manually trigger it below */}
        <form onSubmit={handleSubmit(submit)}>
          <Grid2 container spacing={2}>
            <Grid2 size={12}>
              <Controller
                name="name"
                control={control}
                render={({ field: f }) => (
                  <TextField
                    autoFocus
                    {...f}
                    fullWidth
                    size="small"
                    required
                    label={t("agentHub.fields.name")}
                    error={!!errors.name}
                    helperText={(errors.name?.message as string) || ""}
                  />
                )}
              />
            </Grid2>

            {!disableTypeToggle && (
              <Grid2 size={12}>
                <FormControl component="fieldset" fullWidth>
                  <FormLabel component="legend">{t("agentHub.fields.agentType")}</FormLabel>
                  <Controller
                    name="type"
                    control={control}
                    render={({ field }) => (
                      <FormControlLabel
                        control={
                          <Switch
                            size="small"
                            checked={field.value === "a2a_proxy"}
                            onChange={(_, checked) => field.onChange(checked ? "a2a_proxy" : "basic")}
                          />
                        }
                        label={t("agentHub.fields.a2aProxyToggle")}
                      />
                    )}
                  />
                </FormControl>
              </Grid2>
            )}

            {!isA2aType && (
              <Grid2 size={12}>
                <FormControl component="fieldset" fullWidth>
                  <FormLabel component="legend">{t("agentHub.fields.creationMode")}</FormLabel>
                  <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                    {t("agentHub.fields.creationModeHelp")}
                  </Typography>
                  <Controller
                    name="creation_mode"
                    control={control}
                    render={({ field: f }) => {
                      const options = [
                        {
                          value: "basic",
                          title: t("agentHub.fields.creationModeBasic"),
                          description: t("agentHub.fields.creationModeBasicHelp"),
                        },
                        {
                          value: "profile",
                          title: t("agentHub.fields.creationModeProfile"),
                          description: t("agentHub.fields.creationModeProfileHelp"),
                        },
                        {
                          value: "legacy_v1",
                          title: t("agentHub.fields.creationModeLegacyV1"),
                          description: t("agentHub.fields.creationModeLegacyV1Help"),
                        },
                        ...(isAdmin
                          ? [
                              {
                                value: "class",
                                title: t("agentHub.fields.creationModeClass"),
                                description: t("agentHub.fields.creationModeClassHelp"),
                              },
                            ]
                          : []),
                      ];

                      return (
                        <RadioGroup
                          value={f.value}
                          onChange={(event) => {
                            f.onChange(event.target.value);
                          }}
                        >
                          <Stack spacing={1.25}>
                            {options.map((option) => {
                              const selected = f.value === option.value;
                              return (
                                <Paper
                                  key={option.value}
                                  variant="outlined"
                                  onClick={() => f.onChange(option.value)}
                                  sx={{
                                    p: 1.5,
                                    cursor: "pointer",
                                    borderColor: selected ? "primary.main" : "divider",
                                    backgroundColor: selected ? "action.selected" : "background.paper",
                                  }}
                                >
                                  <Stack direction="row" spacing={1.5} alignItems="flex-start">
                                    <Radio
                                      checked={selected}
                                      value={option.value}
                                      onChange={(event) => f.onChange(event.target.value)}
                                      sx={{ mt: -0.5 }}
                                    />
                                    <Box>
                                      <Typography variant="subtitle2">{option.title}</Typography>
                                      <Typography variant="body2" color="text.secondary">
                                        {option.description}
                                      </Typography>
                                    </Box>
                                  </Stack>
                                </Paper>
                              );
                            })}
                          </Stack>
                        </RadioGroup>
                      );
                    }}
                  />
                </FormControl>
              </Grid2>
            )}

            {isProfileCreation && (
              <Grid2 size={12}>
                <Controller
                  name="profile_id"
                  control={control}
                  render={({ field: f }) => (
                    <Autocomplete
                      options={reactProfiles}
                      loading={isProfilesLoading}
                      value={selectedProfile}
                      isOptionEqualToValue={(option, value) => option.profile_id === value.profile_id}
                      getOptionLabel={(option) => option.title}
                      onChange={(_, value) => {
                        f.onChange(value?.profile_id || "");
                      }}
                      noOptionsText={t("agentHub.fields.profileNoOptions")}
                      renderOption={(props, option) => (
                        <li {...props} key={option.profile_id}>
                          <div>
                            <div>{option.title}</div>
                            <small>{option.description}</small>
                          </div>
                        </li>
                      )}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          fullWidth
                          size="small"
                          label={t("agentHub.fields.profile")}
                          helperText={selectedProfile?.agent_description || t("agentHub.fields.profileHelp")}
                        />
                      )}
                    />
                  )}
                />
              </Grid2>
            )}

            {isClassCreation && (
              <Grid2 size={12}>
                <Controller
                  name="class_path"
                  control={control}
                  render={({ field: f }) => (
                    <Autocomplete
                      options={declaredClassPaths}
                      loading={isClassPathLoading}
                      value={f.value || null}
                      onChange={(_, value) => {
                        f.onChange((value || "").toString());
                      }}
                      noOptionsText={t("agentHub.fields.classPathNoOptions")}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          fullWidth
                          size="small"
                          label={t("agentHub.fields.classPath")}
                          placeholder="my_module.agents.MyCustomAgent"
                          helperText={t("agentHub.fields.classPathHelp")}
                        />
                      )}
                    />
                  )}
                />
              </Grid2>
            )}

            {isLegacyV1Creation && (
              <Grid2 size={12}>
                <Typography variant="body2" color="text.secondary">
                  {t("agentHub.fields.creationModeLegacyV1Note")}
                </Typography>
              </Grid2>
            )}

            {watchType === "a2a_proxy" && (
              <>
                <Controller
                  name="a2a_base_url"
                  control={control}
                  render={({ field: f }) => (
                    <Grid2 size={12}>
                      <TextField
                        {...f}
                        fullWidth
                        size="small"
                        label={t("agentHub.fields.a2aBaseUrl")}
                        placeholder="https://example.com"
                        required
                      />
                    </Grid2>
                  )}
                />

                <Controller
                  name="a2a_token"
                  control={control}
                  render={({ field: f }) => (
                    <Grid2 size={12}>
                      <TextField
                        {...f}
                        fullWidth
                        size="small"
                        label={t("agentHub.fields.a2aToken")}
                        placeholder={t("agentHub.fields.optional")}
                      />
                    </Grid2>
                  )}
                />
              </>
            )}
          </Grid2>
        </form>
      </DialogContent>

      <DialogActions>
        <Button size="small" onClick={onClose} disabled={isLoading || isSubmitting}>
          {t("dialogs.cancel")}
        </Button>
        <Button
          size="small"
          type="submit"
          variant="contained"
          onClick={handleSubmit(submit)}
          disabled={isLoading || isSubmitting}
        >
          {isA2aType ? t("agentHub.registerA2A") : t("dialogs.create.confirm")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
