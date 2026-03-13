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
  FormLabel,
  Grid,
  Paper,
  Radio,
  RadioGroup,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import React from "react";
import { Controller, useForm, useWatch } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

// OpenAPI-generated types & hook
import {
  CreateAgentRequest,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
  useListAgentsAgenticV1AgentsGetQuery as useListAgentsQuery,
  useListDeclaredAgentClassPathsAgenticV1AgentsClassPathsGetQuery as useListDeclaredAgentClassPathsQuery,
  useListReactAgentProfilesAgenticV1AgentsReactProfilesGetQuery as useListReactProfilesQuery,
} from "../../slices/agentic/agenticOpenApi";

import { KeyCloakService } from "../../security/KeycloakService";
import { useToast } from "../ToastProvider";

const createSimpleAgentSchema = (t: (key: string, options?: any) => string) =>
  z.object({
    name: z.string().min(1, { message: t("validation.required") }),
    type: z.literal("basic"),
    creation_mode: z.enum(["basic", "profile", "class", "definition"]),
    profile_id: z.string().optional(),
    class_path: z.string().optional(),
    definition_ref: z.string().optional(),
  });

type FormData = z.infer<ReturnType<typeof createSimpleAgentSchema>>;

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
  initialType?: "basic";
  teamId?: string;
}

