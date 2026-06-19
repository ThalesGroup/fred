import {
  Box,
  Card,
  CardContent,
  CircularProgress,
  Container,
  Drawer,
  Stack,
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableRow,
  Typography,
} from "@mui/material";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap";
import Button from "../rework/components/shared/atoms/Button/Button";
import { IndicatorDot } from "../rework/components/shared/atoms/IndicatorDot/IndicatorDot";
import ProgressBar from "../rework/components/shared/atoms/ProgressBar/ProgressBar";
import PageEmptyState from "../rework/components/shared/molecules/PageEmptyState/PageEmptyState";
import {
  useListCampaignsEvaluationV1CampaignsGetQuery,
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  type EvaluationCampaignResponse,
  type EvaluationCaseResponse,
} from "../slices/evaluation/evaluationOpenApi";

// ── Shimmer animation ─────────────────────────────────────────────────────────

const shimmerKeyframes = `
@keyframes shimmer {
  0% { background-position: -600px 0; }
  100% { background-position: 600px 0; }
}
`;
if (typeof document !== "undefined") {
  const style = document.createElement("style");
  style.textContent = shimmerKeyframes;
  document.head.appendChild(style);
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function verdictColor(v: string): string {
  if (v === "passed") return "#22c55e";
  if (v === "failed") return "#ef4444";
  if (v === "inconclusive") return "#f59e0b";
  return "#6b7280";
}

function stateColor(s: string): string {
  if (s === "running") return "#3b82f6";
  if (s === "completed" || s === "succeeded") return "#22c55e";
  if (s === "failed" || s === "cancelled") return "#ef4444";
  if (s === "pending") return "#f59e0b";
  return "#6b7280";
}

function targetLabel(t: EvaluationCampaignResponse["target"]): string {
  if (t.kind === "managed_instance") return `Instance · ${t.agent_instance_id.slice(0, 8)}`;
  return t.agent_id;
}

// ── Animated counter ──────────────────────────────────────────────────────────

function useAnimatedCount(target: number, duration = 800): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min((now - start) / duration, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      setCount(Math.round(ease * target));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return count;
}

// ── KPI Card ──────────────────────────────────────────────────────────────────

function KpiCard({ label, value, color, suffix = "" }: { label: string; value: number; color: string; suffix?: string }) {
  const animated = useAnimatedCount(value);
  return (
    <Card sx={{ flex: 1, borderTop: `3px solid ${color}`, bgcolor: "rgba(255,255,255,0.04)" }}>
      <CardContent>
        <Typography variant="h4" fontWeight={800} color={color}>
          {animated}{suffix}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
          {label}
        </Typography>
      </CardContent>
    </Card>
  );
}

// ── Pill ──────────────────────────────────────────────────────────────────────

function Pill({ label, color }: { label: string; color: string }) {
  return (
    <Box
      component="span"
      sx={{
        display: "inline-block", px: 1.2, py: 0.3, borderRadius: "999px",
        fontSize: 11, fontWeight: 700, letterSpacing: 0.5,
        color, border: `1px solid ${color}`, bgcolor: `${color}18`,
        textTransform: "uppercase",
      }}
    >
      {label}
    </Box>
  );
}

// ── Case drawer ───────────────────────────────────────────────────────────────

function CaseDrawer({ campaignId, open, onClose }: { campaignId: string | null; open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const { data, isLoading } = useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery(
    { campaignId: campaignId ?? "", limit: 200 },
    { skip: !campaignId || !open },
  );
  const cases = data?.cases ?? [];

  const handleCaseClick = (c: EvaluationCaseResponse) => {
    onClose();
    navigate(`/admin/evaluations/${campaignId}`, { state: { selectedCaseId: c.case_id } });
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      PaperProps={{ sx: { width: 560, bgcolor: "#12121e", p: 3, boxShadow: "-4px 0 24px rgba(0,0,0,0.5)" } }}
      SlideProps={{ timeout: 300 }}
    >
      <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 1 }}>
        <Typography variant="h6" fontWeight={700}>Cas de la campagne</Typography>
        <Button color="secondary" variant="outlined" size="small" onClick={onClose}>✕</Button>
      </Stack>
      <Typography variant="caption" color="text.secondary" sx={{ mb: 2, display: "block" }}>
        Cliquez sur un cas pour voir tous les détails
      </Typography>

      {isLoading && (
        <Box sx={{ textAlign: "center", py: 6 }}><CircularProgress size={32} /></Box>
      )}

      <Stack spacing={2} sx={{ overflowY: "auto" }}>
        {cases.map((c) => (
          <CaseCard key={c.case_id} c={c} onClick={() => handleCaseClick(c)} />
        ))}
        {!isLoading && cases.length === 0 && (
          <Typography color="text.secondary" textAlign="center" sx={{ py: 4 }}>Aucun cas disponible.</Typography>
        )}
      </Stack>
    </Drawer>
  );
}

