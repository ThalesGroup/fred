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
import { Box, MenuItem, Stack, TextField, Typography } from "@mui/material";
import { FieldSpec } from "../../slices/agentic/agenticOpenApi";
import { PromptEditor } from "./PromptEditor";

type Props = {
  fields: FieldSpec[];
  onChange: (index: number, next: any) => void;
};

export function TuningForm({ fields, onChange }: Props) {
  // optional grouping by ui.group
  const groups = groupBy(fields, (f) => f.ui?.group || "General");

  return (
    <Stack spacing={2}>
      {Object.entries(groups).map(([groupName, groupFields]) => (
        <Box key={groupName} sx={{ mt: 0.5 }}>
          <Typography variant="subtitle2" sx={{ mb: 1 }}>
            {groupName}
          </Typography>
          <Stack spacing={1.5}>
            {groupFields.map((f) => {
              const idx = fields.indexOf(f);
              const label = f.title || f.key;
              const val = f.default as any;

              if (f.type === "prompt") {
                // Suggest default routing tokens if key matches
                const tokens = f.key.includes("routing.prompts.choose_expert")
                  ? ["{objective}", "{step_number}", "{step}", "{options}"]
                  : [];

                return (
                  <PromptEditor
                    key={f.key}
                    label={label}
                    value={val ?? ""}
                    defaultValue={f.default as string}
                    onChange={(next) => onChange(idx, next)}
                    tokens={tokens}
                  />
                );
              }

              if (f.type === "boolean") {
                return (
                  <TextField
                    key={f.key}
                    label={label}
                    value={val ? "true" : "false"}
                    onChange={(e) => onChange(idx, e.target.value === "true")}
                    select
                    fullWidth
                    size="small"
                  >
                    <MenuItem value="true">True</MenuItem>
                    <MenuItem value="false">False</MenuItem>
                  </TextField>
                );
              }

              if (f.type === "select" && Array.isArray(f.enum)) {
                return (
                  <TextField
                    key={f.key}
                    select
                    fullWidth
                    size="small"
                    label={label}
                    value={val ?? ""}
                    onChange={(e) => onChange(idx, e.target.value)}
                  >
                    {f.enum!.map((opt) => (
                      <MenuItem key={opt} value={opt}>
                        {opt}
                      </MenuItem>
                    ))}
                  </TextField>
                );
              }

              // default text/number/etc
              return (
                <TextField
                  key={f.key}
                  fullWidth
                  size="small"
                  label={label}
                  value={val ?? ""}
                  onChange={(e) => onChange(idx, e.target.value)}
                  multiline={!!f.ui?.multiline}
                  minRows={f.ui?.multiline ? Math.min(f.ui?.max_lines ?? 6, 10) : undefined}
                  placeholder={f.ui?.placeholder || ""}
                />
              );
            })}
          </Stack>
        </Box>
      ))}
    </Stack>
  );
}

function groupBy<T>(arr: T[], key: (t: T) => string) {
  return arr.reduce<Record<string, T[]>>((acc, v) => {
    const k = key(v);
    (acc[k] ||= []).push(v);
    return acc;
  }, {});
}
