import { useEffect, useState } from "react";
import { 
  Box, 
  Typography, 
  IconButton, 
  Button, 
  CircularProgress, 
  AppBar,
  Toolbar,
  Chip,
  Drawer,
  Backdrop
} from "@mui/material";
import CloseIcon from "@mui/icons-material/Close";
import DownloadIcon from '@mui/icons-material/Download';
import OpenInNewIcon from '@mui/icons-material/OpenInNew';
import PersonOutlineIcon from '@mui/icons-material/PersonOutline';
import { ExcelIcon, PdfIcon, WordIcon } from "../../utils/icons.tsx";
import DocumentIcon from '@mui/icons-material/Description';
import MarkdownIcon from '@mui/icons-material/Code'; // You can choose a more appropriate icon
import { pdfjs } from 'react-pdf';
import MarkdownViewer from '../../utils/markdownRenderer.tsx'; // Import the markdown viewer component

// Configuration for react-pdf
pdfjs.GlobalWorkerOptions.workerSrc = `//cdnjs.cloudflare.com/ajax/libs/pdf.js/${pdfjs.version}/pdf.worker.min.js`;

interface DocumentViewerProps {
  document: any;
  open: boolean;
  onClose: () => void;
  loading: boolean;
}

const getIcon = (fileName?: string) => {
  if (!fileName) return <DocumentIcon />;
  const fileType = fileName.split('.').pop()?.toLowerCase();
  switch (fileType) {
    case 'pdf':
      return <PdfIcon sx={{ mr: 1 }} />;
    case 'docx':
    case 'doc':
      return <WordIcon sx={{ mr: 1 }} />;
    case 'xlsx':
    case 'xls':
      return <ExcelIcon sx={{ mr: 1 }} />;
    case 'md':
    case 'markdown':
      return <MarkdownIcon sx={{ mr: 1 }} />; // Add markdown icon
    default:
      return <DocumentIcon sx={{ mr: 1 }} />;
  }
};

