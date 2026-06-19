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
import { taskRegistered, taskEventReceived, taskEvicted, selectActiveTasks } from "../rework/features/tasks/taskSlice";
import { FolderRow } from "../rework/components/shared/molecules/FolderRow/FolderRow";
import { DocRow } from "../rework/components/shared/molecules/DocRow/DocRow";
import type { DocStatus } from "../rework/components/shared/atoms/DocStatusBadge/DocStatusBadge";
import styles from "./LibraryTreePlayground.module.css";

/**
 * Dev-only playground (route `dev/library`) for the Resources page core components:
 * the collapsible folder/sub-folder tree with one row per file. 100% mock — no
 * backend round-trip. The `processing` state is driven by REAL tasks dispatched
 * into the task slice (same technique as TaskPlayground), proving the reuse.
 */

interface MockDoc {
  id: string;
  name: string;
  fileType: string;
  status: DocStatus;
}

interface MockFolder {
  id: string;
  name: string;
  docCount: number;
  docs: MockDoc[];
}

const PDF_ID = "demo-doc-ecb-pdf";
const PDF_TASK = "demo-task-ecb-pdf";
const CSV_ID = "demo-doc-donnees-csv";

const STEPS = ["Extraction du texte", "Découpage en chunks", "Vectorisation des chunks", "Indexation"];

const TREE: MockFolder[] = [
  {
    id: "cir",
    name: "CIR",
    docCount: 5,
    docs: [
      { id: "demo-doc-cir-docx", name: "CIR_TSN_2024_BIDGPT.docx", fileType: "docx", status: "ready" },
      { id: PDF_ID, name: "ecb.wp3105~8786f3ac1c.en.pdf", fileType: "pdf", status: "ready" },
      { id: CSV_ID, name: "donnees_2024.csv", fileType: "csv", status: "raw" },
      { id: "demo-doc-cir-notes", name: "notes-internes.md", fileType: "md", status: "raw" },
      { id: "demo-doc-cir-budget", name: "budget-2024.xlsx", fileType: "xlsx", status: "ready" },
    ],
  },
  {
    id: "innovation",
    name: "Innovation",
    docCount: 12,
    docs: [
      { id: "demo-doc-inno-deck", name: "vision-2030.pptx", fileType: "pptx", status: "ready" },
      { id: "demo-doc-inno-report", name: "veille-techno.pdf", fileType: "pdf", status: "ready" },
    ],
  },
];

