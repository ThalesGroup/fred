import LibraryBooksIcon from "@mui/icons-material/LibraryBooks";
import { Box, Button, Chip, Paper, Typography } from "@mui/material";
import Grid2 from "@mui/material/Grid2";
import { useEffect, useMemo, useState } from "react";
import FoldableChatSection from "./FoldableChatSection";
import { VectorSearchHit } from "../../slices/agentic/agenticOpenApi";
import { SourceDetailsDialog } from "./SourceDetailsDialog";

type Props = {
  sources: VectorSearchHit[];
  expandSources?: boolean;
  enableSources?: boolean;
  pageSize?: number; // default 8
  highlightUid?: string | null;
};

type SelectedState = null | { uid: string; hits: VectorSearchHit[] };

function SourceRow({
  uid,
  hits,
  onOpen,
  highlighted = false,
}: {
  uid: string;
  hits: VectorSearchHit[];
  onOpen: () => void;
  highlighted: boolean; 
}) {
  const bestScore = Math.max(...hits.map(h => h.score ?? 0));
  const bestPct = Math.round(Math.max(0, Math.min(1, bestScore)) * 100);
  const first = hits[0] ?? ({} as VectorSearchHit);
  const title =
    (hits.find(h => h.title)?.title || first.title || first.file_name || uid)?.trim() || uid;
  const fileName = first.file_name || "";
  const mime = first.mime_type || "";
  const lang = first.language || "";
  const pageCount = [...new Set(hits.map(h => h.page).filter(Boolean))].length;

  const tags = Array.from(new Set(hits.flatMap(h => h.tag_names ?? [])));
  const shownTags = tags.slice(0, 3);
  const extra = Math.max(0, tags.length - shownTags.length);

  return (
    <Paper
      variant="outlined"
      sx={{
    px: 1.5,
    py: 1,
    mb: 1,
    borderRadius: 2,
    borderColor: highlighted ? "primary.main" : undefined,
    boxShadow: highlighted ? 3 : undefined,
    "&:hover": { bgcolor: "action.hover" },
    cursor: "pointer",
    transition: "box-shadow 120ms ease, border-color 120ms ease",
  }}
      role="button"
      tabIndex={0}
      onClick={onOpen}
      onKeyDown={(e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          onOpen();
        }
      }}
      aria-label={`Open details for ${title}`}
    >
      <Grid2 container alignItems="center" spacing={1}>
        <Grid2 size={{ xs: "auto" }}>
          <Box
            sx={{
              minWidth: 44,
              height: 24,
              borderRadius: 1,
              bgcolor: "primary.main",
              color: "primary.contrastText",
              fontSize: 12,
              fontWeight: 700,
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              px: 1,
            }}
          >
            {bestPct}%
          </Box>
        </Grid2>

        <Grid2 size={{ xs: 8}}>
          <Box sx={{ display: "flex", alignItems: "center", gap: 1, minWidth: 0 }}>
            <Typography
              variant="subtitle2"
              noWrap
              title={title}
              sx={{ fontWeight: 600, maxWidth: "60%" }}
            >
              {title}
            </Typography>
            {fileName && (
              <Typography variant="body2" noWrap title={fileName} sx={{ color: "text.secondary" }}>
                {fileName}
              </Typography>
            )}
          </Box>

          <Box sx={{ display: "flex", alignItems: "center", gap: 0.5, mt: 0.5, flexWrap: "wrap" }}>
            {shownTags.map((t) => (
              <Chip key={t} size="small" label={t} sx={{ borderRadius: 1.5 }} />
            ))}
            {extra > 0 && <Chip size="small" label={`+${extra}`} sx={{ borderRadius: 1.5 }} />}
          </Box>
        </Grid2>

        <Grid2 size={{ xs: "auto" }}>
          <Typography variant="caption" sx={{ color: "text.secondary" }}>
            {mime || "—"} {lang ? `• ${lang}` : ""} {pageCount ? `• ${pageCount} page(s)` : ""}
          </Typography>
        </Grid2>
      </Grid2>
    </Paper>
  );
}

