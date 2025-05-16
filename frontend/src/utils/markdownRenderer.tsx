import { Box, CircularProgress } from "@mui/material";
import MarkdownRenderer from "../common/MarkdownRenderer";

interface MarkdownViewerProps {
  markdown: string;
  isLoading?: boolean;
}

/**
 * Simple Markdown viewer component
 */
const MarkdownViewer = ({ markdown, isLoading = false }: MarkdownViewerProps) => {
  return (
    <Box sx={{ display: 'flex', flexDirection: 'column', height: '100%' }}>
      <Box sx={{ flex: 1, overflow: 'auto', p: 3, bgcolor: 'background.paper', borderRadius: 1 }}>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
            <CircularProgress />
          </Box>
        ) : (
         <MarkdownRenderer content={markdown}  size = 'medium' />
        )}
      </Box>
    </Box>
  );
};

export default MarkdownViewer;