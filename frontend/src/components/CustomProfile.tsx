import React from 'react';
import {
    Card,
    CardContent,
    Typography,
    useTheme,
    Stack,
    Box,
    Chip,
    Divider,
    IconButton,
    Tooltip,
    Fade,
    alpha
} from "@mui/material";
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import { ChatProfile, ChatProfileDocument } from '../pages/ChatProfiles';

interface CustomProfileProps {
    chatProfile: ChatProfile;
    index: number;
    onEdit: (chatProfile: ChatProfile) => void;
    onDelete: (chatProfile: ChatProfile) => void;
    getFileIcon: (fileType: string) => React.ReactNode;
    formatFileSize: (bytes: number) => string;
}

export const CustomProfile: React.FC<CustomProfileProps> = ({
    chatProfile,
    index,
    onEdit,
    onDelete,
    getFileIcon,
    formatFileSize
}) => {
    const theme = useTheme();

    console.log(chatProfile)
    return (
        <Fade in={true} timeout={1600 + index * 200}>
            <Card
                sx={{
                    height: '100%',
                    display: 'flex',
                    flexDirection: 'column',
                    borderRadius: 4,
                    border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                    backgroundColor: alpha(theme.palette.background.paper, 0.8),
                    backdropFilter: 'blur(10px)',
                    boxShadow: `0 4px 20px ${alpha(theme.palette.common.black, 0.1)}`,
                    transition: 'all 0.4s cubic-bezier(0.4, 0, 0.2, 1)',
                    overflow: 'hidden',
                    position: 'relative',
                    '&:hover': {
                        transform: 'translateY(-2px)',
                        boxShadow: `0 20px 40px ${alpha(theme.palette.common.black, 0.15)}`,
                        '& .chatProfile-actions': {
                            opacity: 1,
                            transform: 'translateY(0)',
                        },
                        '& .chatProfile-gradient': {
                            opacity: 0.1,
                        }
                    }
                }}
            >
                {/* Background Gradient */}
                <Box
                    className="chatProfile-gradient"
                    sx={{
                        position: 'absolute',
                        top: 0,
                        left: 0,
                        right: 0,
                        height: '100%',
                        background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.05)} 0%, ${alpha(theme.palette.secondary.main, 0.05)} 100%)`,
                        opacity: 0,
                        transition: 'opacity 0.4s ease',
                    }}
                />

                {/* Header with document count */}
                <Box
                    sx={{
                        p: 3,
                        pb: 2,
                        position: 'relative',
                        zIndex: 1,
                    }}
                >
                    <Stack direction="row" justifyContent="space-between" alignItems="flex-start" spacing={2}>
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography
                                variant="h6"
                                fontWeight={600}
                                sx={{
                                    mb: 1,
                                    overflow: 'hidden',
                                    textOverflow: 'ellipsis',
                                    whiteSpace: 'nowrap',
                                }}
                            >
                                {chatProfile.title}
                            </Typography>
                            <Typography
                                variant="body2"
                                color="text.secondary"
                                sx={{
                                    display: '-webkit-box',
                                    WebkitLineClamp: 2,
                                    WebkitBoxOrient: 'vertical',
                                    overflow: 'hidden',
                                    lineHeight: 1.5,
                                    minHeight: '3em',
                                }}
                            >
                                {chatProfile.description || "Aucune description"}
                            </Typography>
                        </Box>

                        <Chip
                            icon={<DocumentScannerIcon fontSize="small" />}
                            label={chatProfile.documents.length}
                            size="small"
                            sx={{
                                background: `linear-gradient(135deg, ${alpha(theme.palette.primary.main, 0.1)} 0%, ${alpha(theme.palette.primary.main, 0.2)} 100%)`,
                                border: `1px solid ${alpha(theme.palette.primary.main, 0.2)}`,
                                color: theme.palette.primary.main,
                                fontWeight: 600,
                            }}
                        />
                    </Stack>
                </Box>

                {/* Compact Documents Section */}
                {chatProfile.documents.length > 0 && (
                    <Box sx={{ px: 3, pb: 2 }}>
                        <Stack spacing={0.8}>
                            {/* Show up to 3 documents */}
                            {chatProfile.documents.slice(0, 3).map((doc, docIndex) => (
                                <Box
                                    key={doc.id}
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 1,
                                        p: 1,
                                        borderRadius: 2,
                                        backgroundColor: alpha(theme.palette.background.default, 0.3),
                                        border: `1px solid ${alpha(theme.palette.divider, 0.1)}`,
                                        transition: 'all 0.2s ease',
                                        '&:hover': {
                                            backgroundColor: alpha(theme.palette.background.default, 0.5),
                                        }
                                    }}
                                >
                                    {getFileIcon(doc.document_type)}
                                    <Box sx={{ flex: 1, minWidth: 0 }}>
                                        <Typography
                                            variant="caption"
                                            fontWeight={500}
                                            sx={{
                                                overflow: 'hidden',
                                                textOverflow: 'ellipsis',
                                                whiteSpace: 'nowrap',
                                                display: 'block',
                                                fontSize: '0.75rem',
                                            }}
                                        >
                                            {doc.document_name}
                                        </Typography>
                                    </Box>
                                </Box>
                            ))}
                            
                            {/* Show count for remaining documents if more than 3 */}
                            {chatProfile.documents.length > 3 && (
                                <Box
                                    sx={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: 1,
                                        pl: 1,
                                        pt: 0.5,
                                    }}
                                >
                                    <Typography 
                                        variant="caption" 
                                        color="text.secondary" 
                                        sx={{ 
                                            fontSize: '0.75rem',
                                            fontStyle: 'italic',
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: 0.5,
                                        }}
                                    >
                                        📁 +{chatProfile.documents.length - 3} more
                                    </Typography>
                                </Box>
                            )}
                        </Stack>
                    </Box>
                )}

                <Divider sx={{ mx: 3 }} />

                {/* Footer with emojis */}
                <Box sx={{ p: 3, pt: 2 }}>
                    <Stack direction="row" justifyContent="space-between" alignItems="center">
                        <Box>
                            <Typography 
                                variant="caption" 
                                color="text.secondary"
                                sx={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 0.5,
                                    fontSize: '0.75rem',
                                }}
                            >
                                🪙 <Typography>{(chatProfile.tokens ?? 0).toLocaleString()}</Typography> tokens
                            </Typography>
                            <Typography 
                                variant="caption" 
                                color="text.secondary" 
                                sx={{ 
                                    display: 'flex',
                                    alignItems: 'center',
                                    gap: 0.5,
                                    fontSize: '0.75rem',
                                    mt: 0.3,
                                }}
                            >
                                📅 {new Date(chatProfile.updated_at).toLocaleDateString('fr-FR', {
                                    day: 'numeric',
                                    month: 'short',
                                    year: 'numeric'
                                })}
                            </Typography>
                        </Box>

                        {/* Actions with emoji tooltips */}
                        <Stack
                            direction="row"
                            spacing={1}
                            className="chatProfile-actions"
                            sx={{
                                opacity: 0,
                                transform: 'translateY(8px)',
                                transition: 'all 0.3s ease',
                            }}
                        >
                            <Tooltip title="Modifier">
                                <IconButton
                                    size="small"
                                    onClick={() => onEdit(chatProfile)}
                                    sx={{
                                        backgroundColor: alpha(theme.palette.primary.main, 0.1),
                                        color: theme.palette.primary.main,
                                        '&:hover': {
                                            backgroundColor: alpha(theme.palette.primary.main, 0.2),
                                            transform: 'scale(1.05)',
                                        },
                                        transition: 'all 0.2s ease',
                                    }}
                                >
                                    <EditIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                            <Tooltip title="Supprimer">
                                <IconButton
                                    size="small"
                                    onClick={() => onDelete(chatProfile)}
                                    sx={{
                                        backgroundColor: alpha(theme.palette.error.main, 0.1),
                                        color: theme.palette.error.main,
                                        '&:hover': {
                                            backgroundColor: alpha(theme.palette.error.main, 0.2),
                                            transform: 'scale(1.05)',
                                        },
                                        transition: 'all 0.2s ease',
                                    }}
                                >
                                    <DeleteIcon fontSize="small" />
                                </IconButton>
                            </Tooltip>
                        </Stack>
                    </Stack>
                </Box>
            </Card>
        </Fade>
    );
};