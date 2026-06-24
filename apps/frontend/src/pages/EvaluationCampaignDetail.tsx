import {
  Accordion,
  AccordionDetails,
  AccordionSummary,
  Alert,
  Box,
  Card,
  CardContent,
  Chip,
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
import ExpandMoreIcon from "@mui/icons-material/ExpandMore";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { TopBar } from "../common/TopBar";
import { KeyCloakService } from "../security/KeycloakService";
import Button from "../rework/components/shared/atoms/Button/Button";
import { IndicatorDot } from "../rework/components/shared/atoms/IndicatorDot/IndicatorDot";
import ProgressBar from "../rework/components/shared/atoms/ProgressBar/ProgressBar";
import {
  useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation,
  useAnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostMutation,
  useGetCampaignEvaluationV1CampaignsCampaignIdGetQuery,
  useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery,
  type CampaignAnalysisResult,
  type EvaluationCampaignResponse,
  type EvaluationCaseResponse,
  type EvaluationMetricResultResponse,
} from "../slices/evaluation/evaluationOpenApi";
import { useGetTelemetryQuery, useGetTelemetrySessionQuery } from "../slices/evaluation/evaluationApi";

// ── Helpers ───────────────────────────────────────────────────────────────────

function verdictColor(v: string): string {
  if (v === "passed") return "#22c55e";
  if (v === "failed") return "#ef4444";
  if (v === "insufficient") return "#f59e0b";
  if (v === "inconclusive" || v === "error") return "#f59e0b";
  return "#6b7280";
}

function stateColor(s: string): string {
  if (s === "running") return "#3b82f6";
  if (s === "completed" || s === "succeeded") return "#22c55e";
  if (s === "failed" || s === "cancelled") return "#ef4444";
  if (s === "pending") return "#f59e0b";
  return "#6b7280";
}

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

function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { dateStyle: "short", timeStyle: "short" });
}

