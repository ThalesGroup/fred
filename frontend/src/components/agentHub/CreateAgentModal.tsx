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
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  FormLabel,
  Switch,
  TextField,
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
} from "../../slices/agentic/agenticOpenApi";

import { useToast } from "../ToastProvider";

const createSimpleAgentSchema = (t: (key: string, options?: any) => string) =>
  z.object({
    name: z.string().min(1, { message: t("validation.required") }),
    type: z.enum(["basic", "a2a_proxy"]),
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
      a2a_base_url: "",
      a2a_token: "",
    },
  });
  const watchType = useWatch({ control, name: "type", defaultValue: initialType });
  const isA2aType = watchType === "a2a_proxy";

  const submit = async (data: FormData) => {
    if (data.type === "a2a_proxy" && !data.a2a_base_url) {
      showError({
        summary: t("validation.required"),
        detail: t("agentHub.fields.a2aBaseUrlRequired"),
      });
      return;
    }

    const req: CreateAgentRequest = {
      name: data.name.trim(),
      type: data.type,
      team_id: teamId,
      a2a_base_url: data.type === "a2a_proxy" ? data.a2a_base_url?.trim() || undefined : undefined,
      a2a_token: data.type === "a2a_proxy" ? data.a2a_token?.trim() || undefined : undefined,
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
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
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
