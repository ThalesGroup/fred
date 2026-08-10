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
import { useDispatch, useSelector } from "react-redux";
import { taskRegistered, taskEventReceived, taskEvicted, selectVisibleTasks } from "../rework/features/tasks/taskSlice";
import { TASK_KINDS } from "../rework/features/tasks/taskKinds";
import { TaskIndicator } from "../rework/components/shared/molecules/TaskIndicator/TaskIndicator";
import { TaskCard } from "../rework/components/shared/molecules/TaskCard/TaskCard";
import { TaskStateBadge } from "../rework/components/shared/atoms/TaskStateBadge/TaskStateBadge";
import { TaskProgressBar } from "../rework/components/shared/atoms/TaskProgressBar/TaskProgressBar";
import Select from "../rework/components/shared/molecules/Select/Select";
import Button from "../rework/components/shared/atoms/Button/Button";
import Chip from "../rework/components/shared/atoms/Chip/Chip";
import type { TaskState } from "../rework/features/tasks/taskTypes";
import styles from "./TaskPlayground.module.css";

const KINDS = Object.keys(TASK_KINDS);
const STATES: TaskState[] = ["pending", "running", "cancelling", "succeeded", "failed", "cancelled"];

const KIND_OPTIONS = KINDS.map((k) => ({ value: k, label: k, key: k }));
const STATE_OPTIONS = STATES.map((s) => ({ value: s, label: s, key: s }));

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
    <div className={styles.page}>
      <h1 className={styles.title}>Task atoms — playground</h1>

      {/* ── Controls ─────────────────────────────────────────────────── */}
      <div className={styles.controlsPanel}>
        <Select options={KIND_OPTIONS} value={kind} onChange={setKind} label="Kind" size="small" />
        <Select options={STATE_OPTIONS} value={targetState} onChange={setTargetState} label="State" size="small" />

        {targetState === "running" ? (
          <div className={styles.progressRow}>
            <Button
              variant={indeterminate ? "filled" : "outlined"}
              color="primary"
              size="small"
              onClick={() => setIndeterminate((v) => !v)}
            >
              indét.
            </Button>
            <input
              type="range"
              className={styles.rangeInput}
              min={0}
              max={1}
              step={0.01}
              value={progress}
              disabled={indeterminate}
              onChange={(e) => setProgress(Number(e.target.value))}
              aria-label="Progress"
            />
            <span className={styles.progressValue} style={{ opacity: indeterminate ? 0.4 : 1 }}>
              {indeterminate ? "null" : `${Math.round(progress * 100)}%`}
            </span>
          </div>
        ) : (
          <div />
        )}

        <div className={styles.actionsRow}>
          <Button variant="outlined" color="primary" size="small" onClick={inject}>
            Injecter état sélectionné
          </Button>
          <Button variant="filled" color="primary" size="small" onClick={animate} disabled={animating}>
            Animer (0 → 100% → succès)
          </Button>
          <Button variant="outlined" color="secondary" size="small" onClick={injectAll}>
            Tous les états d'un coup
          </Button>
          <div className={styles.actionsSpacer} />
          <Button variant="text" color="error" size="small" onClick={clearAll}>
            Tout effacer
          </Button>
        </div>
      </div>

      {tasks.length === 0 && (
        <p className={styles.emptyState}>Aucune tâche — cliquez sur "Injecter" ou "Animer" ci-dessus.</p>
      )}

      {tasks.length > 0 && (
        <>
          {/* ── TaskIndicator ─────────────────────────────────────────── */}
          <Section title="TaskIndicator" subtitle="sm + md — cliquer pour ouvrir le popover">
            <div className={styles.indicatorGroup}>
              {tasks.map((t) => (
                <div key={t.taskId} className={styles.indicatorItem}>
                  <span className={styles.indicatorMeta}>
                    {t.state}
                    {t.progress !== null ? ` · ${Math.round(t.progress * 100)}%` : ""}
                  </span>
                  <div className={styles.indicatorRow}>
                    <TaskIndicator taskId={t.taskId} size="sm" />
                    <TaskIndicator taskId={t.taskId} size="md" />
                  </div>
                </div>
              ))}
            </div>
          </Section>

          <hr className={styles.divider} />

          {/* ── TaskStateBadge + TaskProgressBar ──────────────────────── */}
          <Section title="TaskStateBadge + TaskProgressBar">
            <div className={styles.stateGrid}>
              {tasks.map((t) => (
                <div key={t.taskId} className={styles.stateRow}>
                  <div className={styles.stateBadgeCell}>
                    <TaskStateBadge state={t.state} size="sm" />
                  </div>
                  <div className={styles.stateProgressCell}>
                    <TaskProgressBar state={t.state} progress={t.progress} />
                  </div>
                  <span className={styles.statePercentCell}>
                    {t.progress !== null ? `${Math.round(t.progress * 100)}%` : "—"}
                  </span>
                  <Chip label={t.state} />
                </div>
              ))}
            </div>
          </Section>

          <hr className={styles.divider} />

          {/* ── TaskCard ──────────────────────────────────────────────── */}
          <Section title="TaskCard">
            <div className={styles.cardGrid}>
              {tasks.map((t) => (
                <TaskCard key={t.taskId} task={t} />
              ))}
            </div>
          </Section>
        </>
      )}
    </div>
  );
}

function Section({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className={styles.section}>
      <div>
        <h2 className={styles.sectionTitle}>{title}</h2>
        {subtitle && <span className={styles.sectionSubtitle}>{subtitle}</span>}
      </div>
      {children}
    </div>
  );
}