export default function Sources({
  sources,
  expandSources = false,
  enableSources = false,
  pageSize = 8,
  highlightUid,
}: Props) {
  const [visibleCount, setVisibleCount] = useState(pageSize);
  const [selected, setSelected] = useState<SelectedState>(null);

  // -------- keep your analytics/logging exactly as-is --------
  useEffect(() => {
    if (!sources?.length) return;
    const pct = (x?: number | null) => Math.round(Math.max(0, Math.min(1, x ?? 0)) * 100);
    const short = (s?: string | null, n = 80) =>
      (s ?? "").length > n ? (s ?? "").slice(0, n - 1) + "…" : (s ?? "");
    const uniq = <T,>(arr: T[]) => Array.from(new Set(arr));
    const asDate = (s?: string | null) => (s ? new Date(s) : undefined);
    const fmtDate = (s?: string | null) => {
      const d = asDate(s);
      return d ? `${d.toLocaleDateString()} ${d.toLocaleTimeString()}` : "";
    };

    console.groupCollapsed(`[Sources] Received ${sources.length} hits`);
    console.table(
      sources.map((s, i) => ({
        i,
        uid: s.uid,
        score: s.score,
        "%": pct(s.score),
        rank: s.rank ?? "",
        page: s.page ?? "",
        section: short(s.section, 40),
        title: short(s.title, 50) || short(s.file_name, 50),
        file: short(s.file_name, 40),
        repo: short(s.repository, 40),
        pull: short(s.pull_location, 40),
        path: short(s.file_path, 40),
        lang: s.language ?? "",
        mime: s.mime_type ?? "",
        type: s.type ?? "",
        tags: (s.tag_names || []).join(", "),
        author: short(s.author, 40),
        created: fmtDate(s.created),
        modified: fmtDate(s.modified),
        model: s.embedding_model ?? "",
        vindex: s.vector_index ?? "",
        tokens: s.token_count ?? "",
        retrieved_at: fmtDate(s.retrieved_at),
        retrieval_session_id: short(s.retrieval_session_id, 20),
        has_fragment: Boolean(s.viewer_fragment),
        frag_len: (s.viewer_fragment || "").length,
        content_len: (s.content || "").length,
        confidential: s.confidential ?? null,
      }))
    );

    const byUid = sources.reduce<Record<string, typeof sources>>((acc, h) => {
      (acc[h.uid] ||= []).push(h);
      return acc;
    }, {});
    const docSummaries = Object.entries(byUid).map(([uid, hits]) => {
      const best = Math.max(...hits.map(h => h.score ?? 0));
      const avg = hits.reduce((sum, h) => sum + (h.score ?? 0), 0) / (hits.length || 1);
      const langs = uniq(hits.map(h => h.language).filter(Boolean) as string[]);
      const mimes = uniq(hits.map(h => h.mime_type).filter(Boolean) as string[]);
      const tags = uniq(hits.flatMap(h => h.tag_names ?? []));
      const created = hits.map(h => h.created).filter(Boolean) as string[];
      const modified = hits.map(h => h.modified).filter(Boolean) as string[];
      const title =
        (hits.find(h => h.title)?.title || hits[0]?.title)?.trim() ||
        hits[0]?.file_name?.trim() ||
        uid;

      const minMod = modified.length
        ? modified.reduce((a, b) => (new Date(a) < new Date(b) ? a : b))
        : undefined;
      const maxMod = modified.length
        ? modified.reduce((a, b) => (new Date(a) > new Date(b) ? a : b))
        : undefined;

      return {
        uid,
        title: short(title, 60),
        hits: hits.length,
        best_pct: pct(best),
        avg_pct: pct(avg),
        langs: langs.join("|"),
        mimes: mimes.join("|"),
        tags: tags.slice(0, 6).join(", ") + (tags.length > 6 ? ` (+${tags.length - 6})` : ""),
        created_any: created.length ? fmtDate(created[0]) : "",
        modified_range: minMod || maxMod ? `${fmtDate(minMod)} → ${fmtDate(maxMod)}` : "",
      };
    });
    console.table(docSummaries.sort((a, b) => b.best_pct - a.best_pct));

    const count = (arr: (string | undefined | null)[]) =>
      arr.reduce<Record<string, number>>((acc, v) => {
        const k = (v || "(none)").toLowerCase();
        acc[k] = (acc[k] || 0) + 1;
        return acc;
      }, {});
    const sortPairs = (obj: Record<string, number>) =>
      Object.entries(obj).sort((a, b) => b[1] - a[1]);

    const mimeDist = sortPairs(count(sources.map(s => s.mime_type)));
    const langDist = sortPairs(count(sources.map(s => s.language)));
    const tagDist = sortPairs(count(sources.flatMap(s => s.tag_names || [])));

    console.log("[Sources] MIME distribution", Object.fromEntries(mimeDist));
    console.log("[Sources] Language distribution", Object.fromEntries(langDist));
    console.log("[Sources] Top tags", Object.fromEntries(tagDist.slice(0, 20)));

    const sample = sources.slice(0, 10).map(s => ({
      uid: s.uid,
      page: s.page ?? "",
      section: short(s.section, 40),
      has_fragment: Boolean(s.viewer_fragment),
      fragment: short(s.viewer_fragment, 120),
      content: short(s.content, 120),
    }));
    console.table(sample);

    const xmlLike = mimeDist.filter(([m]) => /xml/.test(m));
    if (xmlLike.length) console.warn("[Sources][Audit] XML-like MIME present:", Object.fromEntries(xmlLike));
    const missingTitles = sources.filter(s => !s.title && !s.file_name).length;
    if (missingTitles) console.warn(`[Sources][Audit] ${missingTitles} hit(s) with no title/file_name`);
    const noMime = sources.filter(s => !s.mime_type).length;
    if (noMime) console.warn(`[Sources][Audit] ${noMime} hit(s) with no mime_type`);
    const zeroScores = sources.filter(s => !s.score).length;
    if (zeroScores) console.warn(`[Sources][Audit] ${zeroScores} hit(s) with score=0 or undefined`);

    console.groupEnd();

    setVisibleCount(pageSize);
  }, [sources, pageSize]);
  // -------- end analytics --------

  const groupedOrdered = useMemo(() => {
    if (!sources?.length) return [];
    const grouped: Record<string, VectorSearchHit[]> = sources.reduce((acc, h) => {
      if (!h?.uid) return acc;
      (acc[h.uid] ||= []).push(h);
      return acc;
    }, {} as Record<string, VectorSearchHit[]>);

    const entries = Object.entries(grouped).map(([uid, hits]) => {
      const bestScore = Math.max(...hits.map(h => h.score ?? 0));
      return { uid, hits, bestScore };
    });

    return entries.sort((a, b) => (b.bestScore ?? 0) - (a.bestScore ?? 0));
  }, [sources]);

  if (!enableSources || !sources?.length) return null;

  const docCount = groupedOrdered.length;
  const items = groupedOrdered.slice(0, visibleCount);
  const hasMore = visibleCount < docCount;

  return (
    <FoldableChatSection
      title={`Sources (${docCount})`}
      icon={<LibraryBooksIcon />}
      defaultOpen={expandSources}
      sx={{ mt: 2 }}
    >
      <Box sx={{ mt: 0.5 }}>
        {items.map(({ uid, hits }) => (
          <SourceRow key={uid} uid={uid} hits={hits} 
          highlighted={uid === highlightUid}
          onOpen={() => setSelected({ uid, hits })} />
        ))}
      </Box>

      {hasMore && (
        <Box sx={{ display: "flex", justifyContent: "center", mt: 1 }}>
          <Button variant="text" onClick={() => setVisibleCount((c) => c + pageSize)}>
            Show more
          </Button>
        </Box>
      )}

      <SourceDetailsDialog
        open={!!selected}
        onClose={() => setSelected(null)}
        documentId={selected?.uid || ""}
        hits={selected?.hits || []}
      />
    </FoldableChatSection>
  );
}
