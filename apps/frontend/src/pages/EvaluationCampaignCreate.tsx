import {
  Alert,
  Box,
  Card,
  CardContent,
  CircularProgress,
  Container,
  FormControl,
  InputLabel,
  MenuItem,
  Select,
  Stack,
  Step,
  StepLabel,
  Stepper,
  TextField,
  Typography,
  IconButton,
} from "@mui/material";
import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap";
import { useToast } from "../rework/components/shared/molecules/Toast/ToastProvider";
import Button from "../rework/components/shared/atoms/Button/Button";
import { useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery } from "../slices/controlPlane/controlPlaneOpenApi";
import {
  useCreateCampaignEvaluationV1CampaignsPostMutation,
  type EvaluationCaseInput,
} from "../slices/evaluation/evaluationOpenApi";

const STEPS = ["Cible", "Dataset", "Politique d'évaluation"];

type TargetKind = "managed_instance" | "runtime_agent";

interface CaseRow {
  id: string;
  input: string;
  expected_output: string;
  external_id: string;
}

function newRow(): CaseRow {
  return { id: crypto.randomUUID(), input: "", expected_output: "", external_id: "" };
}

// ── Target selector card ──────────────────────────────────────────────────────

function TargetCard({ selected, label, description, onClick }: {
  selected: boolean; label: string; description: string; onClick: () => void;
}) {
  return (
    <Card
      onClick={onClick}
      sx={{
        flex: 1, cursor: "pointer",
        border: selected ? "2px solid #7c3aed" : "2px solid rgba(255,255,255,0.1)",
        bgcolor: selected ? "rgba(124,58,237,0.12)" : "rgba(255,255,255,0.04)",
        transition: "all 0.2s ease",
        "&:hover": { borderColor: selected ? "#7c3aed" : "rgba(255,255,255,0.25)" },
      }}
    >
      <CardContent>
        <Typography variant="subtitle1" fontWeight={700} gutterBottom>{label}</Typography>
        <Typography variant="body2" color="text.secondary">{description}</Typography>
      </CardContent>
    </Card>
  );
}

// ── Drag-drop zone ────────────────────────────────────────────────────────────

