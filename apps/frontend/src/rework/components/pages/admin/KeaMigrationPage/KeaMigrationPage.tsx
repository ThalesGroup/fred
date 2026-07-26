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
import Button from "@shared/atoms/Button/Button.tsx";
import { launchPlatformImport } from "../../../../features/migration/launchPlatformImport";
import { runKeaDryRun } from "../../../../features/migration/runKeaDryRun";
import { taskRegistered } from "../../../../features/tasks/taskSlice";
import type { KeaDryRunResponse } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./KeaMigrationPage.module.css";

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
      setError(e instanceof Error ? e.message : String(e));
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
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIsApplying(false);
    }
  };

  return (
    <div className={styles.page}>
      <h1>Kea → Swift — réconciliation (temporaire, cutover 2026)</h1>
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
    </div>
  );
}
