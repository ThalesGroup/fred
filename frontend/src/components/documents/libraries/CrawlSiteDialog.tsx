import LanguageIcon from "@mui/icons-material/Language";
import {
  Alert,
  Box,
  Button,
  Checkbox,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  FormControl,
  FormControlLabel,
  InputLabel,
  LinearProgress,
  MenuItem,
  Select,
  Stack,
  TextField,
  Typography,
} from "@mui/material";
import React from "react";
import {
  CrawlRun,
  useCrawlSiteMutation,
  useGetCrawlSiteRunQuery,
} from "../../../slices/knowledgeFlow/crawlSiteApi";
import { useToast } from "../../ToastProvider";

type CrawlSiteDialogProps = {
  open: boolean;
  onClose: () => void;
  onStarted?: (payload: { run: CrawlRun; resourceId: string; directoryName: string }) => void;
  onFinished?: () => void;
  redirectTo?: string;
};

/**
 * Why:
 * The crawl completes while the user is usually already on the Resources/Documents page.
 * In that case, navigating to the same URL may keep the SPA in a stale state, while a
 * full browser reload reliably restores the view.
 *
 * How to use:
 * Pass the desired Resources URL after a successful crawl. The helper reloads when the
 * target matches the current route, otherwise it performs a browser navigation.
 *
 * Example:
 * ```ts
 * redirectAfterCrawl("/team/personal/ressources?view=documents");
 * ```
 */
function redirectAfterCrawl(redirectTo?: string): void {
  if (!redirectTo) return;
  const currentUrl = new URL(window.location.href);
  const targetUrl = new URL(redirectTo, window.location.origin);

  if (currentUrl.pathname === targetUrl.pathname && currentUrl.search === targetUrl.search) {
    window.location.reload();
    return;
  }

  window.location.assign(targetUrl.toString());
}

/**
 * Why:
 * This dialog starts a crawl and keeps polling the crawl run until it reaches a terminal state.
 *
 * How to use:
 * Render it from the Resources/Documents UI, provide `open` and `onClose`, and optionally pass
 * `redirectTo` so successful crawls return the user to the refreshed Resources page.
 *
 * Example:
 * ```tsx
 * <CrawlSiteDialog
 *   open={open}
 *   onClose={() => setOpen(false)}
 *   redirectTo="/team/personal/ressources?view=documents"
 * />
 * ```
 */
