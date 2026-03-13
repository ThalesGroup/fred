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
import Editor, { OnMount } from "@monaco-editor/react";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import RestoreIcon from "@mui/icons-material/Restore";
import { Box, Chip, Divider, IconButton, Stack, Typography, useTheme } from "@mui/material";
import * as monaco from "monaco-editor";
import { useMemo, useRef } from "react";
import { SimpleTooltip } from "../../shared/ui/tooltips/Tooltips";

type Props = {
  label: string;
  value: string;
  defaultValue?: string;
  onChange: (next: string) => void;
  tokens?: string[]; // e.g. ["{objective}", "{step_number}", "{step}", "{options}"]
  required?: boolean;
};

export function PromptEditor({ label, value, defaultValue = "", onChange, tokens = [], required }: Props) {
  const theme = useTheme();

  // keep a ref to monaco editor instance (optional, when Monaco is present)
  const editorRef = useRef<monaco.editor.IStandaloneCodeEditor | null>(null);
  const onMount: OnMount = (editor) => {
    editorRef.current = editor;
  };

  const hasChanged = useMemo(() => (value ?? "") !== (defaultValue ?? ""), [value, defaultValue]);
  // insert token either at cursor (Monaco) or append at end
  const insertToken = (tok: string) => {
    const ed = editorRef.current;
    if (ed) {
      const sel = ed.getSelection();
      const model = ed.getModel();
      if (model && sel) {
        ed.executeEdits("insert-token", [{ range: sel, text: tok, forceMoveMarkers: true }]);
        ed.focus();
        return;
      }
    }
    // fallback: append with spacing
    const next = (value || "") + (value?.endsWith(" ") ? "" : " ") + tok + " ";
    onChange(next);
  };

  const copyToClipboard = async () => {
    try {
      await navigator.clipboard.writeText(value || "");
    } catch {}
  };
  const resetToDefault = () => onChange(defaultValue || "");

  return (
    <Box sx={{ border: `1px solid ${theme.palette.divider}`, borderRadius: 1.5, overflow: "hidden" }}>
      {/* Header */}
      <Box sx={{ px: 1.25, py: 0.75, display: "flex", alignItems: "center", gap: 1, bgcolor: "action.hover" }}>
        <Typography variant="subtitle2">
          {label}
          {required && <Typography component="span">{" *"}</Typography>}
        </Typography>
        {hasChanged && (
          <Chip
            size="small"
            color="warning"
            variant="outlined"
            label="modified"
            sx={{ ml: 0.5, height: 18, fontSize: 11 }}
          />
        )}
        <Box sx={{ ml: "auto", display: "flex", alignItems: "center", gap: 0.5 }}>
          <SimpleTooltip title="Reset to default">
            <span>
              <IconButton size="small" onClick={resetToDefault} disabled={!hasChanged}>
                <RestoreIcon fontSize="small" />
              </IconButton>
            </span>
          </SimpleTooltip>
          <SimpleTooltip title="Copy prompt">
            <IconButton size="small" onClick={copyToClipboard}>
              <ContentCopyIcon fontSize="small" />
            </IconButton>
          </SimpleTooltip>
        </Box>
      </Box>

      {/* Compact token toolbar (chips) */}
      {tokens.length > 0 && (
        <>
          <Box sx={{ px: 1.25, py: 0.5 }}>
            <Stack direction="row" alignItems="center" gap={0.75} flexWrap="wrap">
              <Typography variant="caption" color="text.secondary">
                Insert
              </Typography>
              {tokens.map((t) => (
                <Chip
                  key={t}
                  label={t}
                  size="small"
                  color="primary"
                  variant="outlined"
                  onClick={() => insertToken(t)}
                  sx={{
                    height: 22,
                    fontSize: 11,
                    borderRadius: 1,
                    cursor: "pointer",
                    "& .MuiChip-label": { px: 0.75 },
                  }}
                />
              ))}
            </Stack>
          </Box>
          <Divider />
        </>
      )}

      {/* Editor */}
      <Box sx={{ height: 360 }}>
        <Editor
          onMount={onMount}
          height="100%"
          language="markdown"
          defaultValue={value}
          theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
          onChange={(v) => onChange(v ?? "")}
          options={{
            wordWrap: "on",
            minimap: { enabled: false },
            fontSize: 13,
            lineNumbers: "on",
            renderWhitespace: "selection",
            scrollBeyondLastLine: false,
          }}
        />
      </Box>
    </Box>
  );
}
