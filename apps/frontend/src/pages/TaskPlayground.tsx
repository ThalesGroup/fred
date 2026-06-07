// Copyright Thales 2026
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

import React from "react";
import {
  Box,
  Button,
  Chip,
  Divider,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Slider,
  Stack,
  Typography,
} from "@mui/material";
import { useDispatch, useSelector } from "react-redux";
import { taskRegistered, taskEventReceived, taskEvicted, selectVisibleTasks } from "../rework/features/tasks/taskSlice";
import { TASK_KINDS } from "../rework/features/tasks/taskKinds";
import { TaskIndicator } from "../rework/components/shared/molecules/TaskIndicator/TaskIndicator";
import { TaskCard } from "../rework/components/shared/molecules/TaskCard/TaskCard";
import { TaskStateBadge } from "../rework/components/shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "../rework/components/shared/atoms/TaskProgressBar/TaskProgressBar";
import type { TaskState } from "../rework/features/tasks/taskTypes";
const KINDS = Object.keys(TASK_KINDS);
const STATES: TaskState[] = ["pending", "running", "cancelling", "succeeded", "failed", "cancelled"];

const DEMO_LABELS = [
  "rapport-annuel-2025.pdf",
  "presentation-q4.pptx",
  "roadmap-technique.docx",
  "donnees-clients.xlsx",
  "synthese-risques.pdf",
  "budget-previsionnel.xlsx",
];

const STEPS = ["Extraction du texte", "Découpage en chunks", "Vectorisation des chunks", "Indexation"];

let counter = 0;

function makeId() {
  counter++;
  return { taskId: `demo-${Date.now()}-${counter}`, docId: `doc-demo-${counter}` };
}

function labelFor(n: number) {
  return DEMO_LABELS[(n - 1) % DEMO_LABELS.length];
}