function CaseCard({ c, onClick }: { c: EvaluationCaseResponse; onClick: () => void }) {
  return (
    <Card
      onClick={onClick}
      sx={{
        bgcolor: "rgba(255,255,255,0.05)",
        border: "1px solid rgba(255,255,255,0.08)",
        cursor: "pointer",
        transition: "border-color 0.15s, background 0.15s",
        "&:hover": {
          bgcolor: "rgba(255,255,255,0.08)",
          borderColor: "rgba(124,58,237,0.5)",
        },
      }}
    >
      <CardContent sx={{ pb: "12px !important" }}>
        <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1.5 }}>
          <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
            {c.external_id ?? c.case_id.slice(0, 12)}
          </Typography>
          <Stack direction="row" spacing={1} alignItems="center">
            <Pill label={c.verdict} color={verdictColor(c.verdict)} />
            {c.metrics.length > 0 && (
              <Typography variant="caption" color="text.secondary">
                {c.metrics.length} métrique{c.metrics.length > 1 ? "s" : ""}
              </Typography>
            )}
          </Stack>
        </Stack>

        <FieldBlock label="Input" value={c.input} />

        {c.execution_error && (
          <Box sx={{ mt: 1, p: 1.5, borderRadius: 1, bgcolor: "#ef444418", border: "1px solid #ef444440" }}>
            <Typography variant="caption" color="#ef4444" fontWeight={700}>Erreur d'exécution</Typography>
            <Typography variant="caption" color="#ef4444" sx={{ display: "block", mt: 0.5 }}>{c.execution_error}</Typography>
          </Box>
        )}

        {c.metrics.length > 0 && (
          <Stack spacing={1} sx={{ mt: 1.5 }}>
            {c.metrics.map((m, i) => (
              <Box key={i}>
                <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                  <Typography variant="caption" color="text.secondary">{m.name.replace("Metric", "")}</Typography>
                  <Typography variant="caption" fontWeight={700} color={verdictColor(m.verdict)}>
                    {m.score != null ? `${(m.score * 100).toFixed(0)}%` : m.verdict}
                  </Typography>
                </Stack>
                {m.score != null && (
                  <ProgressBar theme={m.verdict === "passed" ? "success" : "error"} current={Math.round(m.score * 100)} max={100} />
                )}
              </Box>
            ))}
          </Stack>
        )}

        <Typography variant="caption" color="rgba(124,58,237,0.7)" sx={{ display: "block", mt: 1.5, textAlign: "right" }}>
          Voir le détail complet →
        </Typography>
      </CardContent>
    </Card>
  );
}