function formatMs(ms: number | null | undefined): string {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms} ms`;
  return `${(ms / 1000).toFixed(1)} s`;
}

function passRate(c: EvaluationCampaignResponse): number {
  if (!c.total_cases) return 0;
  return Math.round((c.passed_cases / c.total_cases) * 100);
}

// ── Animated counter ──────────────────────────────────────────────────────────

function useAnimatedCount(target: number): number {
  const [count, setCount] = useState(0);
  useEffect(() => {
    const start = performance.now();
    let raf: number;
    const tick = (now: number) => {
      const t = Math.min((now - start) / 800, 1);
      const ease = 1 - Math.pow(1 - t, 3);
      setCount(Math.round(ease * target));
      if (t < 1) raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target]);
  return count;
}

// ── SSE hook ──────────────────────────────────────────────────────────────────

function useCampaignSse(campaignId: string, onEvent: () => void) {
  const cbRef = useRef(onEvent);
  cbRef.current = onEvent;

  useEffect(() => {
    if (!campaignId) return;
    const ac = new AbortController();
    let retryMs = 1_000;

    const connect = async () => {
      try {
        const token = KeyCloakService.GetToken();
        const res = await fetch(`/evaluation/v1/campaigns/${campaignId}/events`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
          signal: ac.signal,
        });
        if (!res.ok || !res.body) return;
        retryMs = 1_000;
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let buf = "";
        while (true) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          const lines = buf.split("\n");
          buf = lines.pop() ?? "";
          for (const line of lines) {
            if (line.startsWith("data:")) cbRef.current();
          }
        }
      } catch {
        // AbortError swallowed
      }
      if (!ac.signal.aborted) {
        await new Promise((r) => setTimeout(r, retryMs));
        retryMs = Math.min(retryMs * 2, 30_000);
        connect();
      }
    };

    connect();
    return () => ac.abort();
  }, [campaignId]);
}

// ── Aggregate card ────────────────────────────────────────────────────────────

function AggregateCard({ label, value, color }: { label: string; value: number; color: string }) {
  const animated = useAnimatedCount(value);
  return (
    <Card sx={{ flex: 1, bgcolor: "rgba(255,255,255,0.04)", border: "1px solid rgba(255,255,255,0.08)" }}>
      <CardContent sx={{ py: 1.5 }}>
        <Typography variant="h5" fontWeight={800} color={color}>{animated}</Typography>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </CardContent>
    </Card>
  );
}

// ── Field block ───────────────────────────────────────────────────────────────

function FieldBlock({ label, value }: { label: string; value: string }) {
  return (
    <Box sx={{ mb: 1.5 }}>
      <Typography variant="caption" color="text.secondary" sx={{ display: "block", mb: 0.5 }}>{label}</Typography>
      <Box sx={{
        p: 1.5, borderRadius: 1, bgcolor: "rgba(255,255,255,0.05)",
        fontFamily: "monospace", fontSize: 12, whiteSpace: "pre-wrap",
        wordBreak: "break-word", maxHeight: 140, overflowY: "auto",
      }}>
        {value}
      </Box>
    </Box>
  );
}

// ── Case drawer ───────────────────────────────────────────────────────────────

function CaseDrawer({ caseData, onClose }: { caseData: EvaluationCaseResponse | null; onClose: () => void }) {
  return (
    <Drawer
      anchor="right"
      open={!!caseData}
      onClose={onClose}
      PaperProps={{ sx: { width: 560, bgcolor: "#12121e", p: 3, boxShadow: "-4px 0 24px rgba(0,0,0,0.5)" } }}
      SlideProps={{ timeout: 300 }}
    >
      {caseData && (
        <>
          <Stack direction="row" alignItems="center" justifyContent="space-between" sx={{ mb: 3 }}>
            <Typography variant="h6" fontWeight={700}>Détail du cas</Typography>
            <Stack direction="row" spacing={1} alignItems="center">
              <Pill label={caseData.verdict} color={verdictColor(caseData.verdict)} />
              <Button color="secondary" variant="outlined" size="small" onClick={onClose}>Fermer</Button>
            </Stack>
          </Stack>

          <Stack direction="row" spacing={3} sx={{ mb: 2 }}>
            <Box>
              <Typography variant="caption" color="text.secondary">Latence</Typography>
              <Typography variant="body2" fontWeight={600}>{formatMs(caseData.latency_ms)}</Typography>
            </Box>
            <Box>
              <Typography variant="caption" color="text.secondary">Statut</Typography>
              <Typography variant="body2" fontWeight={600}>{caseData.status}</Typography>
            </Box>
          </Stack>

          <Box sx={{ overflowY: "auto", flex: 1 }}>
            <FieldBlock label="Input" value={caseData.input} />
            {caseData.expected_output && <FieldBlock label="Sortie attendue" value={caseData.expected_output} />}
            {caseData.actual_output && <FieldBlock label="Sortie réelle" value={caseData.actual_output} />}

            {caseData.execution_error && (
              <Alert severity="error" sx={{ mb: 2 }}>
                <Typography variant="caption" fontWeight={700} display="block">Erreur d'exécution</Typography>
                <Typography variant="body2">{caseData.execution_error}</Typography>
              </Alert>
            )}

            {caseData.scoring_errors?.length > 0 && (
              <Alert severity="warning" sx={{ mb: 2 }}>
                <Typography variant="caption" fontWeight={700} display="block">Erreurs de scoring</Typography>
                {caseData.scoring_errors.map((e: string, i: number) => (
                  <Typography key={i} variant="body2">{e}</Typography>
                ))}
              </Alert>
            )}

            {caseData.metrics.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Métriques ({caseData.metrics.length})</Typography>
                <Stack spacing={1.5}>
                  {caseData.metrics.map((m: EvaluationMetricResultResponse, i: number) => (
                    <Box key={i}>
                      <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                        <Typography variant="caption" color="text.secondary">{m.name.replace("Metric", "")}</Typography>
                        <Stack direction="row" spacing={1} alignItems="center">
                          {m.score != null && (
                            <Typography variant="caption" fontWeight={700} color={verdictColor(m.verdict)}>
                              {(m.score * 100).toFixed(0)}%
                            </Typography>
                          )}
                          <Pill label={m.verdict} color={verdictColor(m.verdict)} />
                        </Stack>
                      </Stack>
                      {m.score != null && (
                        <ProgressBar
                          theme={m.verdict === "passed" ? "success" : m.verdict === "insufficient" ? "warning" : "error"}
                          current={Math.round(m.score * 100)}
                          max={100}
                        />
                      )}
                      {m.explanation && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: "block", mt: 0.5 }}>
                          {m.explanation}
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Stack>
              </Box>
            )}

            {caseData.structural_checks?.length > 0 && (
              <Box>
                <Typography variant="subtitle2" sx={{ mb: 1 }}>Vérifications structurelles ({caseData.structural_checks.length})</Typography>
                <Stack spacing={1}>
                  {caseData.structural_checks.map((c: { name: string; passed: boolean | null }, i: number) => (
                    <Stack key={i} direction="row" justifyContent="space-between" alignItems="center">
                      <Typography variant="caption" color="text.secondary">{c.name}</Typography>
                      <Pill
                        label={c.passed === null ? "skipped" : c.passed ? "passed" : "failed"}
                        color={c.passed === null ? "#6b7280" : c.passed ? "#22c55e" : "#ef4444"}
                      />
                    </Stack>
                  ))}
                </Stack>
              </Box>
            )}
          </Box>
        </>
      )}
    </Drawer>
  );
}

// ── Analysis card ─────────────────────────────────────────────────────────────

const RISK_COLOR: Record<string, string> = {
  low: "#22c55e",
  medium: "#f59e0b",
  high: "#ef4444",
};

function AnalysisSection({ title, items, color }: { title: string; items: string[]; color: string }) {
  return (
    <Box>
      <Typography variant="caption" sx={{ color, fontWeight: 700, letterSpacing: 1, textTransform: "uppercase", display: "block", mb: 1 }}>
        {title}
      </Typography>
      <Stack spacing={0.8}>
        {items.map((item, i) => (
          <Stack key={i} direction="row" spacing={1.5} alignItems="flex-start">
            <Box sx={{ width: 4, height: 4, borderRadius: "50%", bgcolor: color, mt: "7px", flexShrink: 0 }} />
            <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.6 }}>{item}</Typography>
          </Stack>
        ))}
      </Stack>
    </Box>
  );
}

function AnalysisCard({ analysis, onClose }: { analysis: CampaignAnalysisResult; onClose: () => void }) {
  const riskColor = RISK_COLOR[analysis.risk_level] ?? "#6b7280";
  return (
    <Card sx={{ mb: 3, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.10)" }}>
      <CardContent sx={{ p: 3 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" sx={{ mb: 2.5 }}>
          <Box>
            <Typography variant="subtitle2" sx={{ color: "text.primary", fontWeight: 700, mb: 0.5 }}>
              Analyse
            </Typography>
            <Typography variant="caption" sx={{ color: riskColor, fontFamily: "monospace", letterSpacing: 0.5 }}>
              risk: {analysis.risk_level}
            </Typography>
          </Box>
          <Button color="secondary" variant="text" size="small" onClick={onClose}>✕</Button>
        </Stack>

        <Typography variant="body2" color="text.secondary" sx={{ lineHeight: 1.7, mb: 3, borderLeft: "2px solid rgba(255,255,255,0.12)", pl: 2 }}>
          {analysis.summary}
        </Typography>

        <Stack spacing={2.5}>
          <AnalysisSection title="Points forts" items={analysis.strengths} color="#22c55e" />
          <AnalysisSection title="Points faibles" items={analysis.weaknesses} color="#f59e0b" />
          <AnalysisSection title="Recommandations" items={analysis.recommendations} color="#a78bfa" />
        </Stack>
      </CardContent>
    </Card>
  );
}

// ── Main ──────────────────────────────────────────────────────────────────────

export default function EvaluationCampaignDetail() {
  const { campaignId } = useParams<{ campaignId: string }>();
  const navigate = useNavigate();
  const location = useLocation();
  const [selectedCase, setSelectedCase] = useState<EvaluationCaseResponse | null>(null);
  const [cancelError, setCancelError] = useState<string | null>(null);
  const [progressDisplay, setProgressDisplay] = useState(0);

  const { data: campaign, isLoading: campaignLoading, refetch: refetchCampaign } =
    useGetCampaignEvaluationV1CampaignsCampaignIdGetQuery({ campaignId: campaignId! }, { skip: !campaignId });

  const { data: casesData, isLoading: casesLoading, refetch: refetchCases } =
    useListCasesEvaluationV1CampaignsCampaignIdCasesGetQuery(
      { campaignId: campaignId!, limit: 200 },
      { skip: !campaignId },
    );

  const [cancelCampaign, { isLoading: isCancelling }] =
    useCancelCampaignEvaluationV1CampaignsCampaignIdCancelPostMutation();

  const [analyzeCampaign, { isLoading: isAnalyzing }] =
    useAnalyzeCampaignEvaluationV1CampaignsCampaignIdAnalyzePostMutation();
  const [analysis, setAnalysis] = useState<CampaignAnalysisResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  const { data: telemetry } = useGetTelemetryQuery();
  const { data: langfuseSession } = useGetTelemetrySessionQuery(campaignId ?? "", {
    skip: !campaignId || !telemetry?.enabled,
    pollingInterval: 10000,
  });

  const handleAnalyze = async () => {
    if (!campaignId) return;
    setAnalysisError(null);
    try {
      const result = await analyzeCampaign({ campaignId }).unwrap();
      setAnalysis(result.analysis as CampaignAnalysisResult);
    } catch (e: any) {
      setAnalysisError(e?.data?.detail ?? "Erreur lors de l'analyse");
    }
  };

  const isLive = campaign?.operational_state === "running" || campaign?.operational_state === "pending";

  useCampaignSse(campaignId ?? "", () => { refetchCampaign(); refetchCases(); });

  // Auto-open case drawer when navigated from the campaigns list
  useEffect(() => {
    const selectedCaseId = location.state?.selectedCaseId;
    if (!selectedCaseId || !casesData?.cases) return;
    const found = casesData.cases.find((c) => c.case_id === selectedCaseId);
    if (found) setSelectedCase(found);
  }, [location.state?.selectedCaseId, casesData?.cases]);

  useEffect(() => {
    if (!campaign) return;
    const target = campaign.total_cases ? (campaign.completed_cases / campaign.total_cases) * 100 : 0;
    const t = setTimeout(() => setProgressDisplay(target), 100);
    return () => clearTimeout(t);
  }, [campaign?.completed_cases, campaign?.total_cases]);

  const handleCancel = async () => {
    if (!campaignId) return;
    setCancelError(null);
    try {
      await cancelCampaign({ campaignId }).unwrap();
    } catch (e: any) {
      setCancelError(e?.data?.detail ?? "Impossible d'annuler");
    }
  };

  if (campaignLoading) {
    return <Container maxWidth="xl" sx={{ py: 8, textAlign: "center" }}><CircularProgress /></Container>;
  }
  if (!campaign) {
    return <Container maxWidth="xl" sx={{ py: 4 }}><Alert severity="error">Campagne introuvable.</Alert></Container>;
  }

  const cases = casesData?.cases ?? [];
  const rate = passRate(campaign);

  return (
    <Container maxWidth="xl" sx={{ py: 3 }}>
      <TopBar title={campaign.name} description={`Campagne · ${campaign.campaign_id.slice(0, 12)}`}>
        <Stack direction="row" spacing={1} alignItems="center">
          {isLive && (
            <Button
              color="error" variant="outlined" size="medium"
              onClick={handleCancel} disabled={isCancelling}
            >
              {isCancelling ? <CircularProgress size={14} sx={{ mr: 1 }} /> : null}
              Annuler
            </Button>
          )}
          {campaign.operational_state === "completed" && (
            <Button
              color="secondary" variant="outlined" size="medium"
              onClick={handleAnalyze} disabled={isAnalyzing}
            >
              {isAnalyzing ? <CircularProgress size={14} sx={{ mr: 1 }} /> : null}
              {isAnalyzing ? "Analyse…" : "Analyser"}
            </Button>
          )}
          {telemetry?.enabled && (
            <Button
              color="secondary"
              variant="outlined"
              size="medium"
              disabled={!langfuseSession?.available}
              onClick={() => langfuseSession?.url && window.open(langfuseSession.url, "_blank")}
            >
              {langfuseSession?.available
                ? "Voir sur Langfuse ↗"
                : telemetry?.langfuse_session_url
                  ? "En attente de Langfuse…"
                  : "Langfuse hors ligne"}
            </Button>
          )}
          <Button color="secondary" variant="text" size="medium" onClick={() => navigate("/admin/evaluations")}>
            ← Retour
          </Button>
        </Stack>
      </TopBar>

      {cancelError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => setCancelError(null)}>{cancelError}</Alert>
      )}

      {/* Hero state row */}
      <Stack direction="row" spacing={2} alignItems="center" sx={{ mb: 3 }}>
        {isLive && <IndicatorDot status="streaming" label="En cours d'exécution" />}
        <Pill label={campaign.operational_state} color={stateColor(campaign.operational_state)} />
        <Pill label={`Verdict: ${campaign.verdict}`} color={verdictColor(campaign.verdict)} />
        <Typography variant="body2" color="text.secondary">
          {rate}% de réussite · {campaign.completed_cases}/{campaign.total_cases} cas
        </Typography>
      </Stack>

      {/* Progress bar with glow at leading edge */}
      <Box sx={{ mb: 3, position: "relative" }}>
        <Box sx={{ height: 8, borderRadius: 4, bgcolor: "rgba(255,255,255,0.08)", overflow: "hidden", position: "relative" }}>
          <Box
            sx={{
              position: "absolute", top: 0, left: 0, height: "100%",
              width: `${progressDisplay}%`,
              bgcolor: "#7c3aed",
              borderRadius: 4,
              transition: "width 0.8s ease",
              "&::after": isLive ? {
                content: '""',
                position: "absolute", right: 0, top: "50%", transform: "translateY(-50%)",
                width: 12, height: 12, borderRadius: "50%",
                bgcolor: "#a78bfa",
                boxShadow: "0 0 12px 4px rgba(167,139,250,0.8)",
              } : {},
            }}
          />
        </Box>
        {isLive && (
          <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, display: "block" }}>
            Exécution en cours…
          </Typography>
        )}
      </Box>

      {/* Aggregate cards */}
      <Stack direction="row" spacing={2} sx={{ mb: 3 }}>
        <AggregateCard label="Réussis" value={campaign.passed_cases} color="#22c55e" />
        <AggregateCard label="Échoués" value={campaign.failed_cases} color="#ef4444" />
        <AggregateCard label="Erreurs exec." value={campaign.execution_error_cases} color="#f59e0b" />
        <AggregateCard label="Erreurs scoring" value={campaign.scoring_error_cases} color="#6b7280" />
      </Stack>

      {/* Metric averages */}
      {campaign.metric_averages && Object.keys(campaign.metric_averages).length > 0 && (
        <Card sx={{ mb: 3, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
          <CardContent sx={{ py: 1.5 }}>
            <Typography variant="subtitle2" sx={{ mb: 1.5 }}>Scores par métrique</Typography>
            <Stack spacing={1}>
              {Object.entries(campaign.metric_averages).map(([name, avg]) => {
                const pct = Math.round(avg * 100);
                const color = pct >= 80 ? "#22c55e" : pct >= 50 ? "#f59e0b" : "#ef4444";
                return (
                  <Box key={name}>
                    <Stack direction="row" justifyContent="space-between" sx={{ mb: 0.5 }}>
                      <Typography variant="caption" color="text.secondary">{name}</Typography>
                      <Typography variant="caption" fontWeight={700} color={color}>{pct}%</Typography>
                    </Stack>
                    <Box sx={{ height: 6, borderRadius: 3, bgcolor: "rgba(255,255,255,0.08)", overflow: "hidden" }}>
                      <Box sx={{ height: "100%", width: `${pct}%`, bgcolor: color, borderRadius: 3, transition: "width 0.8s ease" }} />
                    </Box>
                  </Box>
                );
              })}
              {(() => {
                const values = Object.values(campaign.metric_averages);
                const globalPct = Math.round((values.reduce((a, b) => a + b, 0) / values.length) * 100);
                const color = globalPct >= 80 ? "#22c55e" : globalPct >= 50 ? "#f59e0b" : "#ef4444";
                return (
                  <Box sx={{ pt: 1, borderTop: "1px solid rgba(255,255,255,0.08)" }}>
                    <Stack direction="row" justifyContent="space-between">
                      <Typography variant="caption" color="text.secondary" fontWeight={600}>Score global</Typography>
                      <Typography variant="caption" fontWeight={800} color={color}>{globalPct}%</Typography>
                    </Stack>
                  </Box>
                );
              })()}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Analysis */}
      {analysisError && (
        <Alert severity="error" sx={{ mb: 3 }} onClose={() => setAnalysisError(null)}>{analysisError}</Alert>
      )}
      {analysis && <AnalysisCard analysis={analysis} onClose={() => setAnalysis(null)} />}

      {/* Metadata accordion */}
      <Accordion sx={{ mb: 3, bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }} disableGutters>
        <AccordionSummary expandIcon={<ExpandMoreIcon />}>
          <Typography variant="subtitle2">Informations de la campagne</Typography>
        </AccordionSummary>
        <AccordionDetails>
          <Stack direction="row" flexWrap="wrap" gap={3}>
            {[
              { label: "Dataset", value: `${campaign.dataset_name}${campaign.dataset_version ? ` v${campaign.dataset_version}` : ""}` },
              { label: "Profil scoring", value: campaign.profile },
              { label: "Juge", value: campaign.judge_profile_id },
              { label: "Équipe", value: campaign.team_id },
              { label: "Créée le", value: formatDate(campaign.created_at) },
              { label: "Démarrée le", value: formatDate(campaign.started_at) },
              { label: "Terminée le", value: formatDate(campaign.completed_at) },
            ].map((item) => (
              <Box key={item.label} sx={{ minWidth: 160 }}>
                <Typography variant="caption" color="text.secondary">{item.label}</Typography>
                <Typography variant="body2" sx={{ fontFamily: "monospace", fontSize: 12 }}>{item.value}</Typography>
              </Box>
            ))}
          </Stack>
        </AccordionDetails>
      </Accordion>

      {/* Cases table */}
      <Card sx={{ bgcolor: "rgba(255,255,255,0.03)", border: "1px solid rgba(255,255,255,0.08)" }}>
        <CardContent sx={{ p: 0 }}>
          <Typography variant="subtitle1" sx={{ px: 2, pt: 2, pb: 1 }} fontWeight={600}>
            Cas ({casesData?.total ?? 0})
          </Typography>
          {casesLoading ? (
            <Box sx={{ py: 4, textAlign: "center" }}><CircularProgress size={32} /></Box>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow sx={{ "& th": { color: "text.secondary", fontSize: 12, fontWeight: 600, textTransform: "uppercase", letterSpacing: 0.5 } }}>
                  <TableCell>ID</TableCell>
                  <TableCell>Input</TableCell>
                  <TableCell>Statut</TableCell>
                  <TableCell>Verdict</TableCell>
                  <TableCell>Latence</TableCell>
                  <TableCell>Métriques</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {cases.map((c) => (
                  <TableRow
                    key={c.case_id}
                    hover
                    sx={{ cursor: "pointer", "&:hover": { bgcolor: "rgba(255,255,255,0.04)" } }}
                    onClick={() => setSelectedCase(c)}
                  >
                    <TableCell>
                      <Typography variant="caption" sx={{ fontFamily: "monospace" }}>
                        {c.external_id ?? c.case_id.slice(0, 10)}
                      </Typography>
                    </TableCell>
                    <TableCell sx={{ maxWidth: 280 }}>
                      <Typography variant="body2" noWrap color="text.secondary">{c.input}</Typography>
                    </TableCell>
                    <TableCell>
                      <Pill
                        label={c.status}
                        color={c.status === "completed" ? "#22c55e" : c.status === "error" ? "#ef4444" : c.status === "running" ? "#3b82f6" : "#6b7280"}
                      />
                    </TableCell>
                    <TableCell>
                      <Pill label={c.verdict} color={verdictColor(c.verdict)} />
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption" color="text.secondary">{formatMs(c.latency_ms)}</Typography>
                    </TableCell>
                    <TableCell>
                      {c.metrics.length > 0 ? (
                        <Stack direction="row" spacing={0.5} flexWrap="wrap">
                          {c.metrics.slice(0, 2).map((m: EvaluationMetricResultResponse, i: number) => (
                            <Chip
                              key={i}
                              label={`${m.name.replace("Metric", "")} ${m.score != null ? `${(m.score * 100).toFixed(0)}%` : "—"}`}
                              size="small"
                              sx={{ fontSize: 10, color: verdictColor(m.verdict), border: `1px solid ${verdictColor(m.verdict)}40`, bgcolor: `${verdictColor(m.verdict)}18` }}
                            />
                          ))}
                          {c.metrics.length > 2 && <Chip label={`+${c.metrics.length - 2}`} size="small" sx={{ fontSize: 10 }} />}
                        </Stack>
                      ) : (
                        <Typography variant="caption" color="text.secondary">—</Typography>
                      )}
                    </TableCell>
                    <TableCell onClick={(e) => e.stopPropagation()}>
                      <Button color="secondary" variant="outlined" size="small" onClick={() => setSelectedCase(c)}>
                        Voir
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      <CaseDrawer caseData={selectedCase} onClose={() => setSelectedCase(null)} />
    </Container>
  );
}