function DragDropZone({ onParsed, mode }: { onParsed: (rows: CaseRow[]) => void; mode: "json" | "csv" }) {
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const parse = (text: string, name: string) => {
    setError(null);
    try {
      if (name.endsWith(".json")) {
        const data = JSON.parse(text);
        const arr = Array.isArray(data) ? data : data.cases ?? [];
        if (arr.length > 200) { setError("Maximum 200 cas autorisés."); return; }
        onParsed(arr.map((item: any) => ({
          id: crypto.randomUUID(),
          input: String(item.input ?? ""),
          expected_output: String(item.expected_output ?? ""),
          external_id: String(item.external_id ?? ""),
        })));
      } else {
        const lines = text.split("\n").filter(Boolean).slice(1);
        if (lines.length > 200) { setError("Maximum 200 cas autorisés."); return; }
        onParsed(lines.map((line) => {
          const parts = line.split(",");
          return { id: crypto.randomUUID(), input: parts[0] ?? "", expected_output: parts[1] ?? "", external_id: parts[2] ?? "" };
        }));
      }
    } catch {
      setError("Fichier invalide. Vérifiez le format JSON ou CSV.");
    }
  };

  const handleFile = (file: File) => {
    const reader = new FileReader();
    reader.onload = (e) => parse(e.target?.result as string, file.name);
    reader.readAsText(file);
  };

  return (
    <Box>
      <Box
        onDragOver={(e) => { e.preventDefault(); setDragging(true); }}
        onDragLeave={() => setDragging(false)}
        onDrop={(e) => { e.preventDefault(); setDragging(false); const f = e.dataTransfer.files[0]; if (f) handleFile(f); }}
        onClick={() => inputRef.current?.click()}
        sx={{
          border: `2px dashed ${dragging ? "#7c3aed" : "rgba(255,255,255,0.2)"}`,
          borderRadius: 2, p: 4, textAlign: "center", cursor: "pointer", transition: "all 0.2s",
          boxShadow: dragging ? "0 0 20px rgba(124,58,237,0.4)" : "none",
          bgcolor: dragging ? "rgba(124,58,237,0.08)" : "transparent",
          "&:hover": { borderColor: "#7c3aed", bgcolor: "rgba(124,58,237,0.05)" },
        }}
      >
        <Typography variant="body2" color="text.secondary">
          Glissez-déposez un fichier {mode.toUpperCase()}, ou cliquez pour parcourir
        </Typography>
        <Typography variant="caption" color="text.secondary">Max 200 cas · 65 KB par input</Typography>
        <input
          ref={inputRef} type="file" accept=".json,.csv" style={{ display: "none" }}
          onChange={(e) => { const f = e.target.files?.[0]; if (f) handleFile(f); }}
        />
      </Box>
      {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
    </Box>
  );
}

// ── Step slide wrapper ────────────────────────────────────────────────────────

function StepSlide({ active, children }: { active: boolean; children: React.ReactNode }) {
  return (
    <Box sx={{
      transition: "opacity 0.3s ease, transform 0.3s ease",
      opacity: active ? 1 : 0,
      transform: active ? "translateX(0)" : "translateX(40px)",
      pointerEvents: active ? "auto" : "none",
      position: active ? "relative" : "absolute",
    }}>
      {children}
    </Box>
  );
}

// ── Recap card ────────────────────────────────────────────────────────────────

function RecapCard({ name, targetKind, agentInstanceId, runtimeId, agentId, datasetName, datasetVersion, cases, judgeProfileId, maxConcurrency, caseTimeout }: {
  name: string; targetKind: TargetKind; agentInstanceId: string; runtimeId: string; agentId: string;
  datasetName: string; datasetVersion: string; cases: CaseRow[];
  judgeProfileId: string; maxConcurrency: number; caseTimeout: number;
}) {
  const rows = [
    { label: "Campagne", value: name },
    { label: "Type de cible", value: targetKind === "managed_instance" ? "Instance gérée" : "Agent runtime" },
    ...(targetKind === "managed_instance"
      ? [{ label: "Instance", value: agentInstanceId || "—" }]
      : [{ label: "Runtime", value: runtimeId || "—" }, { label: "Agent", value: agentId || "—" }]),
    { label: "Dataset", value: `${datasetName}${datasetVersion ? ` v${datasetVersion}` : ""}` },
    { label: "Cas", value: `${cases.length}` },
    { label: "Juge", value: judgeProfileId },
    { label: "Concurrence", value: `${maxConcurrency}` },
    { label: "Timeout", value: `${caseTimeout}s` },
    { label: "Profil scoring", value: "auto (détection automatique)" },
  ];
  return (
    <Card sx={{ bgcolor: "rgba(124,58,237,0.08)", border: "1px solid rgba(124,58,237,0.3)" }}>
      <CardContent>
        <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1.5, color: "#a78bfa" }}>
          Récapitulatif
        </Typography>
        <Stack spacing={0.75}>
          {rows.map((r) => (
            <Stack key={r.label} direction="row" justifyContent="space-between">
              <Typography variant="caption" color="text.secondary">{r.label}</Typography>
              <Typography variant="caption" fontWeight={600} sx={{ fontFamily: "monospace" }}>{r.value}</Typography>
            </Stack>
          ))}
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function EvaluationCampaignCreate() {
  const navigate = useNavigate();
  const { showSuccess, showError } = useToast();
  const { activeTeam, availableTeams } = useFrontendBootstrap();
  // The evaluation campaign must target the team that owns the agent. The admin
  // route is not team-scoped, so let the user pick the team explicitly instead of
  // defaulting to the personal space (whose agents the Control Plane can't resolve).
  const [teamId, setTeamId] = useState(() => localStorage.getItem("eval.teamId") ?? "");
  useEffect(() => {
    if (!teamId && activeTeam?.id) setTeamId(activeTeam.id);
  }, [activeTeam?.id, teamId]);
  useEffect(() => {
    if (teamId) localStorage.setItem("eval.teamId", teamId);
  }, [teamId]);

  const [step, setStep] = useState(0);
  const [name, setName] = useState("");
  const [targetKind, setTargetKind] = useState<TargetKind>("managed_instance");
  const [agentInstanceId, setAgentInstanceId] = useState("");
  const [runtimeId, setRuntimeId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [datasetName, setDatasetName] = useState("");
  const [datasetVersion, setDatasetVersion] = useState("");
  const [jsonCases, setJsonCases] = useState<CaseRow[]>([]);
  const [csvCases, setCsvCases] = useState<CaseRow[]>([]);
  const [cases, setCases] = useState<CaseRow[]>([newRow()]);
  const [judgeProfileId, setJudgeProfileId] = useState("mistral-small");
  const [maxConcurrency, setMaxConcurrency] = useState(3);
  const [caseTimeout, setCaseTimeout] = useState(120);

  const { data: instances, isLoading: instancesLoading } =
    useGetTeamAgentInstancesControlPlaneV1TeamsTeamIdAgentInstancesGetQuery({ teamId }, { skip: !teamId });

  const [createCampaign, { isLoading: isCreating }] = useCreateCampaignEvaluationV1CampaignsPostMutation();

  const canNext0 = name.trim() && (targetKind === "managed_instance" ? agentInstanceId : runtimeId && agentId);
  const allCases = [...cases, ...jsonCases, ...csvCases].filter((c) => c.input.trim());
  const canNext1 = datasetName.trim() && allCases.length > 0;

  const addRow = () => setCases((p) => [...p, newRow()]);
  const removeRow = (id: string) => setCases((p) => p.filter((r) => r.id !== id));
  const updateRow = (id: string, field: keyof CaseRow, value: string) =>
    setCases((p) => p.map((r) => (r.id === id ? { ...r, [field]: value } : r)));

  const handleSubmit = async () => {
    const caseInputs: EvaluationCaseInput[] = allCases.map((c) => ({
      input: c.input,
      expected_output: c.expected_output || null,
      external_id: c.external_id || null,
    }));
    const target =
      targetKind === "managed_instance"
        ? { kind: "managed_instance" as const, agent_instance_id: agentInstanceId }
        : { kind: "runtime_agent" as const, runtime_id: runtimeId, agent_id: agentId };
    try {
      const result = await createCampaign({
        createEvaluationCampaignRequest: {
          name, team_id: teamId, target,
          dataset: { name: datasetName, version: datasetVersion || null, cases: caseInputs },
          profile: "auto",
          judge_profile_id: judgeProfileId,
          execution: { max_concurrency: maxConcurrency, case_timeout_seconds: caseTimeout },
        },
      }).unwrap();
      showSuccess({ summary: "Campagne lancée — en file d'attente" });
      navigate(`/admin/evaluations/${result.campaign_id}`);
    } catch (e: any) {
      const msg = e?.data?.detail ?? e?.message ?? "Erreur lors de la création";
      showError({ summary: typeof msg === "string" ? msg : JSON.stringify(msg) });
    }
  };

  return (
    <Container maxWidth="md" sx={{ py: 3 }}>
      <TopBar title="Nouvelle campagne d'évaluation" description="Configurez la cible, le dataset et la politique de scoring">
        <Button color="secondary" variant="text" size="medium" onClick={() => navigate("/admin/evaluations")}>
          ← Retour
        </Button>
      </TopBar>

      <Stepper activeStep={step} sx={{ mb: 4 }}>
        {STEPS.map((label) => (
          <Step key={label}><StepLabel>{label}</StepLabel></Step>
        ))}
      </Stepper>

      <Box sx={{ position: "relative", overflow: "hidden" }}>

        {/* Step 0 — Cible */}
        <StepSlide active={step === 0}>
          <Stack spacing={3}>
            <TextField
              label="Nom de la campagne" value={name}
              onChange={(e) => setName(e.target.value)}
              fullWidth required placeholder="ex. Validation GitHub Assistant v2"
            />

            <FormControl fullWidth required>
              <InputLabel>Équipe</InputLabel>
              <Select
                value={teamId}
                label="Équipe"
                onChange={(e) => {
                  setTeamId(e.target.value);
                  setAgentInstanceId(""); // instances are team-scoped — reset on team change
                }}
              >
                {availableTeams.map((t) => (
                  <MenuItem key={t.id} value={t.id}>
                    {t.name}
                  </MenuItem>
                ))}
              </Select>
            </FormControl>

            <Box>
              <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>Type de cible</Typography>
              <Stack direction="row" spacing={2}>
                <TargetCard
                  selected={targetKind === "managed_instance"}
                  label="Instance gérée"
                  description="Agent déployé et géré par le Control Plane. Recommandé pour la production."
                  onClick={() => setTargetKind("managed_instance")}
                />
                <TargetCard
                  selected={targetKind === "runtime_agent"}
                  label="Agent runtime"
                  description="Appel direct par runtime_id + agent_id. Pour les environnements de dev."
                  onClick={() => setTargetKind("runtime_agent")}
                />
              </Stack>
            </Box>

            {targetKind === "managed_instance" ? (
              <FormControl fullWidth required>
                <InputLabel>Instance d'agent</InputLabel>
                <Select value={agentInstanceId} label="Instance d'agent" onChange={(e) => setAgentInstanceId(e.target.value)}>
                  {instancesLoading && <MenuItem disabled><CircularProgress size={16} sx={{ mr: 1 }} />Chargement…</MenuItem>}
                  {(instances ?? []).map((inst) => (
                    <MenuItem key={inst.agent_instance_id} value={inst.agent_instance_id}>
                      {inst.display_name}
                      <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 1, fontFamily: "monospace" }}>
                        ({inst.agent_instance_id.slice(0, 8)})
                      </Typography>
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
            ) : (
              <Stack spacing={2}>
                <TextField label="Runtime ID" value={runtimeId} onChange={(e) => setRuntimeId(e.target.value)} fullWidth required placeholder="ex. fred-agents" />
                <TextField label="Agent ID" value={agentId} onChange={(e) => setAgentId(e.target.value)} fullWidth required placeholder="ex. fred.github.assistant" />
              </Stack>
            )}

            <Box sx={{ p: 2, borderRadius: 1, bgcolor: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
              <Typography variant="caption" color="text.secondary">
                Les URLs de runtime ne sont jamais exposées au navigateur. Seuls des identifiants contrôlés sont acceptés.
              </Typography>
            </Box>
          </Stack>
        </StepSlide>

        {/* Step 1 — Dataset */}
        {step === 1 && (
          <StepSlide active={step === 1}>
            <Stack spacing={3}>
              <Stack direction="row" spacing={2}>
                <TextField label="Nom du dataset" value={datasetName} onChange={(e) => setDatasetName(e.target.value)} fullWidth required />
                <TextField label="Version (optionnel)" value={datasetVersion} onChange={(e) => setDatasetVersion(e.target.value)} sx={{ width: 160 }} />
              </Stack>

              {/* Saisie manuelle */}
              <Box>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Saisie manuelle
                </Typography>
                <Stack spacing={2}>
                  {cases.map((row, idx) => (
                    <Card key={row.id} sx={{ bgcolor: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
                      <CardContent>
                        <Stack direction="row" alignItems="flex-start" spacing={1}>
                          <Box sx={{ flex: 1 }}>
                            <Stack spacing={1.5}>
                              <Typography variant="caption" color="text.secondary">Cas #{idx + 1}</Typography>
                              <TextField label="Input *" value={row.input} onChange={(e) => updateRow(row.id, "input", e.target.value)} fullWidth multiline minRows={2} required />
                              <TextField label="Sortie attendue (optionnel)" value={row.expected_output} onChange={(e) => updateRow(row.id, "expected_output", e.target.value)} fullWidth multiline minRows={2} />
                            </Stack>
                          </Box>
                          <IconButton onClick={() => removeRow(row.id)} disabled={cases.length === 1} color="error" size="small">✕</IconButton>
                        </Stack>
                      </CardContent>
                    </Card>
                  ))}
                  <Box>
                    <Button color="secondary" variant="outlined" size="small" onClick={addRow}>
                      + Ajouter un cas
                    </Button>
                  </Box>
                </Stack>
              </Box>

              {/* Import JSON */}
              <Box>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Importer un fichier JSON
                </Typography>
                <DragDropZone mode="json" onParsed={setJsonCases} />
                {jsonCases.length > 0 && (
                  <Alert severity="success" sx={{ mt: 1 }}>{jsonCases.length} cas importés via JSON.</Alert>
                )}
              </Box>

              {/* Import CSV */}
              <Box>
                <Typography variant="subtitle2" color="text.secondary" sx={{ mb: 1.5 }}>
                  Importer un fichier CSV
                </Typography>
                <DragDropZone mode="csv" onParsed={setCsvCases} />
                {csvCases.length > 0 && (
                  <Alert severity="success" sx={{ mt: 1 }}>{csvCases.length} cas importés via CSV.</Alert>
                )}
              </Box>

              {allCases.length > 0 && (
                <Typography variant="caption" color="text.secondary">
                  Total : {allCases.length} cas à évaluer
                </Typography>
              )}
            </Stack>
          </StepSlide>
        )}

        {/* Step 2 — Politique */}
        {step === 2 && (
          <StepSlide active={step === 2}>
            <Stack spacing={3}>
              <TextField
                label="Modèle juge" value={judgeProfileId}
                onChange={(e) => setJudgeProfileId(e.target.value)}
                fullWidth helperText="Identifiant du modèle d'évaluation, ex. mistral-small"
              />
              <Stack direction="row" spacing={2}>
                <TextField label="Concurrence max" type="number" value={maxConcurrency} onChange={(e) => setMaxConcurrency(Number(e.target.value))} inputProps={{ min: 1, max: 20 }} sx={{ flex: 1 }} />
                <TextField label="Timeout par cas (s)" type="number" value={caseTimeout} onChange={(e) => setCaseTimeout(Number(e.target.value))} inputProps={{ min: 30, max: 600 }} sx={{ flex: 1 }} />
              </Stack>
              <RecapCard
                name={name} targetKind={targetKind} agentInstanceId={agentInstanceId}
                runtimeId={runtimeId} agentId={agentId} datasetName={datasetName}
                datasetVersion={datasetVersion} cases={cases} judgeProfileId={judgeProfileId}
                maxConcurrency={maxConcurrency} caseTimeout={caseTimeout}
              />
            </Stack>
          </StepSlide>
        )}
      </Box>

      {/* Navigation */}
      <Stack direction="row" justifyContent="space-between" sx={{ mt: 4 }}>
        <Button
          color="secondary" variant="text" size="medium"
          disabled={step === 0}
          onClick={() => setStep((s) => s - 1)}
        >
          Précédent
        </Button>
        {step < STEPS.length - 1 ? (
          <Button
            color="primary" variant="filled" size="medium"
            disabled={step === 0 ? !canNext0 : step === 1 ? !canNext1 : false}
            onClick={() => setStep((s) => s + 1)}
          >
            Suivant
          </Button>
        ) : (
          <Button
            color="primary" variant="filled" size="medium"
            onClick={handleSubmit}
            disabled={isCreating}
          >
            {isCreating ? <CircularProgress size={16} sx={{ mr: 1, color: "white" }} /> : null}
            Lancer la campagne
          </Button>
        )}
      </Stack>
    </Container>
  );
}
