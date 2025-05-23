// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Box, Grid2, IconButton, Tooltip, Chip } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import ContentCopyIcon from '@mui/icons-material/ContentCopy';
import { useState } from "react";
import ThumbUpIcon from '@mui/icons-material/ThumbUp';
import ThumbDownIcon from '@mui/icons-material/ThumbDown';
import VolumeUpIcon from '@mui/icons-material/VolumeUp';
import ClearIcon from "@mui/icons-material/Clear";
import { usePostSpeechTextMutation } from "../../frugalit/slices/api.tsx";
import { AgenticFlow } from "../../pages/Chat.tsx";
import { getAgentBadge } from "../../utils/avatar.tsx";
import { FeedbackDialog } from "../../frugalit/component/FeedbackDialog.tsx";
import { useToast } from "../ToastProvider.tsx";
import { extractHttpErrorMessage } from "../../utils/extractHttpErrorMessage.tsx";
import { usePostFeedbackMutation } from "../../slices/chatApi.tsx";
import { ChatMessagePayload } from "../../slices/chatApiStructures.ts";
import MarkdownRenderer from "../markdown/MarkdownRenderer.tsx";

export default function Message(
    {
        message,
        agenticFlow,
        side,
        enableCopy = false,
        enableThumbs = false,
        enableAudio = false
    }: {
        message: ChatMessagePayload
        agenticFlow: AgenticFlow
        side: string,
        enableCopy?: boolean,
        enableThumbs?: boolean,
        enableAudio?: boolean
    }) {

    const theme = useTheme();
    const { showError, showInfo } = useToast(); // Use the toast hook

    const [postSpeechText] = usePostSpeechTextMutation();
    const [postFeedback] = usePostFeedbackMutation();

    const [audioToSpeech, setAudioToSpeech] = useState<HTMLAudioElement>(null);
    const [feedbackOpen, setFeedbackOpen] = useState(false);
    const [feedbackType, setFeedbackType] = useState<'up' | 'down'>('up');
    const handleFeedbackSubmit = (rating: number, reason: string) => {
        postFeedback({ rating, reason, feedbackType }).then((result) => {
            if (result.error) {
                showError({
                    summary: 'Error submitting feedback',
                    detail: extractHttpErrorMessage(result.error)
                });
                console.error("Failed to submit feedback:", result.error);
            } else {
                showInfo({
                    summary: 'Feedback submitted',
                    detail: 'Thank you for your feedback!'
                });
                console.log("Feedback submitted successfully:", result.data);
            }
        });
        setFeedbackOpen(false);
    };

    // Function to start speaking the message content
    const handleStartSpeaking = (message: string) => {
        postSpeechText(message).then((response) => {
            if (response.data) {
                const audioBlob = response.data as Blob;
                const audioUrl = URL.createObjectURL(audioBlob);
                const audioToSpeech = new Audio(audioUrl);
                setAudioToSpeech(audioToSpeech);
                audioToSpeech.play().then(() => {
                    // Stop the audio after it finishes playing
                    audioToSpeech.onended = () => {
                        setAudioToSpeech(null);
                    };
                }).catch((error) => {
                    console.error("Failed to play audio:", error);
                });
            } else {
                console.error("No audio data in response");
            }
        });
    };

    // Function to stop the audio from playing
    const handleStopSpeaking = () => {
        // Stop the audio
        if (audioToSpeech) {
            audioToSpeech.pause();
            setAudioToSpeech(null);
        }

    }

    // Function to copy the message content to the clipboard
    const copyToClipboard = (text: string) => {
        navigator.clipboard.writeText(text).then(() => {
            console.log("Copied to clipboard");
        });
    }
    return (
        <>
            <Grid2 container marginBottom={1}>
                {/* Display the avatar for message on the right side */}
                {side === "left" && agenticFlow &&
                    <Grid2 size="auto" paddingTop={2}>
                        <Tooltip title={`${agenticFlow.nickname}: ${agenticFlow.role}`}>
                            <Box sx={{ mr: 2, mb: 2 }}>
                                {getAgentBadge(agenticFlow.nickname)}
                            </Box>
                        </Tooltip>
                    </Grid2>}
                <Grid2 container size="grow" display="flex" justifyContent={side}>
                    {/* Display the event content only if it is not null */}
                    {message && <>
                        <Grid2>
                            <Box
                                sx={{
                                    display: "flex",
                                    flexDirection: "column",
                                    backgroundColor: side === 'right' ? theme.palette.background.paper : theme.palette.background.default,
                                    paddingTop: "0.8em", // TODO rewrite MarkdownRenderer or adjust css to remove this
                                    paddingLeft: side === 'right' ? 2 : 0,
                                    paddingRight: side === 'right' ? 2 : 0,
                                    marginTop: side === 'right' ? 1 : 0,
                                    borderRadius: 3,
                                    wordBreak: 'break-word',
                                }}>
                                <MarkdownRenderer
                                    content={message.content as string}
                                    size="large"
                                    enableEmojiSubstitution={side === "left"} // only apply for assistant replies
                                />
                            </Box>
                        </Grid2>
                        {side === "left" ?
                            <Grid2 size={12} height="30px" display="flex" alignItems="center">
                                {enableCopy &&
                                    <IconButton aria-label="delete" size="small"
                                        onClick={() => copyToClipboard(message.content as string)}>
                                        <ContentCopyIcon fontSize="medium" color="inherit" />
                                    </IconButton>
                                }
                                {enableThumbs && <>
                                    <IconButton aria-label="thumb up" size="small" onClick={() => {
                                        setFeedbackType('up');
                                        setFeedbackOpen(true);
                                    }}>
                                        <ThumbUpIcon fontSize="medium" color="inherit" />
                                    </IconButton>
                                    <IconButton aria-label="thumb down" size="small" onClick={() => {
                                        setFeedbackType('down');
                                        setFeedbackOpen(true);
                                    }}>
                                        <ThumbDownIcon fontSize="medium" color="inherit" />
                                    </IconButton>
                                </>
                                }
                                {enableAudio &&
                                    <IconButton
                                        aria-label="up"
                                        size="small"
                                        onClick={() => {
                                            if (audioToSpeech) {
                                                handleStopSpeaking();
                                            } else {
                                                handleStartSpeaking(message.content as string);
                                            }
                                        }}
                                    >
                                        {audioToSpeech ?
                                            <ClearIcon fontSize="medium" color="inherit" /> :
                                            <VolumeUpIcon fontSize="medium" color="inherit" />
                                        }
                                    </IconButton>
                                }
                                <Chip
                                    label="AI content may be incorrect, please double-check responses"
                                    size="small"
                                    variant="outlined"
                                    sx={{
                                        ml: 1.5,
                                        fontSize: '0.7rem',
                                        height: '24px',
                                        borderColor: theme.palette.divider,
                                        color: theme.palette.text.primary,
                                    }}
                                />
                            </Grid2> : <Grid2 height="30px"></Grid2>}
                    </>}
                </Grid2>
            </Grid2>
            <FeedbackDialog
                open={feedbackOpen}
                onClose={() => setFeedbackOpen(false)}
                onSubmit={handleFeedbackSubmit}
                feedbackType={feedbackType}
            />
        </>
    )
}