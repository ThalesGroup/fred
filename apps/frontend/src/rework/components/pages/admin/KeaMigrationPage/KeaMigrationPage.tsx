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

// KEA CUTOVER 2026 — temporary, standalone admin page. Not linked from any nav
// menu on purpose (Sébastien reaches it by direct URL, /admin/kea-migration,
// same as kea's own migration page) — deliberately not surfaced next to the
// permanent MigrationPage so it never gets mistaken for the general-purpose
// export/import tool it replaces only for this one cutover.
//
// ⚠️ Delete this whole directory, its route in common/router.tsx, and
// runKeaDryRun.ts a few weeks after the S3NS cutover completes — see
// kea_reconciliation.py's docstring (backend) for the full removal list.

import { useState } from "react";
import { useDispatch } from "react-redux";
import { normalizeApiError } from "@core/errors/normalizeApiError.ts";
import Button from "@shared/atoms/Button/Button.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import { ConfirmationDialog } from "@shared/molecules/ConfirmationDialog/ConfirmationDialog";
import PageHeader from "@shared/molecules/PageHeader/PageHeader.tsx";
import { personalTeamId } from "@shared/utils/teamId";
import { launchPlatformImport } from "../../../../features/migration/launchPlatformImport";
import { runKeaDryRun } from "../../../../features/migration/runKeaDryRun";
import { taskRegistered } from "../../../../features/tasks/taskSlice";
import type { KeaDryRunResponse } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import {
  useCorpusRepairVectorMetadataMutation,
  useCorpusRevectorizeMutation,
} from "../../../../../slices/knowledgeFlow/knowledgeFlowOpenApi";
import { useResetPlatformRebacMutation } from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { KeyCloakService } from "../../../../../security/KeycloakService";
import styles from "./KeaMigrationPage.module.css";

// RTK Query's `.unwrap()` throws a `FetchBaseQueryError`/`SerializedError` --
// a plain, non-Error object (`{status, data}` or `{name, message}`) -- never a
// real `Error` instance. `e instanceof Error ? e.message : String(e)` was
// silently rendering the literal text "[object Object]" for every API error
// on this page instead of the backend's actual detail message.
function describeError(e: unknown): string {
  const detail = normalizeApiError(e).detail;
  if (detail) return detail;
  return e instanceof Error ? e.message : "Erreur inconnue.";
}

function FileField({
  label,
  file,
  onChange,
  required,
}: {
  label: string;
  file: File | null;
  onChange: (f: File | null) => void;
  required?: boolean;
}) {
  return (
    <label className={styles.fileField}>
      <span>
        {label}
        {required ? " *" : " (optionnel)"}
      </span>
      <input
        type="file"
        accept={label.toLowerCase().includes("realm") ? ".json" : ".zip"}
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
      {file && <span className={styles.fileName}>{file.name}</span>}
    </label>
  );
}

function UserList({ title, items }: { title: string; items: KeaDryRunResponse["users_matched"] }) {
  if (items.length === 0) return null;
  return (
    <details className={styles.userList} open={title.includes("PENDING") || title.includes("RELINKED")}>
      <summary>
        {title} ({items.length})
      </summary>
      <ul>
        {items.map((u) => (
          <li key={u.kea_sub}>
            <code>{u.kea_username}</code>
            {u.swift_sub && u.swift_sub !== u.kea_sub && (
              <span className={styles.mismatch}>
                {" "}
                kea={u.kea_sub.slice(0, 8)}… → swift={u.swift_sub.slice(0, 8)}…
              </span>
            )}
          </li>
        ))}
      </ul>
    </details>
  );
}