export function CrawlSiteDialog({ open, onClose, onStarted, onFinished, redirectTo }: CrawlSiteDialogProps) {
  const { showError, showInfo } = useToast();
  const [siteUrl, setSiteUrl] = React.useState("");
  const [directoryName, setDirectoryName] = React.useState("");
  const [processingProfile, setProcessingProfile] = React.useState<"fast" | "medium" | "rich">("fast");
  const [maxDepth, setMaxDepth] = React.useState(2);
  const [maxPages, setMaxPages] = React.useState(100);
  const [restrictToDomain, setRestrictToDomain] = React.useState(true);
  const [respectRobotsTxt, setRespectRobotsTxt] = React.useState(true);
  const [activeRunId, setActiveRunId] = React.useState<string | null>(null);
  const [localError, setLocalError] = React.useState<string | null>(null);
  const [crawlSite, { isLoading }] = useCrawlSiteMutation();
  const { data: activeRun } = useGetCrawlSiteRunQuery(activeRunId || "", {
    skip: !activeRunId,
    pollingInterval: activeRunId ? 2500 : 0,
  });

  React.useEffect(() => {
    if (!activeRun) return;
    const status = activeRun.run.status;
    if (status === "completed") {
      showInfo({ summary: "Crawl complete", detail: activeRun.ui_status });
      setActiveRunId(null);
      onFinished?.();
      if (redirectTo) {
        redirectAfterCrawl(redirectTo);
        return;
      }
      onClose();
    }
    if (status === "failed") {
      showError({ summary: "Crawl failed", detail: activeRun.run.error || activeRun.ui_status });
      setActiveRunId(null);
      onFinished?.();
    }
  }, [activeRun, onClose, onFinished, redirectTo, showError, showInfo]);

  const validate = () => {
    if (!siteUrl.trim()) return "Site URL is required";
    if (!directoryName.trim()) return "Directory name is required";
    try {
      const parsed = new URL(siteUrl);
      if (!["http:", "https:"].includes(parsed.protocol)) return "Use an http or https URL";
    } catch {
      return "Enter a valid site URL";
    }
    if (maxDepth < 0) return "Max crawl depth must be 0 or more";
    if (maxPages < 1) return "Max pages must be at least 1";
    return null;
  };

  const handleSubmit = async () => {
    const error = validate();
    if (error) {
      setLocalError(error);
      return;
    }
    setLocalError(null);
    try {
      const response = await crawlSite({
        site_url: siteUrl.trim(),
        directory_name: directoryName.trim(),
        processing_profile: processingProfile,
        max_depth: maxDepth,
        max_pages: maxPages,
        restrict_to_domain: restrictToDomain,
        respect_robots_txt: respectRobotsTxt,
      }).unwrap();
      setActiveRunId(response.run.id);
      onStarted?.({
        run: response.run,
        resourceId: response.resource.id,
        directoryName: response.resource.name,
      });
      showInfo({ summary: "Crawl started", detail: response.resource.name });
    } catch (e: any) {
      showError({ summary: "Failed to start crawl", detail: e?.data?.detail || e?.message || "Unknown error" });
    }
  };

  const busy = isLoading || Boolean(activeRunId);

  return (
    <Dialog open={open} onClose={busy ? undefined : onClose} fullWidth maxWidth="sm">
      <DialogTitle sx={{ display: "flex", alignItems: "center", gap: 1 }}>
        <LanguageIcon fontSize="small" />
        Crawl a site
      </DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ pt: 1 }}>
          {localError && <Alert severity="error">{localError}</Alert>}
          {activeRun && (
            <Box>
              <Typography variant="body2" sx={{ mb: 1 }}>
                {activeRun.ui_status} · {activeRun.run.extracted_count}/{activeRun.run.discovered_count || maxPages} pages
              </Typography>
              <LinearProgress />
            </Box>
          )}
          <TextField
            label="Site URL"
            value={siteUrl}
            onChange={(e) => setSiteUrl(e.target.value)}
            required
            disabled={busy}
            fullWidth
          />
          <TextField
            label="Directory name"
            value={directoryName}
            onChange={(e) => setDirectoryName(e.target.value)}
            required
            disabled={busy}
            fullWidth
          />
          <FormControl fullWidth>
            <InputLabel>Processing profile</InputLabel>
            <Select
              value={processingProfile}
              label="Processing profile"
              onChange={(e) => setProcessingProfile(e.target.value as "fast" | "medium" | "rich")}
              disabled={busy}
            >
              <MenuItem value="fast">Fast</MenuItem>
              <MenuItem value="medium">Medium</MenuItem>
              <MenuItem value="rich">Rich</MenuItem>
            </Select>
          </FormControl>
          <Box display="grid" gridTemplateColumns={{ xs: "1fr", sm: "1fr 1fr" }} gap={2}>
            <TextField
              label="Max crawl depth"
              type="number"
              value={maxDepth}
              onChange={(e) => setMaxDepth(Number(e.target.value))}
              disabled={busy}
              inputProps={{ min: 0, max: 10 }}
            />
            <TextField
              label="Max pages"
              type="number"
              value={maxPages}
              onChange={(e) => setMaxPages(Number(e.target.value))}
              disabled={busy}
              inputProps={{ min: 1, max: 10000 }}
            />
          </Box>
          <FormControlLabel
            control={<Checkbox checked={restrictToDomain} onChange={(e) => setRestrictToDomain(e.target.checked)} />}
            label="Restrict to domain"
            disabled={busy}
          />
          <FormControlLabel
            control={<Checkbox checked={respectRobotsTxt} onChange={(e) => setRespectRobotsTxt(e.target.checked)} />}
            label="Respect robots.txt"
            disabled={busy}
          />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose} disabled={busy}>
          Cancel
        </Button>
        <Button variant="contained" onClick={handleSubmit} disabled={busy}>
          Start
        </Button>
      </DialogActions>
    </Dialog>
  );
}