function FieldBlock({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ mb: 1 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>{label}</Typography>
      <Box sx={{
        p: 1.5, borderRadius: 1, bgcolor: "rgba(255,255,255,0.05)",
        fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap",
        wordBreak: "break-word", maxHeight: 120, overflowY: "auto", color: "text.primary",
      }}>
        {value}
      </Box>
    </Box>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function EvaluationCampaigns() {
  const navigate = useNavigate();
  const { activeTeam } = useFrontendBootstrap();
  const teamId = activeTeam?.id ?? "";
  const [drawerCampaignId, setDrawerCampaignId] = useState<string | null>(null);

  const { data, isLoading, isError } = useListCampaignsEvaluationV1CampaignsGetQuery(
    { teamId },
    { skip: !teamId, pollingInterval: 10_000 },
  );

  const campaigns = data?.campaigns ?? [];
  const running = campaigns.filter((c) => c.operational_state === "running").length;
  const totalCases = campaigns.reduce((sum, c) => sum + c.completed_cases, 0);
  const criticalErrors = campaigns.reduce((sum, c) => sum + c.execution_error_cases, 0);
  const completedWithAverages = campaigns.filter((c) => c.metric_averages && Object.keys(c.metric_averages).length > 0);
  const globalScore = completedWithAverages.length
    ? Math.round(
        completedWithAverages.reduce((sum, c) => {
          const vals = Object.values(c.metric_averages!);
          return sum + vals.reduce((a, b) => a + b, 0) / vals.length;
        }, 0) / completedWithAverages.length * 100
      )
    : null;

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <TopBar title="Évaluations" description="Campagnes de validation d'agents">
        <Button
          color="primary"
          variant="filled"
          size="medium"
          onClick={() => navigate("/admin/evaluations/new")}
        >
          + Nouvelle campagne
        </Button>
      </TopBar>

      {/* KPI cards */}
      <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
        <KpiCard label="Campagnes actives" value={running} color="#3b82f6" />
        <KpiCard label="Score moyen global" value={globalScore ?? 0} color={globalScore === null ? "#6b7280" : globalScore >= 80 ? "#22c55e" : globalScore >= 50 ? "#f59e0b" : "#ef4444"} suffix="%" />
        <KpiCard label="Cas évalués" value={totalCases} color="#a78bfa" />
        <KpiCard label="Échecs critiques" value={criticalErrors} color="#ef4444" />
      </Stack>

      {/* Table */}
      <Card sx={{ bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
        <CardContent sx={{ p: 0 }}>
          {isLoading && (
            <Box sx={{ py: 8, textAlign: "center" }}><CircularProgress /></Box>
          )}
          {isError && (
            <Box sx={{ py: 4, textAlign: "center" }}>
              <Typography color="error">Erreur lors du chargement des campagnes.</Typography>
            </Box>
          )}
          {!isLoading && !isError && campaigns.length === 0 && (
            <Box sx={{ py: 4 }}>
              <PageEmptyState
                icon="check_circle"
                message="Aucune campagne d'évaluation"
                action={{ label: "Créer une campagne", onClick: () => navigate("/admin/evaluations/new") }}
              />
            </Box>
          )}
          {!isLoading && campaigns.length > 0 && (
            <Table>
              <TableHead>
                <TableRow sx={{ "& th": { color: "text.secondary", fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 } }}>
                  <TableCell>Nom / ID</TableCell>
                  <TableCell>Cible</TableCell>
                  <TableCell>État</TableCell>
                  <TableCell>Verdict</TableCell>
                  <TableCell>Progression</TableCell>
                  <TableCell>Scores</TableCell>
                  <TableCell>Latence moy.</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {campaigns.map((c) => {
                  const isRunning = c.operational_state === "running";
                  return (
                    <TableRow
                      key={c.campaign_id}
                      onClick={() => setDrawerCampaignId(c.campaign_id)}
                      sx={{
                        cursor: "pointer",
                        position: "relative",
                        "&:hover": { bgcolor: "rgba(255,255,255,0.04)" },
                        ...(isRunning && {
                          "&::after": {
                            content: '""',
                            position: "absolute",
                            inset: 0,
                            background: "linear-gradient(90deg, transparent 0%, rgba(255,255,255,0.06) 50%, transparent 100%)",
                            backgroundSize: "600px 100%",
                            animation: "shimmer 2s infinite linear",
                            pointerEvents: "none",
                          },
                        }),
                      }}
                    >
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          {isRunning && <IndicatorDot status="streaming" label="En cours" />}
                          <Box>
                            <Typography variant="body2" fontWeight={600}>{c.name}</Typography>
                            <Typography variant="caption" sx={{ fontFamily: "monospace", color: "text.secondary" }}>
                              {c.campaign_id.slice(0, 12)}
                            </Typography>
                          </Box>
                        </Stack>
                      </TableCell>
                      <TableCell>
                        <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12 }}>
                          {targetLabel(c.target)}
                        </Typography>
                      </TableCell>
                      <TableCell>
                        <Pill label={c.operational_state} color={stateColor(c.operational_state)} />
                      </TableCell>
                      <TableCell>
                        <Pill label={c.verdict} color={verdictColor(c.verdict)} />
                      </TableCell>
                      <TableCell sx={{ minWidth: 160 }}>
                        <Typography variant="caption" color="text.secondary">
                          {c.completed_cases} / {c.total_cases}
                        </Typography>
                        <Box sx={{ mt: 0.5 }}>
                          <ProgressBar
                            theme="secondary"
                            current={c.completed_cases}
                            max={c.total_cases || 1}
                          />
                        </Box>
                      </TableCell>
                      <TableCell sx={{ minWidth: 160 }}>
                        {c.metric_averages && Object.keys(c.metric_averages).length > 0 ? (
                          <Stack spacing={0.5}>
                            {Object.entries(c.metric_averages).map(([name, avg]) => {
                              const pct = Math.round(avg * 100);
                              const color = pct >= 80 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444";
                              return (
                                <Stack key={name} direction="row" spacing={1} alignItems="center">
                                  <Typography variant="caption" color="text.secondary" sx={{ minWidth: 100, fontSize: 11 }}>{name}</Typography>
                                  <Typography variant="caption" fontWeight={700} color={color} sx={{ fontSize: 11 }}>{pct}%</Typography>
                                </Stack>
                              );
                            })}
                          </Stack>
                        ) : (
                          <Typography variant="caption" color="text.secondary">—</Typography>
                        )}
                      </TableCell>
                      <TableCell>
                        <Typography variant="caption" color="text.secondary">—</Typography>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CaseDrawer
        campaignId={drawerCampaignId}
        open={!!drawerCampaignId}
        onClose={() => setDrawerCampaignId(null)}
      />
    </Container>
  );
}