export const DocumentViewer: React.FC<DocumentViewerProps> = ({ 
  document, 
  open, 
  onClose, 
  loading 
}) => {
  const [docContent, setDocContent] = useState<string>('');
  const [isLoadingDoc, setIsLoadingDoc] = useState<boolean>(false);
  const [loadError, setLoadError] = useState<string | null>(null);

  // Download document
  const downloadDocument = () => {
    if (document?.file_url) {
      try {
        const downloadLink = window.document.createElement('a');
        downloadLink.href = document.file_url;
        downloadLink.setAttribute('download', document.file_name || "document");
        downloadLink.setAttribute('target', '_blank');
        document.body.appendChild(downloadLink);
        downloadLink.click();
        document.body.removeChild(downloadLink);
      } catch (error) {
        console.error('Download error:', error);
        // Fallback - open in new tab if download fails
        window.open(document.file_url, '_blank');
      }
    }
  };

  // Load document content based on type
  useEffect(() => {
    if (!document || !open) return;

    const fileType = document.file_name?.split('.').pop()?.toLowerCase();
    
    // Handle Markdown files
    if (['md', 'markdown'].includes(fileType)) {
      const loadMarkdownDocument = async () => {
        try {
          setIsLoadingDoc(true);
          setLoadError(null);

          // If we have content as a string
          if (typeof document.content === 'string' && document.content.length > 0) {
            try {
              console.log(document)
              // Try to decode base64 to text
              const decodedText = atob(document.content);
              setDocContent(decodedText);
            } catch (error) {
              // If Base64 decoding fails, assume it's already plain text
              console.log("Base64 decoding failed, using content as plain text");
              setDocContent(document.content);
            }
          }
          // Otherwise, try to load from URL
          else if (document.file_url) {
            try {
              const response = await fetch(document.file_url);
              if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
              const text = await response.text();
              setDocContent(text);
            } catch (error) {
              throw new Error(`Download error: ${error.message}`);
            }
          }
          else {
            throw new Error("No content or URL available");
          }
        } catch (error) {
          console.error("Error loading markdown document:", error);
          setLoadError(error.message);
        } finally {
          setIsLoadingDoc(false);
        }
      };

      loadMarkdownDocument();
    }
  }, [document, open]);

  // Clean state when closing
  useEffect(() => {
    if (!open) {
      setDocContent('');
      setLoadError(null);
    }
  }, [open]);

  // Render document content based on type
  const renderDocumentContent = () => {
    if (!document) return null;

    // Ensure filename exists
    if (!document.file_name) {
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: 'calc(100vh - 180px)' }}>
          <Typography variant="h6">Unable to load document</Typography>
        </Box>
      );
    }

    const fileType = document.file_name.split('.').pop()?.toLowerCase();

    // Handle different document types
    switch (fileType) {
      case 'pdf': 
      case 'xlsx':
      case 'xls': 

      case 'docx':
      case 'doc':
        return <div>  </div>
      // New case for Markdown files
      case 'md':
      case 'markdown':
        return (
          <Box sx={{ display: 'flex', flexDirection: 'column', height: '98%' }}>
            {isLoadingDoc ? (
              <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
                <CircularProgress />
              </Box>
            ) : loadError ? (
              <Box sx={{ textAlign: 'center', p: 3 }}>
                <Typography variant="h6" color="error" gutterBottom>
                  Error loading markdown document
                </Typography>
                <Typography variant="body1">
                  {loadError}
                </Typography>
                <Button
                  variant="contained"
                  color="primary"
                  sx={{ mt: 2 }}
                  onClick={() => document.file_url && window.open(document.file_url, '_blank')}
                >
                  Try opening in a new tab
                </Button>
              </Box>
            ) : docContent ? (
              <MarkdownViewer markdown={docContent} /> // Use our MarkdownViewer component
            ) : (
              <Box sx={{ textAlign: 'center', p: 3 }}>
                <Typography variant="body1">
                  Unable to load markdown content.
                </Typography>
              </Box>
            )}
          </Box>
        );
        
      default:
        // For text files or other types
        if (typeof document.content === 'string' && document.content.length > 0) {
          // Try to decode base64 content
          try {
            const binary = atob(document.content);
            return (
              <Box sx={{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', p: 3, bgcolor: 'background.paper', borderRadius: 1 }}>
                <Typography variant="body1">
                  {binary.split('\n\n').map((paragraph, index) => (
                    <p key={index}>{paragraph}</p>
                  ))}
                </Typography>
              </Box>
            );
          } catch (error) {
            console.error("Error decoding base64:", error);
            // If Base64 decoding fails, just show the content as is
            return (
              <Box sx={{ maxHeight: 'calc(100vh - 180px)', overflowY: 'auto', p: 3, bgcolor: 'background.paper', borderRadius: 1 }}>
                <Typography variant="body1">
                  {document.content.split('\n\n').map((paragraph, index) => (
                    <p key={index}>{paragraph}</p>
                  ))}
                </Typography>
              </Box>
            );
          }
        } else if (document.file_url) {
          return (
            <Box sx={{ height: 'calc(100vh - 180px)' }}>
              <iframe
                src={document.file_url}
                width="100%"
                height="100%"
                style={{ border: 'none' }}
                title={document.file_name}
              />
            </Box>
          );
        } else {
          return (
            <Typography variant="body1" sx={{ p: 2 }}>
              The content of this document is not available.
            </Typography>
          );
        }
    }
  };

  return (
    <Drawer
      anchor="right"
      open={open}
      onClose={onClose}
      ModalProps={{
        BackdropComponent: Backdrop,
        BackdropProps: {
          open: open,
        }
      }}
      sx={{ zIndex: (theme) => theme.zIndex.drawer + 2 }}
    >
      <Box sx={{ width: '80vw', height: '100vh', display: 'flex', flexDirection: 'column' }}>
        {/* AppBar for document header */}
        <AppBar position="static" color="default" elevation={0} sx={{ borderBottom: '1px solid', borderColor: 'divider' }}>
          <Toolbar>
            <Box sx={{ display: 'flex', alignItems: 'center', flex: 1 }}>
              {document && getIcon(document.file_name)}
              <Typography variant="h6" noWrap component="div">
                {document?.file_name}
              </Typography>
              {document?.agent_name && (
                <Chip 
                  label={document.agent_name} 
                  size="small" 
                  color="primary" 
                  sx={{ ml: 2 }}
                  icon={<PersonOutlineIcon />} 
                />
              )}
            </Box>
            
            {/* Actions */}
            <Box sx={{ display: 'flex', gap: 1 }}>
              {document?.file_url && (
                <>
                  <Button 
                    startIcon={<DownloadIcon />} 
                    onClick={downloadDocument}
                    size="small"
                    variant="outlined"
                  >
                    Download
                  </Button>
                  <Button 
                    startIcon={<OpenInNewIcon />} 
                    onClick={() => window.open(document.file_url, '_blank')}
                    size="small"
                    variant="outlined"
                  >
                    Open
                  </Button>
                </>
              )}
              <IconButton onClick={onClose}>
                <CloseIcon />
              </IconButton>
            </Box>
          </Toolbar>
        </AppBar>
        
        {/* Document content */}
        <Box sx={{ flex: 1, overflow: 'hidden', position: 'relative' }}>
          {loading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', height: '100%' }}>
              <CircularProgress />
            </Box>
          ) : (
            renderDocumentContent()
          )}
        </Box>
      </Box>
    </Drawer>
  );
};

export default DocumentViewer;