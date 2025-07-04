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

import Editor from "@monaco-editor/react";
import EmojiObjectsIcon from "@mui/icons-material/EmojiObjects";
import PsychologyAltIcon from "@mui/icons-material/PsychologyAlt";
import WebhookIcon from "@mui/icons-material/Webhook";
import {
  Timeline,
  TimelineConnector,
  TimelineContent,
  TimelineDot,
  TimelineItem,
  timelineItemClasses,
  TimelineSeparator,
} from "@mui/lab";
import { Box, Fade, Grid2, IconButton, Modal, Tooltip, Typography } from "@mui/material";
import { useTheme } from "@mui/material/styles";
import { useState } from "react";
import { ChatMessagePayload } from "../../slices/chatApiStructures.ts";
import FoldableChatSection from "./FoldableChatSection";

export default function Thoughts({
  messages,
  isOpenByDefault = false,
}: {
  messages: Record<string, ChatMessagePayload[]>;
  isOpenByDefault: boolean;
}) {
  const theme = useTheme();

  const [thoughtsDetails, setThoughtsDetails] = useState<string>("");
  const [modalThoughtsDetails, setModalThoughtsDetails] = useState<boolean>(false);
  console.log("Thoughts component received messages:", messages);

  const handleOpenModalThoughtsToolDetails = (messages: ChatMessagePayload[]) => {
    let content = "";
    // Add expert name from the first message
    if (messages.length > 0) {
      const agentic_flow = messages[0].metadata?.fred?.agentic_flow;
      if (agentic_flow) {
        content += `# Responses from ${agentic_flow} \n \n`;
      }
    }
    for (const message of messages) {
      if (message.type == "tool") {
        // Add a markdown block delimiter for each message
        content += message.content + "\n" + "\n";
        // Display tool
      }
    }
    setThoughtsDetails(content);
    setModalThoughtsDetails(true);
  };

  const handleOpenModalThoughtsDetails = (messages: ChatMessagePayload[]) => {
    let content = "";
    // Add expert name from the first message
    if (messages.length > 0) {
      const agentic_flow = messages[0].metadata?.fred?.agentic_flow;
      if (agentic_flow) {
        content += `# Responses from ${agentic_flow} \n \n`;
        content += "---" + "\n";
      }
    }
    for (const message of messages) {
      if (message.type !== "tool") {
        // Add a markdown block delimiter for each message
        content += message.content + "\n" + "\n";
        // Display tool
      } else {
        // In the case of a tool message,
        // format the Markdown content to display the tool name and the tool content
        const toolName = message.metadata?.name || "Tool";
        content += "Tool calling (" + toolName + ")\n" + "\n";
        //TODO <pre> html component is not displayed well
        content += message.content + "\n" + "\n";
      }
      content += "---" + "\n";
    }
    setThoughtsDetails(content);
    setModalThoughtsDetails(true);
  };
  const handleCloseModalThoughtsDetails = () => {
    setModalThoughtsDetails(false);
  };
  return (
    <>
      {Object.keys(messages).length > 0 && (
        <FoldableChatSection title="Thoughts" icon={<EmojiObjectsIcon />} defaultOpen={isOpenByDefault} sx={{ mt: 2 }}>
          <Timeline
            sx={{
              [`& .${timelineItemClasses.root}:before`]: {
                flex: 0,
                padding: 0,
              },
              margin: "0px",
            }}
          >
            {Object.entries(messages).map(([key, msgs], index) => {
              return (
                <TimelineItem
                  key={`thought-${key}-${index}`}
                  // key={index}
                  style={{
                    minHeight: index < Object.keys(messages).length - 1 ? "60px" : "0px",
                  }}
                >
                  <TimelineSeparator>
                    <TimelineDot
                      style={{
                        backgroundColor: theme.palette.primary.main,
                      }}
                    />
                    {index < Object.keys(messages).length - 1 && <TimelineConnector />}
                  </TimelineSeparator>
                  <TimelineContent>
                    <Grid2 container display="flex" flexDirection="row">
                      <Grid2 size={11}>
                        <Typography variant="body2">{key}</Typography>
                      </Grid2>
                      <Grid2
                        size={1}
                        display="flex"
                        flexDirection="row"
                        alignItems="flex-start"
                        justifyContent="center"
                        gap={0}
                      >
                        <Tooltip title={"View the reasoning path"}>
                          <IconButton
                            aria-label="View details"
                            style={{
                              color: theme.palette.primary.main,
                              padding: 0,
                            }}
                            onClick={() => handleOpenModalThoughtsDetails(msgs)}
                          >
                            <PsychologyAltIcon color="primary" sx={{ fontSize: "1.8rem" }} />
                          </IconButton>
                        </Tooltip>
                        {/* Display the tool icon if thoughts include a tool message */}
                        {msgs.filter((thought) => thought.type === "tool").length > 0 && (
                          <Tooltip title={"View the tools used and their results"}>
                            <IconButton
                              aria-label="View tools usage"
                              style={{
                                color: theme.palette.warning.main,
                                padding: 0,
                              }}
                              onClick={() =>
                                handleOpenModalThoughtsToolDetails(msgs.filter((thought) => thought.type === "tool"))
                              }
                            >
                              <WebhookIcon color="primary" sx={{ fontSize: "1.8rem" }} />
                            </IconButton>
                          </Tooltip>
                        )}
                      </Grid2>
                    </Grid2>
                  </TimelineContent>
                </TimelineItem>
              );
            })}
          </Timeline>
        </FoldableChatSection>
      )}

      <Modal open={modalThoughtsDetails} onClose={handleCloseModalThoughtsDetails}>
        <Fade in={modalThoughtsDetails} timeout={100}>
          <Box
            sx={{
              position: "absolute",
              top: "50%",
              left: { xs: "calc(50% + 40px)", md: "calc(50% + 80px)" },
              transform: "translate(-50%, -50%)",
              width: {
                xs: "calc(100% - 140px)",
                md: "calc(80% - 140px)",
                lg: "calc(55% - 140px)",
              },
              maxHeight: "80vh",
              bgcolor: "background.paper",
              color: "text.primary",
              borderRadius: 3,
              p: 4,
              display: "flex",
              flexDirection: "column",
              scrollBehavior: "smooth",
              scrollbarWidth: "10px",
              boxShadow: 48, // Adds MUI elevation
              overflowY: "auto",
            }}
          >
            {thoughtsDetails && (
              <Editor
                theme={theme.palette.mode === "dark" ? "vs-dark" : "vs"}
                height="100vh"
                defaultLanguage="json"
                options={{ readOnly: true }}
                defaultValue={thoughtsDetails}
              />
            )}
          </Box>
        </Fade>
      </Modal>
    </>
  );
}
