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

import {
  Button,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  Stack,
  TextField,
} from "@mui/material";
import * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import yaml from "js-yaml";
import { buildPromptYaml, looksLikeYamlDoc, splitFrontMatter, buildFrontMatter } from "./resourceYamlUtils";

const promptSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  body: z.string().min(1, "Prompt body is required"),
});

type PromptFormData = z.infer<typeof promptSchema>;

type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // YAML with '---'
};

interface PromptEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: { name?: string; description?: string; labels?: string[]; content: string }) => void;
  initial?: Partial<{ name: string; description?: string; body?: string; yaml?: string; labels?: string[] }>;
  getSuggestion?: () => Promise<string>;
}

/** Modal supports two modes:
 *  - simple mode (name/description/body)
 *  - doc mode (header YAML + body) when initial content is a full YAML doc
 */
export const PromptEditorModal: React.FC<PromptEditorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initial,
}) => {
  const incomingDoc = useMemo(() => (initial as any)?.yaml ?? (initial as any)?.body ?? "", [initial]);
  const isDocMode = useMemo(() => looksLikeYamlDoc(incomingDoc), [incomingDoc]);

  // ----- Simple mode form (create) -----
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<PromptFormData>({
    resolver: zodResolver(promptSchema),
    defaultValues: { name: "", description: "", body: "" },
  });

  // ----- Doc mode state (edit header+body) -----
  const [headerText, setHeaderText] = useState<string>("");
  const [bodyText, setBodyText] = useState<string>("");
  const [headerError, setHeaderError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    if (isDocMode) {
      const { header, body } = splitFrontMatter(incomingDoc);
      setHeaderText(yaml.dump(header).trim());
      setBodyText(body);
    } else {
      reset({
        name: initial?.name ?? "",
        description: initial?.description ?? "",
        body: incomingDoc || "",
      });
    }
  }, [isOpen, isDocMode, incomingDoc, initial?.name, initial?.description, reset]);

  // ----- Submit handlers -----
  const onSubmitSimple = (data: PromptFormData) => {
    const body = (data.body || "").trim();
    const content = looksLikeYamlDoc(body)
      ? body
      : buildPromptYaml({
          name: data.name,
          description: data.description || undefined,
          labels: undefined,
          body,
        });

    const payload: ResourceCreateLike = {
      name: data.name,
      description: data.description || undefined,
      content,
    };
    onSave(payload);
    onClose();
  };

  const onSubmitDoc = () => {
    // Parse header YAML back to object
    let headerObj: Record<string, any>;
    try {
      headerObj = (yaml.load(headerText || "") as Record<string, any>) ?? {};
      setHeaderError(null);
    } catch (e: any) {
      setHeaderError(e?.message || "Invalid YAML");
      return;
    }
    // Ensure kind (UI safety; backend can still validate)
    if (!headerObj.kind) headerObj.kind = "prompt";

    const content = buildFrontMatter(headerObj, bodyText);
    onSave({
      content,
      name: headerObj.name,
      description: headerObj.description,
      labels: headerObj.labels,
    });
    onClose();
  };

  return (
    <Dialog open={isOpen} onClose={onClose} fullWidth maxWidth="md">
      <DialogTitle>{initial ? "Edit Prompt" : "Create Prompt"}</DialogTitle>

      {/* Render either simple or doc form */}
      {isDocMode ? (
        <>
          <DialogContent>
            <Stack spacing={3} mt={1}>
              <TextField
                label="Header (YAML)"
                fullWidth
                multiline
                minRows={10}
                value={headerText}
                onChange={(e) => setHeaderText(e.target.value)}
                error={!!headerError}
                helperText={headerError || "Edit prompt metadata (version, name, labels, schema, etc.)"}
              />
              <TextField
                label="Body"
                fullWidth
                multiline
                minRows={14}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                helperText="Tip: use {placeholders} to define inputs."
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose} variant="outlined">
              Cancel
            </Button>
            <Button onClick={onSubmitDoc} variant="contained">
              Save
            </Button>
          </DialogActions>
        </>
      ) : (
        <form onSubmit={handleSubmit(onSubmitSimple)}>
          <DialogContent>
            <Stack spacing={3} mt={1}>
              <TextField
                label="Prompt Name"
                fullWidth
                {...register("name")}
                error={!!errors.name}
                helperText={errors.name?.message}
              />
              <TextField
                label="Description (optional)"
                fullWidth
                {...register("description")}
                error={!!errors.description}
                helperText={errors.description?.message}
              />
              <TextField
                label="Prompt Body"
                fullWidth
                multiline
                minRows={14}
                {...register("body")}
                error={!!errors.body}
                helperText={errors.body?.message || "Tip: use {placeholders} to define inputs."}
              />
            </Stack>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose} variant="outlined">
              Cancel
            </Button>
            <Button type="submit" variant="contained" disabled={isSubmitting}>
              Save
            </Button>
          </DialogActions>
        </form>
      )}
    </Dialog>
  );
};