export default function KeaMigrationPage() {
  const dispatch = useDispatch();
  const [file, setFile] = useState<File | null>(null);
  const [realmFile, setRealmFile] = useState<File | null>(null);
  const [isDryRunning, setIsDryRunning] = useState(false);
  const [isApplying, setIsApplying] = useState(false);
  const [report, setReport] = useState<KeaDryRunResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [applyResult, setApplyResult] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);
  const [sourceTag, setSourceTag] = useState("");
  const [repairVectorMetadata, { isLoading: isRepairing }] = useCorpusRepairVectorMetadataMutation();
  const [revectorizeCorpus, { isLoading: isRevectorizing }] = useCorpusRevectorizeMutation();
  const [revectorizeResult, setRevectorizeResult] = useState<string | null>(null);
  const [resetPlatformRebac, { isLoading: isTearingDown }] = useResetPlatformRebacMutation();
  const [showTeardownConfirm, setShowTeardownConfirm] = useState(false);
  const [showRebuildConfirm, setShowRebuildConfirm] = useState(false);
  const isBusy3 = isRepairing || isRevectorizing;

  const canRun = file !== null && !isDryRunning && !isApplying;

  // Full JSON, not a formatted summary — offline processing (jq/python/diff
  // against a previous run) needs every field (kea_sub/swift_sub pairs, not
  // just the truncated display text), not a human-readable digest.
  const handleCopyReport = async () => {
    if (!report) return;
    await navigator.clipboard.writeText(JSON.stringify(report, null, 2));
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1500);
  };

  const handleDryRun = async () => {
    if (!file) return;
    setIsDryRunning(true);
    setError(null);
    setApplyResult(null);
    try {
      const result = await runKeaDryRun(file, realmFile ?? undefined);
      setReport(result);
    } catch (e) {
      setError(describeError(e));
      setReport(null);
    } finally {
      setIsDryRunning(false);
    }
  };

  const handleApply = async () => {
    if (!file) return;
    setIsApplying(true);
    setError(null);
    try {
      const { taskId, target } = await launchPlatformImport(file, "Kea cutover import", realmFile ?? undefined);
      dispatch(
        taskRegistered({
          taskId,
          kind: "migration",
          target,
        }),
      );
      setApplyResult(`Import lancé — task ${taskId}. Suivre la progression sur /admin/migration.`);
    } catch (e) {
      setError(describeError(e));
    } finally {
      setIsApplying(false);
    }
  };

  // 3a — dedicated metadata-only repair action (#2234): a small bulk Postgres
  // reconciliation, structurally incapable of deleting vectors, reading content, or
  // calling the embedder — never routes through /corpus/revectorize. See
  // `RepairVectorMetadataWorkflow`'s module docstring on the backend.
  const handleRepair = async () => {
    if (!sourceTag.trim()) return;
    setError(null);
    setRevectorizeResult(null);
    const userId = KeyCloakService.GetUserId();
    if (!userId) {
      setError("Impossible de déterminer l'utilisateur connecté.");
      return;
    }
    try {
      const { task_id } = await repairVectorMetadata({
        repairVectorMetadataRequestV1: {
          source_tag: sourceTag,
          team_id: personalTeamId(userId),
        },
      }).unwrap();
      dispatch(
        taskRegistered({
          taskId: task_id,
          kind: "ingestion",
          target: {
            type: "corpus-repair-vector-metadata",
            id: task_id,
            label: `Repair vector metadata · ${sourceTag}`,
          },
        }),
      );
      setRevectorizeResult(`Lancé — task ${task_id}. Suivre le rapport détaillé sur /admin/tasks.`);
      setSourceTag("");
    } catch (e) {
      setError(describeError(e));
    }
  };

  // 3b — the real re-vectorization pipeline (MIGR-07), unchanged by the #2234
  // 3a split other than dropping the now-removed metadata_only option.
  const handleRebuild = async () => {
    if (!sourceTag.trim()) return;
    setError(null);
    setRevectorizeResult(null);
    const userId = KeyCloakService.GetUserId();
    if (!userId) {
      setError("Impossible de déterminer l'utilisateur connecté.");
      return;
    }
    try {
      const { task_id } = await revectorizeCorpus({
        revectorizeCorpusRequestV1: {
          scope: { source_tag: sourceTag },
          // Fixé au réglage sûr validé pendant la répétition de bascule Kea :
          // incremental + no force ne touche que les documents sans aucun chunk
          // vectoriel existant (voir mark_document_vectorized / MIGR-07.04) — jamais
          // un ré-embedding silencieux de tout le corpus. Volontairement pas exposé.
          options: { mode: "incremental", force: false },
          team_id: personalTeamId(userId),
        },
      }).unwrap();
      dispatch(
        taskRegistered({
          taskId: task_id,
          kind: "ingestion",
          target: { type: "corpus-revectorize", id: task_id, label: `Rebuild missing embeddings · ${sourceTag}` },
        }),
      );
      setRevectorizeResult(`Lancé — task ${task_id}. Suivre la progression sur /admin/tasks.`);
      setSourceTag("");
    } catch (e) {
      setError(describeError(e));
    }
  };

  const handleTeardownConfirmed = async () => {
    setShowTeardownConfirm(false);
    setError(null);
    try {
      const { task_id } = await resetPlatformRebac().unwrap();
      dispatch(
        taskRegistered({
          taskId: task_id,
          kind: "migration",
          target: { type: "platform", id: task_id, label: "Teardown plateforme" },
        }),
      );
    } catch (e) {
      setError(describeError(e));
    }
  };

  const handleRebuildConfirmed = () => {
    setShowRebuildConfirm(false);
    void handleRebuild();
  };

  return (
    <div className={styles.page}>
      <PageHeader title="Kea → Swift — réconciliation (temporaire, cutover 2026)" />
      <p className={styles.intro}>
        Étape 1 : « Analyser » ne touche à rien (ni Keycloak, ni OpenFGA, ni Postgres) — relance-le aussi souvent que
        nécessaire pendant que tu vérifies une hypothèse. Étape 2 : « Lancer l&apos;import réel » appelle l&apos;import
        existant (<code>/admin/migration</code>), inchangé, qui applique maintenant les mêmes corrections.
      </p>

      <div className={styles.uploadRow}>
        <FileField label="Snapshot kea (.zip)" file={file} onChange={setFile} required />
        <FileField label="Realm Keycloak (.json, optionnel)" file={realmFile} onChange={setRealmFile} />
      </div>

      <div className={styles.actions}>
        <Button color="primary" variant="outlined" size="medium" onClick={handleDryRun} disabled={!canRun}>
          {isDryRunning ? "Analyse en cours…" : "Analyser (dry-run)"}
        </Button>
        <Button color="primary" variant="filled" size="medium" onClick={handleApply} disabled={!canRun}>
          {isApplying ? "Lancement…" : "Lancer l'import réel"}
        </Button>
      </div>

      {error && <div className={styles.error}>{error}</div>}
      {applyResult && <div className={styles.success}>{applyResult}</div>}

      {report && (
        <div className={styles.report}>
          <div className={styles.reportHead}>
            <span className={styles.reportTitle}>Rapport</span>
            <Button
              color="secondary"
              variant="outlined"
              size="small"
              icon={{ category: "outlined", type: "content_copy", filled: false }}
              onClick={handleCopyReport}
            >
              {copied ? "Copié !" : "Copier (JSON)"}
            </Button>
          </div>
          {report.source_platform === "swift" ? (
            <p>Snapshot swift-native — la réconciliation kea ne s&apos;applique pas.</p>
          ) : (
            <>
              <div className={styles.statGrid}>
                <div className={styles.stat}>
                  <div className={styles.statValue}>{report.agents_mapped}</div>
                  <div className={styles.statLabel}>agents mappés</div>
                </div>
                <div className={styles.stat}>
                  <div className={styles.statValue}>{report.agents_ignored}</div>
                  <div className={styles.statLabel}>agents ignorés (samples kea)</div>
                </div>
                <div className={`${styles.stat} ${report.agents_gap > 0 ? styles.statWarn : ""}`}>
                  <div className={styles.statValue}>{report.agents_gap}</div>
                  <div className={styles.statLabel}>agents GAP (pas de template)</div>
                </div>
                <div className={styles.stat}>
                  <div className={styles.statValue}>{report.teams_total}</div>
                  <div className={styles.statLabel}>équipes</div>
                </div>
                <div className={`${styles.stat} ${report.users_pending.length > 0 ? styles.statWarn : ""}`}>
                  <div className={styles.statValue}>{report.users_pending.length}</div>
                  <div className={styles.statLabel}>users en attente (1re connexion)</div>
                </div>
                <div className={`${styles.stat} ${report.teams_admin_less.length > 0 ? styles.statDanger : ""}`}>
                  <div className={styles.statValue}>{report.teams_admin_less.length}</div>
                  <div className={styles.statLabel}>équipes SANS admin</div>
                </div>
              </div>

              {report.agents_gap_templates.length > 0 && (
                <p className={styles.warnLine}>
                  Templates sans équivalent swift : {report.agents_gap_templates.join(", ")}
                </p>
              )}
              {report.teams_orphan_dropped.length > 0 && (
                <p className={styles.warnLine}>
                  Équipes orphelines abandonnées : {report.teams_orphan_dropped.join(", ")}
                </p>
              )}
              {report.teams_admin_less.length > 0 && (
                <p className={styles.dangerLine}>
                  ⚠ Équipes sans aucun team_admin après import : {report.teams_admin_less.join(", ")}
                </p>
              )}

              <UserList title="Users MATCHED (sub préservé)" items={report.users_matched} />
              <UserList title="Users RELINKED (sub différent, utilisé tel quel)" items={report.users_relinked} />
              <UserList title="Users PENDING (pas encore connectés sur S3NS)" items={report.users_pending} />

              <p className={styles.summaryHint}>
                {report.team_member_grants_ready} appartenance(s) d&apos;équipe prête(s) à écrire,{" "}
                {report.team_member_grants_pending} en attente · {report.platform_role_grants_ready} rôle(s) plateforme
                prêt(s)
              </p>
            </>
          )}
        </div>
      )}

      <div className={styles.report}>
        <span className={styles.reportTitle}>Étape 3 : réparer le statut des documents</span>
        <p className={styles.intro}>
          Deux actions séparées, à ne jamais confondre. Le tag à saisir est celui utilisé côté Kea au moment de
          l&apos;ingestion des documents (le défaut applicatif pour un upload manuel est <code>fred</code>).
        </p>
        <div className={styles.uploadRow}>
          <TextInput
            label="Source tag"
            value={sourceTag}
            onChange={(e) => setSourceTag(e.target.value)}
            placeholder="ex. fred"
            disabled={isBusy3}
          />
        </div>

        <p className={styles.intro}>
          <strong>3a — Réparer uniquement.</strong> Pour tout document où <em>au moins un</em> chunk vectoriel
          (OpenSearch) et <em>au moins un</em> objet de contenu (S3) ont été retrouvés — signal de présence minimale,
          pas une vérification de complétude totale (aucun nombre attendu fiable de chunks/objets n&apos;existe pour les
          documents restaurés depuis Kea) : corrige seulement le statut &laquo;&nbsp;en attente&nbsp;&raquo; en base. Un
          document réellement sans vecteur ou sans contenu n&apos;est jamais touché — juste compté dans le rapport de la
          tâche. Cette action ne peut structurellement jamais déclencher de reconstruction, de suppression de vecteurs,
          ou d&apos;appel au modèle d&apos;embeddings, quel que soit le tag saisi.
        </p>
        <div className={styles.actions}>
          <Button
            color="primary"
            variant="filled"
            size="medium"
            onClick={() => void handleRepair()}
            disabled={!sourceTag.trim() || isBusy3}
          >
            {isRepairing ? "Lancement…" : "3a — Réparer uniquement (jamais de reconstruction)"}
          </Button>
        </div>

        <p className={styles.intro}>
          <strong>3b — Reconstruire les documents manquants.</strong> À utiliser séparément, seulement pour les
          documents que l&apos;étape 3a a signalés comme réellement sans vecteur — reconstruction réelle (coût de
          calcul, plus long).
        </p>
        <div className={styles.actions}>
          <Button
            color="secondary"
            variant="outlined"
            size="medium"
            onClick={() => setShowRebuildConfirm(true)}
            disabled={!sourceTag.trim() || isBusy3}
          >
            {isRevectorizing ? "Lancement…" : "3b — Reconstruire les documents manquants"}
          </Button>
        </div>
        {revectorizeResult && <div className={styles.success}>{revectorizeResult}</div>}
      </div>

      <div className={styles.report}>
        <span className={styles.reportTitle}>Teardown (tests uniquement)</span>
        <p className={`${styles.intro} ${styles.dangerLine}`}>
          Supprime équipes, agents, prompts, tags et documents (Postgres) ainsi que tous les tuples OpenFGA —
          l&apos;admin root et ton propre compte sont préservés. Les comptes Keycloak, OpenSearch et S3 ne sont jamais
          touchés. À utiliser uniquement pour repartir sur une base propre entre deux répétitions d&apos;import.
        </p>
        <div className={styles.actions}>
          <Button
            color="error"
            variant="outlined"
            size="medium"
            onClick={() => setShowTeardownConfirm(true)}
            disabled={isTearingDown}
          >
            {isTearingDown ? "Teardown en cours…" : "Teardown"}
          </Button>
        </div>
      </div>

      <ConfirmationDialog
        open={showRebuildConfirm}
        title="Reconstruire les documents manquants ?"
        message={`Va réellement reconstruire (extraction + embeddings) tout document sans aucun vecteur sous le tag "${sourceTag}". Plus long et plus coûteux que 3a — à utiliser seulement pour les documents que 3a a signalés comme réellement manquants.`}
        confirmLabel="Reconstruire"
        cancelLabel="Annuler"
        criticalAction
        onConfirm={handleRebuildConfirmed}
        onCancel={() => setShowRebuildConfirm(false)}
      />

      <ConfirmationDialog
        open={showTeardownConfirm}
        title="Teardown — supprimer équipes, agents et OpenFGA ?"
        message="Supprime définitivement les agents, tags, documents, équipes et prompts (Postgres), ainsi que tous les tuples OpenFGA. Les comptes Keycloak, OpenSearch et S3 ne sont pas affectés. Action irréversible."
        confirmLabel="Teardown"
        cancelLabel="Annuler"
        criticalAction
        onConfirm={handleTeardownConfirmed}
        onCancel={() => setShowTeardownConfirm(false)}
      />
    </div>
  );
}
