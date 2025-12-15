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
  Box,
  Chip,
  Dialog,
  DialogContent,
  DialogTitle,
  Divider,
  Grid,
  Stack,
  Typography,
} from "@mui/material";
import { useTranslation } from "react-i18next";

type A2aSkill = {
  id?: string;
  name?: string;
  description?: string;
  tags?: string[];
  examples?: string[];
  inputModes?: string[];
  outputModes?: string[];
};

type A2aCard = {
  name?: string;
  description?: string;
  url?: string;
  preferredTransport?: string;
  capabilities?: { streaming?: boolean; pushNotifications?: boolean; stateTransitionHistory?: boolean };
  defaultInputModes?: string[];
  defaultOutputModes?: string[];
  skills?: A2aSkill[];
  protocolVersion?: string;
  version?: string;
};

interface Props {
  open: boolean;
  onClose: () => void;
  card?: A2aCard | null;
}

export const A2aCardDialog = ({ open, onClose, card }: Props) => {
  const { t } = useTranslation();
  if (!card) return null;

  const cap = card.capabilities || {};
  const skills = card.skills || [];

  return (
    <Dialog open={open} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>{t("agentHub.a2aCardTitle")}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={2}>
          <Box>
            <Typography variant="h6">{card.name}</Typography>
            <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
              {card.description}
            </Typography>
            <Stack direction="row" spacing={1} sx={{ mt: 1, flexWrap: "wrap" }} divider={<Divider orientation="vertical" flexItem />}>
              {card.url && (
                <Typography variant="caption" color="text.secondary">
                  URL: {card.url}
                </Typography>
              )}
              {card.preferredTransport && (
                <Typography variant="caption" color="text.secondary">
                  Transport: {card.preferredTransport}
                </Typography>
              )}
              {(card.version || card.protocolVersion) && (
                <Typography variant="caption" color="text.secondary">
                  Version: {card.version || card.protocolVersion}
                </Typography>
              )}
            </Stack>
          </Box>

          <Box>
            <Typography variant="subtitle2" gutterBottom>
              {t("agentHub.a2aCapabilities")}
            </Typography>
            <Stack direction="row" spacing={1} flexWrap="wrap">
              <Chip label={t("agentHub.a2aStreaming")} color={cap.streaming ? "success" : "default"} />
              <Chip
                label={t("agentHub.a2aPush")}
                color={cap.pushNotifications ? "success" : "default"}
              />
              <Chip
                label={t("agentHub.a2aHistory")}
                color={cap.stateTransitionHistory ? "success" : "default"}
              />
            </Stack>
          </Box>

          {skills.length > 0 && (
            <Box>
              <Typography variant="subtitle2" gutterBottom>
                {t("agentHub.a2aSkills")}
              </Typography>
              <Grid container spacing={1.5}>
                {skills.map((s, idx) => (
                  <Grid item xs={12} sm={6} key={`${s.id || s.name || "skill"}-${idx}`}>
                    <Stack spacing={0.5} sx={{ p: 1, border: (th) => `1px solid ${th.palette.divider}`, borderRadius: 1 }}>
                      <Typography variant="body2" fontWeight={600}>
                        {s.name || s.id}
                      </Typography>
                      {s.description && (
                        <Typography variant="caption" color="text.secondary">
                          {s.description}
                        </Typography>
                      )}
                      <Stack direction="row" spacing={0.5} flexWrap="wrap">
                        {(s.tags || []).map((tag) => (
                          <Chip key={tag} size="small" label={tag} />
                        ))}
                      </Stack>
                      {s.examples && s.examples.length > 0 && (
                        <Typography variant="caption" color="text.secondary">
                          {t("agentHub.a2aExamples")}: {s.examples.join(" · ")}
                        </Typography>
                      )}
                    </Stack>
                  </Grid>
                ))}
              </Grid>
            </Box>
          )}
        </Stack>
      </DialogContent>
    </Dialog>
  );
};