export default function LibraryTreePlayground() {
  const dispatch = useDispatch();
  const activeTasks = useSelector(selectActiveTasks);

  const [expanded, setExpanded] = React.useState<Record<string, boolean>>({ cir: true, innovation: false });
  const [selected, setSelected] = React.useState<string | null>(CSV_ID);
  // Documents whose intrinsic status changed during the demo (raw -> ready after "Traiter").
  const [overrides, setOverrides] = React.useState<Record<string, DocStatus>>({});
  const procIntervals = React.useRef<Record<string, ReturnType<typeof setInterval>>>({});

  // A continuously-running task on the PDF row, so the progress ring is visibly alive.
  React.useEffect(() => {
    dispatch(
      taskRegistered({
        taskId: PDF_TASK,
        kind: "ingestion",
        target: { type: "document", id: PDF_ID, label: "ecb.wp3105~8786f3ac1c.en.pdf" },
      }),
    );
    let prog = 0.2;
    let seq = 0;
    const iv = setInterval(() => {
      prog = prog > 0.92 ? 0.15 : prog + 0.04;
      seq += 1;
      dispatch(
        taskEventReceived({
          kind: "ingestion",
          task_id: PDF_TASK,
          state: "running",
          seq,
          timestamp: new Date().toISOString(),
          progress: prog,
          step: STEPS[Math.min(STEPS.length - 1, Math.floor(prog * STEPS.length))],
          error: null,
          detail: null,
        }),
      );
    }, 280);

    const running = procIntervals.current;
    return () => {
      clearInterval(iv);
      Object.values(running).forEach(clearInterval);
      dispatch(taskEvicted(PDF_TASK));
    };
  }, [dispatch]);

  const baseStatus = (doc: MockDoc): DocStatus => overrides[doc.id] ?? doc.status;

  // Aggregate a folder's state from its docs + any active task targeting them.
  const aggregateFor = (folder: MockFolder) => {
    const stateById = new Map(activeTasks.map((task) => [task.target?.id, task.state] as const));
    let processing = 0;
    let failed = 0;
    for (const doc of folder.docs) {
      const taskState = stateById.get(doc.id);
      const status = taskState ? (taskState === "failed" ? "failed" : "processing") : baseStatus(doc);
      if (status === "processing") processing += 1;
      else if (status === "failed") failed += 1;
    }
    return { processing, failed };
  };

  const handleProcess = (doc: MockDoc) => {
    const taskId = `demo-task-${doc.id}`;
    dispatch(taskRegistered({ taskId, kind: "ingestion", target: { type: "document", id: doc.id, label: doc.name } }));
    let prog = 0;
    let seq = 0;
    procIntervals.current[doc.id] = setInterval(() => {
      prog += 0.1;
      seq += 1;
      if (prog >= 1) {
        clearInterval(procIntervals.current[doc.id]);
        delete procIntervals.current[doc.id];
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
        dispatch(taskEvicted(taskId));
        setOverrides((prev) => ({ ...prev, [doc.id]: "ready" }));
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
          step: STEPS[Math.min(STEPS.length - 1, Math.floor(prog * STEPS.length))],
          error: null,
          detail: null,
        }),
      );
    }, 220);
  };

  const reset = () => {
    Object.values(procIntervals.current).forEach(clearInterval);
    procIntervals.current = {};
    activeTasks.filter((task) => task.taskId !== PDF_TASK).forEach((task) => dispatch(taskEvicted(task.taskId)));
    setOverrides({});
    setSelected(CSV_ID);
  };

  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1 className={styles.title}>Ressources — arbre dossiers / fichiers</h1>
        <p className={styles.caption}>
          Playground de dev (mock, sans backend). Un objet = une ligne = un état. Survolez une ligne pour révéler les
          actions ; cliquez « Traiter » sur un fichier brut pour le voir passer en traitement puis « Prêt ».
        </p>
        <button type="button" className={styles.resetButton} onClick={reset}>
          Réinitialiser la démo
        </button>
      </header>

      <div className={styles.card}>
        {TREE.map((folder) => (
          <div key={folder.id}>
            <FolderRow
              id={folder.id}
              name={folder.name}
              docCount={folder.docCount}
              expanded={!!expanded[folder.id]}
              onToggle={() => setExpanded((prev) => ({ ...prev, [folder.id]: !prev[folder.id] }))}
              aggregate={aggregateFor(folder)}
            />
            {expanded[folder.id] && (
              <div className={styles.children} id={`folder-${folder.id}`}>
                {folder.docs.map((doc) => (
                  <DocRow
                    key={doc.id}
                    id={doc.id}
                    name={doc.name}
                    fileType={doc.fileType}
                    status={baseStatus(doc)}
                    selected={selected === doc.id}
                    onSelect={() => setSelected(doc.id)}
                    onPreview={() => undefined}
                    onDownload={() => undefined}
                    moreActions={[
                      { id: "delete", label: "Supprimer", onSelect: () => undefined },
                      { id: "searchable", label: "Activer/désactiver la recherche", onSelect: () => undefined },
                    ]}
                    onProcess={() => handleProcess(doc)}
                  />
                ))}
              </div>
            )}
          </div>
        ))}
      </div>

      <p className={styles.hint}>
        Dossier ouvert avec état agrégé (« N en traitement »). Dossier replié avec son verdict (« à jour »). La ligne
        brute (survolée/sélectionnée) propose directement « Traiter ».
      </p>
    </div>
  );
}
