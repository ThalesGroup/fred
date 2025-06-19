import React from 'react';
import {
    Card, Typography, useTheme, Stack, Box, Chip,
    Divider, IconButton, Tooltip, Fade, alpha, LinearProgress
} from "@mui/material";
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/Delete';
import DocumentScannerIcon from '@mui/icons-material/DocumentScanner';
import { ChatProfile } from '../pages/ChatProfiles';

interface CustomProfileProps {
    chatProfile: ChatProfile;
    index: number;
    onEdit: (chatProfile: ChatProfile) => void;
    onDelete: (chatProfile: ChatProfile) => void;
    getFileIcon: (fileType: string) => React.ReactNode;
    formatFileSize: (bytes: number) => string;
    maxTokens?: number;
}

export const CustomProfile: React.FC<CustomProfileProps> = ({
    chatProfile,
    index,
    onEdit,
    onDelete,
    getFileIcon,
    formatFileSize,
    maxTokens,
}) => {
    const theme = useTheme();
    const tokensUsed = chatProfile.tokens ?? 0;
    const percentageUsed = Math.min((tokensUsed / maxTokens) * 100, 100);

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

                <Box sx={{ p: 3, pb: 2, position: 'relative', zIndex: 1 }}>
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

                {chatProfile.documents.length > 0 && (
                    <Box sx={{ px: 3, pb: 2 }}>
                        <Stack spacing={0.8}>
                            {chatProfile.documents.slice(0, 3).map((doc) => (
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
                                                fontSize: '0.75rem',
                                                maxWidth: '100%',
                                            }}
                                        >
                                            {doc.document_name}
                                        </Typography>
                                    </Box>
                                </Box>
                            ))}
                            {chatProfile.documents.length > 3 && (
                                <Typography
                                    variant="caption"
                                    color="text.secondary"
                                    sx={{
                                        fontSize: '0.75rem',
                                        fontStyle: 'italic',
                                        pl: 1,
                                    }}
                                >
                                    📁 +{chatProfile.documents.length - 3} more
                                </Typography>
                            )}
                        </Stack>
                    </Box>
                )}

                <Divider sx={{ mx: 3 }} />

                <Box sx={{ p: 3, pt: 2, flexGrow: 1, display: 'flex', flexDirection: 'column' }}>
                    <Stack spacing={1}>
                        <Typography
                            variant="caption"
                            color={tokensUsed >= maxTokens ? 'error.main' : 'text.secondary'}
                        >
                            🪙 Tokens: {tokensUsed?.toLocaleString()} / {maxTokens?.toLocaleString()}
                        </Typography>
                        <LinearProgress
                            variant="determinate"
                            value={percentageUsed}
                            sx={{
                                height: 6,
                                borderRadius: 5,
                                backgroundColor: alpha(theme.palette.grey[300], 0.4),
                                '& .MuiLinearProgress-bar': {
                                    backgroundColor:
                                        percentageUsed >= 100
                                            ? theme.palette.error.main
                                            : theme.palette.primary.main,
                                },
                            }}
                        />
                        <Typography
                            variant="caption"
                            color="text.secondary"
                            sx={{ fontSize: '0.75rem' }}
                        >
                            📅 {new Date(chatProfile.updated_at).toLocaleDateString('fr-FR', {
                                day: 'numeric',
                                month: 'short',
                                year: 'numeric'
                            })}
                        </Typography>
                    </Stack>

                    <Box
                        className="chatProfile-actions"
                        sx={{
                            mt: 2,
                            display: 'flex',
                            justifyContent: 'flex-end',
                            gap: 1,
                            opacity: 0,
                            transform: 'translateY(8px)',
                            transition: 'all 0.3s ease',
                        }}
                    >
                        <Tooltip title="Edit">
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
                                }}
                            >
                                <EditIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                        <Tooltip title="Delete">
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
                                }}
                            >
                                <DeleteIcon fontSize="small" />
                            </IconButton>
                        </Tooltip>
                    </Box>
                </Box>
            </Card>
        </Fade>
    );
};
