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

import { Button, Box, Typography } from "@mui/material";
import AppsIcon from "@mui/icons-material/Apps";
import ChevronRightIcon from "@mui/icons-material/ChevronRight";

type SidePanelToggleProps = {
  isOpen: boolean;
  label: string; // "Assistants" or current agent's display name
  onToggle: () => void;
};

/**
 * Fred rationale:
 * - We avoid playful badges here; the toggle should feel like a control, not content.
 * - Chevron rotation conveys panel state without extra chrome.
 * - Neutral outline + surface colors read as "tooling" in our UI vocabulary.
 */
export function SidePanelToggle({ isOpen, label, onToggle }: SidePanelToggleProps) {
  return (
    <Button
      onClick={onToggle}
      variant="outlined"
      size="small"
      aria-label="Toggle assistants & conversations panel"
      aria-expanded={isOpen}
      startIcon={<AppsIcon fontSize="small" />}
      endIcon={
        <Box
          component={ChevronRightIcon}
          sx={{
            fontSize: 18,
            transform: isOpen ? "rotate(180deg)" : "rotate(0deg)",
            transition: (t) =>
              t.transitions.create("transform", {
                duration: t.transitions.duration.shorter,
              }),
          }}
        />
      }
      sx={(t) => ({
        // Pill look, neutral, unobtrusive
        borderRadius: 999,
        textTransform: "none",
        bgcolor: t.palette.background.paper,
        borderColor: t.palette.divider,
        boxShadow: t.palette.mode === "light" ? 1 : 3,
        px: 1.25,
        minHeight: 32,
        color: t.palette.text.primary,
        "&:hover": { bgcolor: t.palette.action.hover },
      })}
    >
      <Typography variant="body2" noWrap>
        {label}
      </Typography>
    </Button>
  );
}
