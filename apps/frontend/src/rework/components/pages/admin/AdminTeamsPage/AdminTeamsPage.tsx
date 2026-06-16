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

import { useState } from "react";
import Button from "@shared/atoms/Button/Button.tsx";
import { DeleteIconButton } from "@shared/atoms/DeleteIconButton/DeleteIconButton.tsx";
import Switch from "@shared/atoms/Switch/Switch.tsx";
import TextInput from "@shared/atoms/TextInput/TextInput.tsx";
import DataTable, { DataTableColumn } from "@shared/molecules/DataTable/DataTable.tsx";
import PageEmptyState from "@shared/molecules/PageEmptyState/PageEmptyState.tsx";
import { useConfirmationDialog } from "../../../../../components/ConfirmationDialogProvider";
import { useToast } from "../../../../../components/ToastProvider";
import {
  useCreateTeamMutation,
  useDeleteTeamMutation,
  useListTeamsQuery,
} from "../../../../../slices/controlPlane/controlPlaneApiEnhancements";
import { Team } from "../../../../../slices/controlPlane/controlPlaneOpenApi";
import styles from "./AdminTeamsPage.module.css";

function extractApiErrorDetail(error: unknown): string | undefined {
  if (typeof error !== "object" || error === null) return undefined;
  const detail = (error as { data?: { detail?: string } }).data?.detail;
  return typeof detail === "string" ? detail : undefined;
}

export default function AdminTeamsPage() {
  const { showSuccess, showError } = useToast();
  const { showConfirmationDialog } = useConfirmationDialog();

  const { data: teams = [], isLoading } = useListTeamsQuery();
  const [createTeam, { isLoading: isCreating }] = useCreateTeamMutation();
  const [deleteTeam] = useDeleteTeamMutation();

  const [showForm, setShowForm] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [isPrivate, setIsPrivate] = useState(true);

  const collaborativeTeams = teams.filter((t) => !t.id.startsWith("personal-"));

  const closeForm = () => {
    setShowForm(false);
    setName("");
    setDescription("");
    setIsPrivate(true);
  };

  const handleCreate = async () => {
    try {
      await createTeam({
        createTeamRequest: { name, description: description || null, is_private: isPrivate },
      }).unwrap();
      showSuccess({ summary: "Équipe créée" });
      closeForm();
    } catch (error: unknown) {
      showError({
        summary: "Échec de la création de l'équipe",
        detail: extractApiErrorDetail(error) ?? "Une erreur inattendue est survenue.",
      });
    }
  };

  const handleDelete = (team: Team) => {
    showConfirmationDialog({
      criticalAction: true,
      title: "Supprimer cette équipe ?",
      message: `Supprimer l'équipe "${team.name}" ? Cette action est irréversible.`,
      onConfirm: async () => {
        try {
          await deleteTeam({ teamId: team.id }).unwrap();
          showSuccess({ summary: "Équipe supprimée" });
        } catch (error: unknown) {
          showError({
            summary: "Échec de la suppression",
            detail: extractApiErrorDetail(error) ?? "Une erreur inattendue est survenue.",
          });
        }
      },
    });
  };

  const columns: DataTableColumn<Team>[] = [
    {
      label: "Nom",
      cellRenderer: (team) => <div>{team.name}</div>,
    },
    {
      label: "Identifiant",
      size: "16rem",
      cellRenderer: (team) => (
        <div className={styles.id} title={team.id}>
          {team.id}
        </div>
      ),
    },
    {
      label: "Description",
      cellRenderer: (team) => <div>{team.description || <span className={styles.hint}>—</span>}</div>,
    },
    {
      label: "Visibilité",
      size: "8rem",
      cellRenderer: (team) => (
        <span className={team.is_private ? styles.badgePrivate : styles.badgePublic}>
          {team.is_private ? "Privée" : "Publique"}
        </span>
      ),
    },
    {
      label: "",
      size: "4rem",
      cellRenderer: (team) => <DeleteIconButton size="medium" onClick={() => handleDelete(team)} />,
    },
  ];

  return (
    <div className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>Équipes</h1>
        {!showForm && (
          <Button
            color="primary"
            variant="filled"
            size="medium"
            icon={{ category: "outlined", type: "add" }}
            onClick={() => setShowForm(true)}
          >
            Nouvelle équipe
          </Button>
        )}
      </div>

      {showForm && (
        <div className={styles.form}>
          <TextInput
            label="Nom"
            placeholder="Nom de l'équipe"
            value={name}
            onChange={(e) => setName(e.target.value)}
            required
            maxLength={255}
          />
          <TextInput
            label="Description"
            placeholder="Description (optionnel)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            maxLength={180}
          />
          <label className={styles.toggleRow}>
            <Switch checked={!isPrivate} onChange={(e) => setIsPrivate(!e.target.checked)} />
            <span>Équipe publique</span>
          </label>
          <div className={styles.formActions}>
            <Button color="on-surface" variant="text" size="medium" onClick={closeForm}>
              Annuler
            </Button>
            <Button
              color="primary"
              variant="filled"
              size="medium"
              onClick={handleCreate}
              disabled={isCreating || !name.trim()}
            >
              {isCreating ? "Création…" : "Créer"}
            </Button>
          </div>
        </div>
      )}

      {isLoading ? (
        <div className={styles.loadingState}>Chargement…</div>
      ) : collaborativeTeams.length === 0 ? (
        <PageEmptyState
          icon="groups"
          message="Aucune équipe collaborative."
          action={showForm ? undefined : { label: "Créer une équipe", onClick: () => setShowForm(true) }}
        />
      ) : (
        <DataTable columns={columns} data={collaborativeTeams} />
      )}
    </div>
  );
}
