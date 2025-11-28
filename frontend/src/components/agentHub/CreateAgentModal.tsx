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
import { Button, Dialog, DialogActions, DialogContent, DialogTitle, TextField, Typography } from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import React from "react";
import { Controller, useForm } from "react-hook-form";
import { useTranslation } from "react-i18next";
import { z } from "zod";

// OpenAPI-generated types & hook
import {
  CreateMcpAgentRequest,
  useCreateAgentAgenticV1AgentsCreatePostMutation,
} from "../../slices/agentic/agenticOpenApi";

import { useToast } from "../ToastProvider";

// 1. Simplified Schema: Only includes the required 'name' field
const createSimpleAgentSchema = (t: (key: string, options?: any) => string) =>
  z.object({
    name: z.string().min(1, { message: t("validation.required", { defaultValue: "Required" }) }),
  });

type FormData = z.infer<ReturnType<typeof createSimpleAgentSchema>>;

interface CreateAgentModalProps {
  open: boolean;
  onClose: () => void;
  onCreated: () => void;
}

export const CreateAgentModal: React.FC<CreateAgentModalProps> = ({ open, onClose, onCreated }) => {
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
    },
  });

  const submit = async (data: FormData) => {
    // 2. Construct the request object.
    // Set all suppressed fields to safe, empty values to satisfy the API contract.
    const req: CreateMcpAgentRequest = {
      name: data.name.trim(),
    };

    try {
      await createAgent({ createMcpAgentRequest: req }).unwrap();
      onCreated();
      reset();
      onClose();
      showSuccess({
        summary: t("agentHub.success.summary", "Agent created"),
        detail: t("agentHub.success.detail"),
      });
    } catch (e: any) {
      showError({
        title: t("agentHub.errors.creationFailedSummary"),
        summary: t("agentHub.errors.creationFailedSummary"),
        detail: e?.data?.detail || e.message || e.toString(),
      });
      console.error("Create MCP agent failed:", e);
    }
  };

  return (
    <Dialog open={open} onClose={onClose} fullWidth maxWidth="xs">
      <DialogTitle>{t("agentHub.createMcpAgent")}</DialogTitle>
      <DialogContent dividers>
        {/* Note: The <form> element is required for handleSubmit, but we'll manually trigger it below */}
        <form onSubmit={handleSubmit(submit)}>
          <Grid2 container spacing={2}>
            <Grid2 size={12}>
              <Typography variant="body2" color="textSecondary" mb={2}>
                {t("agentHub.createMcpAgent")}
              </Typography>
              {/* Only the 'name' field remains in the UI */}
              <Controller
                name="name"
                control={control}
                render={({ field: f }) => (
                  <TextField
                    {...f}
                    fullWidth
                    size="small"
                    required
                    label={t("agentHub.fields.name", "Agent Name")}
                    error={!!errors.name}
                    helperText={(errors.name?.message as string) || ""}
                  />
                )}
              />
            </Grid2>
          </Grid2>
        </form>
      </DialogContent>

      <DialogActions>
        <Button size="small" onClick={onClose} disabled={isLoading || isSubmitting}>
          {t("dialogs.cancel", "Cancel")}
        </Button>
        <Button
          size="small"
          type="submit"
          variant="contained"
          onClick={handleSubmit(submit)}
          disabled={isLoading || isSubmitting}
        >
          {t("dialogs.create.confirm", "Create")}
        </Button>
      </DialogActions>
    </Dialog>
  );
};
