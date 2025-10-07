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
  Stack,
  TextField,
} from "@mui/material";
import yaml from "js-yaml";
import { useTranslation } from "react-i18next";
import { ResourceKind, useKindLabels } from "./resourceLabels";

import * as React from "react";
import { useEffect, useMemo, useState } from "react";
import { useForm } from "react-hook-form";
import { z } from "zod";
import {
  buildFrontMatter,
  buildProfileYaml,
  looksLikeYamlDoc,
  splitFrontMatter,
} from "./resourceYamlUtils";

const profileSchema = z.object({
  name: z.string().min(1, "Name is required"),
  description: z.string().optional(),
  body: z.string().min(1, "Profile body is required"),
});

type ProfileFormData = z.infer<typeof profileSchema>;

type ResourceCreateLike = {
  name?: string;
  description?: string;
  labels?: string[];
  content: string; // YAML with '---'
};

interface ProfileEditorModalProps {
  isOpen: boolean;
  onClose: () => void;
  onSave: (payload: { name?: string; description?: string; labels?: string[]; content: string }) => void;
  initial?: Partial<{ name: string; description?: string; body?: string; yaml?: string; labels?: string[] }>;
  getSuggestion?: () => Promise<string>;
  kind?: ResourceKind;
}

/** Modal supports two modes:
 * - simple mode (name/description/body)
 * - doc mode (header YAML + body) when initial content is a full YAML doc
 */
export const ProfileEditorModal: React.FC<ProfileEditorModalProps> = ({
  isOpen,
  onClose,
  onSave,
  initial,
  kind,
}) => {
  const incomingDoc = useMemo(() => (initial as any)?.yaml ?? (initial as any)?.body ?? "", [initial]);
  const isDocMode = useMemo(() => looksLikeYamlDoc(incomingDoc), [incomingDoc]);
  const { t } = useTranslation();
  const { one: typeOne } = useKindLabels(kind ?? "profile");

  // ----- Simple mode form (create) -----
  
  const {
    register,
    handleSubmit,
    reset,
    formState: { errors, isSubmitting },
  } = useForm<ProfileFormData>({
    resolver: zodResolver(profileSchema),
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
  const onSubmitSimple = (data: ProfileFormData) => {
    const body = (data.body || "").trim();
    const content = looksLikeYamlDoc(body)
      ? body
      : buildProfileYaml({
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
    if (!headerObj.kind) headerObj.kind = "profile";

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
      <DialogTitle>
        {initial
          ? t("resourceLibrary.editResource", { typeOne })
          : t("resourceLibrary.createResource", { typeOne })}
      </DialogTitle>
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
                helperText={headerError || "Edit profile metadata (version, name, labels, schema, etc.)"}
              />
              <TextField
                label="Body"
                fullWidth
                multiline
                minRows={14}
                value={bodyText}
                onChange={(e) => setBodyText(e.target.value)}
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
                label="Context Name"
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
                label="Context Body"
                fullWidth
                multiline
                minRows={14}
                {...register("body")}
                error={!!errors.body}
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