export default function TaskPlayground() {
  const dispatch = useDispatch();
  const tasks = useSelector(selectVisibleTasks);

  const [kind, setKind] = React.useState<string>("ingestion");
  const [targetState, setTargetState] = React.useState<TaskState>("running");
  const [progress, setProgress] = React.useState<number>(0.35);
  const [indeterminate, setIndeterminate] = React.useState(false);
  const animRef = React.useRef<ReturnType<typeof setInterval> | null>(null);
  const [animating, setAnimating] = React.useState(false);

  React.useEffect(() => {
    return () => {
      if (animRef.current) clearInterval(animRef.current);
    };
  }, []);

  function inject() {
    const { taskId, docId } = makeId();
    const label = labelFor(counter);

    dispatch(taskRegistered({ taskId, kind, target: { type: "document", id: docId, label } }));

    if (targetState === "pending") return;

    dispatch(
      taskEventReceived({
        kind: "ingestion",
        task_id: taskId,
        state: targetState,
        seq: 0,
        timestamp: new Date().toISOString(),
        progress:
          targetState === "running" ? (indeterminate ? null : progress) : targetState === "succeeded" ? 1 : null,
        step: targetState === "running" && !indeterminate ? STEPS[Math.floor(progress * STEPS.length)] : null,
        error: targetState === "failed" ? "Erreur lors de l'extraction du texte (demo)" : null,
        detail: null,
      }),
    );
  }

  function animate() {
    if (animating) return;
    const { taskId, docId } = makeId();
    const label = labelFor(counter);

    dispatch(taskRegistered({ taskId, kind, target: { type: "document", id: docId, label } }));
    setAnimating(true);

    let prog = 0;
    let seq = 0;

    animRef.current = setInterval(() => {
      prog = Math.min(1, prog + 0.025);
      seq++;
      const stepIdx = Math.min(STEPS.length - 1, Math.floor(prog * STEPS.length));

      if (prog >= 1) {
        clearInterval(animRef.current!);
        animRef.current = null;
        dispatch(
          taskEventReceived({
            kind: "ingestion",
            task_id: taskId,
            state: "succeeded",
            seq,
            timestamp: new Date().toISOString(),
            progress: 1,
            step: "Terminé",
            error: null,
            detail: null,
          }),
        );
        setAnimating(false);
        return;
      }

      dispatch(
        taskEventReceived({
          kind: "ingestion",
          task_id: taskId,
          state: "running",
          seq,
          timestamp: new Date().toISOString(),
          progress: prog,
          step: STEPS[stepIdx],
          error: null,
          detail: null,
        }),
      );
    }, 150);
  }

  function injectAll() {
    // One task per state (running at 60%)
    for (const st of STATES) {
      const { taskId, docId } = makeId();
      const label = labelFor(counter);
      dispatch(taskRegistered({ taskId, kind: "ingestion", target: { type: "document", id: docId, label } }));
      if (st !== "pending") {
        dispatch(
          taskEventReceived({
            kind: "ingestion",
            task_id: taskId,
            state: st,
            seq: 0,
            timestamp: new Date().toISOString(),
            progress: st === "running" ? 0.6 : st === "succeeded" ? 1 : null,
            step: st === "running" ? "Vectorisation des chunks" : null,
            error: st === "failed" ? "Erreur (demo)" : null,
            detail: null,
          }),
        );
      }
    }
    // Extra: running indéterminé (progress = null) — the shimmer bar case
    const { taskId, docId } = makeId();
    const label = labelFor(counter);
    dispatch(taskRegistered({ taskId, kind: "ingestion", target: { type: "document", id: docId, label } }));
    dispatch(
      taskEventReceived({
        kind: "ingestion",
        task_id: taskId,
        state: "running",
        seq: 0,
        timestamp: new Date().toISOString(),
        progress: null,
        step: "Initialisation…",
        error: null,
        detail: null,
      }),
    );
  }

  function clearAll() {
    if (animRef.current) {
      clearInterval(animRef.current);
      animRef.current = null;
      setAnimating(false);
    }
    tasks.forEach((t) => dispatch(taskEvicted(t.taskId)));
  }

  return (
    <Box p={3} display="grid" gap={3} maxWidth={900}>
      <Typography variant="h5" fontWeight={600}>
        Task atoms — playground
      </Typography>

      {/* ── Controls ─────────────────────────────────────────────────── */}
      <Box
        display="grid"
        gap={2}
        gridTemplateColumns="160px 160px 1fr"
        alignItems="center"
        sx={{ p: 2, borderRadius: 2, border: "1px solid", borderColor: "divider", bgcolor: "background.paper" }}
      >
        <FormControl size="small">
          <InputLabel>Kind</InputLabel>
          <Select label="Kind" value={kind} onChange={(e) => setKind(e.target.value)}>
            {KINDS.map((k) => (
              <MenuItem key={k} value={k}>
                {k}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        <FormControl size="small">
          <InputLabel>State</InputLabel>
          <Select label="State" value={targetState} onChange={(e) => setTargetState(e.target.value as TaskState)}>
            {STATES.map((s) => (
              <MenuItem key={s} value={s}>
                {s}
              </MenuItem>
            ))}
          </Select>
        </FormControl>

        {targetState === "running" ? (
          <Box display="flex" alignItems="center" gap={1.5}>
            <Button
              size="small"
              variant={indeterminate ? "contained" : "outlined"}
              onClick={() => setIndeterminate((v) => !v)}
              sx={{ flexShrink: 0, minWidth: 0, fontSize: 11 }}
            >
              indét.
            </Button>
            <Slider
              size="small"
              min={0}
              max={1}
              step={0.01}
              value={progress}
              disabled={indeterminate}
              onChange={(_, v) => setProgress(v as number)}
            />
            <Typography variant="body2" sx={{ minWidth: 36, textAlign: "right", opacity: indeterminate ? 0.4 : 1 }}>
              {indeterminate ? "null" : `${Math.round(progress * 100)}%`}
            </Typography>
          </Box>
        ) : (
          <Box />
        )}

        <Stack direction="row" gap={1} sx={{ gridColumn: "1 / -1" }}>
          <Button variant="outlined" size="small" onClick={inject}>
            Injecter état sélectionné
          </Button>
          <Button variant="contained" size="small" onClick={animate} disabled={animating}>
            Animer (0 → 100% → succès)
          </Button>
          <Button variant="outlined" size="small" color="secondary" onClick={injectAll}>
            Tous les états d'un coup
          </Button>
          <Box flex={1} />
          <Button variant="text" size="small" color="error" onClick={clearAll}>
            Tout effacer
          </Button>
        </Stack>
      </Box>

      {tasks.length === 0 && (
        <Typography variant="body2" color="text.secondary">
          Aucune tâche — cliquez sur "Injecter" ou "Animer" ci-dessus.
        </Typography>
      )}

      {tasks.length > 0 && (
        <>
          {/* ── TaskIndicator ─────────────────────────────────────────── */}
          <Section title="TaskIndicator" subtitle="sm + md — cliquer pour ouvrir le popover">
            <Box display="flex" flexWrap="wrap" gap={3} alignItems="flex-end">
              {tasks.map((t) => (
                <Box key={t.taskId} display="flex" flexDirection="column" gap={0.75} alignItems="flex-start">
                  <Typography variant="caption" color="text.secondary">
                    {t.state}
                    {t.progress !== null ? ` · ${Math.round(t.progress * 100)}%` : ""}
                  </Typography>
                  <Box display="flex" gap={1.5} alignItems="center">
                    <TaskIndicator taskId={t.taskId} size="sm" />
                    <TaskIndicator taskId={t.taskId} size="md" />
                  </Box>
                </Box>
              ))}
            </Box>
          </Section>

          <Divider />

          {/* ── TaskStateBadge + TaskProgressBar ──────────────────────── */}
          <Section title="TaskStateBadge + TaskProgressBar">
            <Box display="grid" gap={1.5}>
              {tasks.map((t) => (
                <Box key={t.taskId} display="flex" gap={2} alignItems="center">
                  <Box sx={{ width: 220 }}>
                    <TaskStateBadge state={t.state} size="sm" />
                  </Box>
                  <Box flex={1}>
                    <TaskProgressBar state={t.state} progress={t.progress} />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ minWidth: 36, textAlign: "right" }}>
                    {t.progress !== null ? `${Math.round(t.progress * 100)}%` : "—"}
                  </Typography>
                  <Chip label={t.state} size="small" sx={{ minWidth: 90 }} />
                </Box>
              ))}
            </Box>
          </Section>

          <Divider />

          {/* ── TaskCard ──────────────────────────────────────────────── */}
          <Section title="TaskCard">
            <Box display="flex" flexWrap="wrap" gap={2}>
              {tasks.map((t) => (
                <TaskCard key={t.taskId} task={t} />
              ))}
            </Box>
          </Section>
        </>
      )}
    </Box>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <Box display="grid" gap={1.5}>
      <Box>
        <Typography variant="subtitle1" fontWeight={600}>
          {title}
        </Typography>
        {subtitle && (
          <Typography variant="caption" color="text.secondary">
            {subtitle}
          </Typography>
        )}
      </Box>
      {children}
    </Box>
  );
}