export const CreateAgentModal: React.FC<CreateAgentModalProps> = ({
  open,
  onClose,
  onCreated,
  initialType = "basic",
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
    setValue,
    formState: { errors, isSubmitting },
    reset,
  } = useForm<FormData>({
    resolver: zodResolver(schema),
    defaultValues: {
      name: "",
      type: initialType,
      creation_mode: "basic",
      profile_id: "",
      class_path: "",
      definition_ref: "",
    },
  });
  const watchCreationMode = useWatch({ control, name: "creation_mode", defaultValue: "basic" });
  const watchProfileId = useWatch({ control, name: "profile_id", defaultValue: "" });
  const watchDefinitionRef = useWatch({ control, name: "definition_ref", defaultValue: "" });
  const isClassCreation = isAdmin && watchCreationMode === "class";
  const isDefinitionCreation = watchCreationMode === "definition";
  const { data: reactProfiles = [], isFetching: isProfilesLoading } = useListReactProfilesQuery(undefined, {
    skip: false,
  });
  const hasReactProfiles = reactProfiles.length > 0;
  const isProfileCreation = watchCreationMode === "profile" && hasReactProfiles;

  React.useEffect(() => {
    if (!hasReactProfiles && watchCreationMode === "profile") {
      setValue("creation_mode", "basic", { shouldDirty: true });
      setValue("profile_id", "", { shouldDirty: true });
      return;
    }

    if (!hasReactProfiles) {
      return;
    }

    const selectedStillExists = reactProfiles.some((profile) => profile.profile_id === watchProfileId);
    if (!selectedStillExists) {
      setValue("profile_id", reactProfiles[0].profile_id, { shouldDirty: false });
    }
  }, [hasReactProfiles, reactProfiles, setValue, watchCreationMode, watchProfileId]);

  const { data: declaredClassPaths = [], isFetching: isClassPathLoading } = useListDeclaredAgentClassPathsQuery(
    undefined,
    {
      skip: !isAdmin || !isClassCreation,
    },
  );
  const { data: availableAgents = [] } = useListAgentsQuery({});
  const selectedProfile = reactProfiles.find((profile) => profile.profile_id === watchProfileId) ?? null;
  const knownDefinitionRefs = React.useMemo<string[]>(() => ["v2.demo.postal_tracking_workflow"], []);
  const definitionRefsFromAgents = React.useMemo<string[]>(
    () =>
      Array.from(
        new Set(
          (availableAgents || [])
            .map((agent) => agent.definition_ref)
            .filter((value): value is string => typeof value === "string" && value.trim().length > 0)
            .map((value) => value.trim()),
        ),
      ),
    [availableAgents],
  );
  const definitionRefOptions = React.useMemo<string[]>(
    () => Array.from(new Set([...knownDefinitionRefs, ...definitionRefsFromAgents])).sort((a, b) => a.localeCompare(b)),
    [definitionRefsFromAgents, knownDefinitionRefs],
  );

  React.useEffect(() => {
    if (!isDefinitionCreation) {
      return;
    }
    if (watchDefinitionRef && watchDefinitionRef.trim().length > 0) {
      return;
    }
    if (definitionRefOptions.length === 0) {
      return;
    }
    setValue("definition_ref", definitionRefOptions[0], { shouldDirty: false });
  }, [definitionRefOptions, isDefinitionCreation, setValue, watchDefinitionRef]);

  const submit = async (data: FormData) => {
    if (data.creation_mode === "profile" && !data.profile_id?.trim()) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.profileRequired"),
      });
      return;
    }

    if (data.creation_mode === "class" && !data.class_path?.trim()) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.classPathRequired"),
      });
      return;
    }
    if (data.creation_mode === "definition" && !data.definition_ref?.trim()) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.definitionRefRequired", {
          defaultValue: "A definition reference is required.",
        }),
      });
      return;
    }

    const req: CreateAgentRequest = {
      name: data.name.trim(),
      type: "basic",
      team_id: teamId,
      class_path: data.creation_mode === "class" ? data.class_path?.trim() || undefined : undefined,
      definition_ref: data.creation_mode === "definition" ? data.definition_ref?.trim() || undefined : undefined,
      profile_id: data.creation_mode === "profile" ? data.profile_id?.trim() || undefined : undefined,
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
      <DialogTitle>{t("agentHub.createAgent")}</DialogTitle>
      <DialogContent dividers>
        {/* Note: The <form> element is required for handleSubmit, but we'll manually trigger it below */}
        <form onSubmit={handleSubmit(submit)}>
          <Grid container spacing={2}>
            <Grid size={12}>
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
            </Grid>

            <Grid size={12}>
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
                        value: "definition",
                        title: t("agentHub.fields.creationModeDefinition", {
                          defaultValue: "Definition ref",
                        }),
                        description: t("agentHub.fields.creationModeDefinitionHelp", {
                          defaultValue: "Create from a backend v2 definition reference.",
                        }),
                      },
                      ...(hasReactProfiles
                        ? [
                            {
                              value: "profile",
                              title: t("agentHub.fields.creationModeProfile"),
                              description: t("agentHub.fields.creationModeProfileHelp"),
                            },
                          ]
                        : []),
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
            </Grid>

            {isProfileCreation && (
              <Grid size={12}>
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
              </Grid>
            )}

            {isClassCreation && (
              <Grid size={12}>
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
              </Grid>
            )}
            {isDefinitionCreation && (
              <Grid size={12}>
                <Controller
                  name="definition_ref"
                  control={control}
                  render={({ field: f }) => (
                    <Autocomplete
                      freeSolo
                      options={definitionRefOptions}
                      value={f.value || ""}
                      onInputChange={(_, value) => {
                        f.onChange(value);
                      }}
                      onChange={(_, value) => {
                        f.onChange(typeof value === "string" ? value : "");
                      }}
                      noOptionsText={t("agentHub.fields.definitionRefNoOptions", {
                        defaultValue: "No predefined definition refs.",
                      })}
                      renderInput={(params) => (
                        <TextField
                          {...params}
                          fullWidth
                          size="small"
                          required
                          label={t("agentHub.fields.definitionRef", {
                            defaultValue: "Definition reference",
                          })}
                          placeholder="v2.demo.postal_tracking_workflow"
                          helperText={t("agentHub.fields.definitionRefHelp", {
                            defaultValue: "Example: v2.demo.postal_tracking_workflow",
                          })}
                        />
                      )}
                    />
                  )}
                />
              </Grid>
            )}
          </Grid>
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
          {t("dialogs.create.confirm")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
