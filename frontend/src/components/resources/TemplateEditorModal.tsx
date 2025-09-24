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

import { Button, Dialog, DialogActions, DialogContent, DialogTitle, MenuItem, Stack, TextField } from "@mui/material";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import { zodResolver } from "@hookform/resolvers/zod";
import yaml from "js-yaml";
import { buildTemplateYaml, splitFrontMatter, buildFrontMatter, looksLikeYamlDoc } from "./resourceYamlUtils";

/** ---- Minimal form schema ---- */
const templateSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  format: z.enum(["markdown", "html", "text", "json"]), // keep in sync with options below
  body: z.string().min(1, "Template body is required"),
});
type TemplateFormData = z.infer<typeof templateSchema>;

type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // final YAML with '---'
};

interface TemplateEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: ResourceCreateLike) => void;
  /** initial.body for plain text; initial.yaml for full doc */
  initial?: Partial<TemplateFormData & { labels?: string[]; yaml?: string }>;
  getSuggestion?: () => Promise<string>;
}

export const TemplateEditorModal = ({ isOpen, onClose, onSave, initial }: TemplateEditorModalProps) => {
  // decide incoming doc
  const incomingDoc = useMemo(() => (initial as any)?.yaml ?? (initial as any)?.body ?? "", [initial]);
  const isDocMode = useMemo(() => looksLikeYamlDoc(incomingDoc), [incomingDoc]);

  // ---- simple mode form ----
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<TemplateFormData>({
    resolver: zodResolver(templateSchema),
    defaultValues: { name: "", description: "", format: "markdown", body: "" },
  });

  // ---- doc mode state ----
  const [headerText, setHeaderText] = useState<string>("");
  const [bodyText, setBodyText] = useState<string>("");
  const [headerError, setHeaderError] = useState<string | null>(null);

  useEffect(() => {
    if (!isOpen) return;

    if (isDocMode) {
      const { header, body } = splitFrontMatter(incomingDoc);
      const headerYaml = Object.keys(header).length ? yaml.dump(header).trim() : "";
      setHeaderText(headerYaml);
      setBodyText(body);
    } else {
      reset({
        name: initial?.name ?? "",
        description: initial?.description ?? "",
        format: (initial?.format as any) ?? "markdown",
        body: incomingDoc || "",
      });
    }
  }, [isOpen, isDocMode, incomingDoc, initial?.name, initial?.description, initial?.format, reset]);

  // ---- submit handlers ----
  const onSubmitSimple = (data: TemplateFormData) => {
    const body = (data.body || "").trim();
    const content = looksLikeYamlDoc(body)
      ? body
      : buildTemplateYaml({
          name: data.name,
          description: data.description || undefined,
          labels: undefined,
          format: data.format,
          body,
        });

    onSave({ name: data.name, description: data.description || undefined, content });
    onClose();
  };

  const onSubmitDoc = () => {
    let headerObj: Record<string, any>;
    try {
      headerObj = (yaml.load(headerText || "") as Record<string, any>) ?? {};
      setHeaderError(null);
    } catch (e: any) {
      setHeaderError(e?.message || "Invalid YAML");
      return;
    }
    if (!headerObj.kind) headerObj.kind = "template"; // UI safety

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
      <DialogTitle>{initial ? "Edit Template" : "Create Template"}</DialogTitle>

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
                helperText={headerError || "Edit template metadata (version, name, labels, format, schema, etc.)"}
              />
              <TextField
                label="Body"
                fullWidth
                multiline
                minRows={14}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
                helperText="Use {placeholders} to define inputs."
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
                label="Template Name"
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
                label="Format"
                select
                fullWidth
                {...register("format")}
                error={!!errors.format}
                helperText={errors.format?.message}
              >
                <MenuItem value="markdown">Markdown</MenuItem>
                <MenuItem value="html">HTML</MenuItem>
                <MenuItem value="text">Text</MenuItem>
                <MenuItem value="json">JSON</MenuItem>
                {/* If you want DOCX, add it to the Zod enum too. */}
              </TextField>
              <TextField
                label="Template Body"
                fullWidth
                multiline
                minRows={14}
                {...register("body")}
                error={!!errors.body}
                helperText={errors.body?.message || "Use {placeholders} to define inputs."}
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
