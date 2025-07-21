import { Stack, Typography, Box, Divider, Card } from "@mui/material";
import { Tag, useListTagsKnowledgeFlowV1TagsGetQuery } from "../slices/knowledgeFlow/knowledgeFlowOpenApi";
import InvisibleLink from "../components/InvisibleLink";
import Tooltip from "@mui/material/Tooltip";
import dayjs from "dayjs";

export function DocumentLibrariesList() {
  const { data: libraries } = useListTagsKnowledgeFlowV1TagsGetQuery();

  return (
    <Card sx={{ borderRadius: 4, p: 2 }}>
      {libraries && libraries.length > 0 ? (
        <Stack spacing={0} divider={<Divider />}>
          {/* No gap, use divider for separation */}
          {libraries.map((library) => (
            <DocumentLibraryRow key={library.id} library={library} />
          ))}
        </Stack>
      ) : (
        <Typography color="text.secondary" px={2} py={2}>
          No document libraries found.
        </Typography>
      )}
    </Card>
  );
}

function formatLastUpdate(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const diffMs = now.getTime() - date.getTime();
  const diffDays = Math.floor(diffMs / (1000 * 60 * 60 * 24));
  if (diffDays < 1) {
    return "Today";
  } else if (diffDays === 1) {
    return "1 day ago";
  } else if (diffDays < 30) {
    return `${diffDays} days ago`;
  } else {
    // Use local date display (e.g. 23/02/25)
    return dayjs(date).format("L");
  }
}

function DocumentLibraryRow({ library }: { library: Tag }) {
  const documentCount = library.document_ids ? library.document_ids.length : 0;
  const lastUpdateLabel = formatLastUpdate(library.updated_at);
  const lastUpdateTooltip = new Date(library.updated_at).toLocaleString();

  return (
    <InvisibleLink to={`/documentLibrary/${library.id}`}>
      <Box
        display="flex"
        alignItems="center"
        px={2}
        py={1.5}
        borderRadius={3}
        sx={{
          transition: "background 0.2s",
          "&:hover": {
            background: (theme) => theme.palette.action.hover,
          },
          minWidth: 0,
          width: "100%",
        }}
      >
        <Typography variant="body1" fontWeight={500} sx={{ flex: 2, minWidth: 0 }} noWrap>
          {library.name}
        </Typography>
        <Typography variant="body2" color="text.secondary" sx={{ flex: 1, minWidth: 120 }}>
          {documentCount} document{documentCount !== 1 ? "s" : ""}
        </Typography>
        <Tooltip title={lastUpdateTooltip} arrow>
          <Typography variant="caption" color="text.secondary" sx={{ flex: 1, minWidth: 160 }}>
            {lastUpdateLabel}
          </Typography>
        </Tooltip>
      </Box>
    </InvisibleLink>
  );
}
