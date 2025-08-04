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

// User input component for the chatbot
import { Badge, Grid2, IconButton, InputBase, Tooltip, useTheme } from "@mui/material";
import ArrowUpwardIcon from "@mui/icons-material/ArrowUpward";
import AttachFileIcon from "@mui/icons-material/AttachFile";
import MicIcon from "@mui/icons-material/Mic";
import React, { useRef, useState } from "react";
import AudioRecorder from "./AudioRecorder.tsx";
import StopIcon from "@mui/icons-material/Stop";
import AudioController from "./AudioController.tsx";
import VisibilityOffIcon from "@mui/icons-material/VisibilityOff";
import Chip from "@mui/material/Chip";
import { ChatLibrariesSelection } from "./ChatLibrariesSelection";

export interface UserInputContent {
  text?: string;
  audio?: Blob;
  files?: File[];
}

export default function UserInput({
  enableFilesAttachment = false,
  enableAudioAttachment = false,
  isWaiting = false,
  onSend = () => {},
}: {
  enableFilesAttachment: boolean;
  enableAudioAttachment: boolean;
  isWaiting: boolean;
  onSend: (content: UserInputContent) => void;
}) {
  const theme = useTheme();
  const fileInputRef = useRef<HTMLInputElement>(null);

  // Focus on send button
  const sendRef = useRef<HTMLInputElement>(null);

  // State for recording audio
  const [displayAudioRecorder, setDisplayAudioRecorder] = useState<boolean>(false);
  const [displayAudioController, setDisplayAudioController] = useState<boolean>(false);
  const [isRecording, setIsRecording] = useState<boolean>(false);

  const [userInput, setUserInput] = useState<string>("");
  const [audioBlob, setAudioBlob] = useState<Blob | null>(null);
  const [filesBlob, setFilesBlob] = useState<File[] | null>(null);
  const [selectedDocumentLibrariesIds, setSelectedDocumentLibrariesIds] = useState<string[]>([]);
  const [selectedPromptLibrariesIds, setSelectedPromptLibrariesIds] = useState<string[]>([]);

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Enter") {
      if (event.shiftKey) {
        // Shift + Enter: Add new line
        setUserInput((prev) => prev + "\n");
        event.preventDefault();
      } else {
        // Enter: Submit the input
        event.preventDefault();
        handleSend();
      }
    }
  };

  // Handle sending the user input which can be text, audio or file
  const handleSend = () => {
    // Here we send the user input, audio and file to the parent component
    console.log("Text user input : ", userInput);
    console.log("Audio blob : ", audioBlob);
    console.log("Files blob : ", filesBlob);
    onSend({
      text: userInput,
      audio: audioBlob,
      files: filesBlob,
    });
    setUserInput("");
    setAudioBlob(null);
    setFilesBlob(null);
  };

  // Handle file selection
  const handleFilesChange = (event: React.ChangeEvent<HTMLInputElement>) => {
    // Add the selected files to previous files
    if (event.target.files) {
      setFilesBlob((prev) => {
        let newFiles = prev ? [...prev] : [];
        for (let i = 0; i < event.target.files.length; i++) {
          newFiles.push(event.target.files[i]);
        }
        return newFiles;
      });
    }
  };

  const handleAudioRecorderDisplay = () => {
    setIsRecording(!isRecording);
    setDisplayAudioRecorder(true);
    // Focus on the send button after starting the recording
    sendRef ? sendRef.current.focus() : console.error("Send ref is null");
  };

  const handleAudioChange = (content: Blob) => {
    setIsRecording(false);
    setDisplayAudioRecorder(false);
    setAudioBlob(content);
    // Focus on the send button after stopping the recording
    sendRef ? sendRef.current.focus() : console.error("Send ref is null");
  };

  const handleRemoveFile = (index: number) => {
    setFilesBlob((prev) => {
      let newFiles = prev ? [...prev] : [];
      newFiles.splice(index, 1);
      return newFiles;
    });
  };
  return (
    <Grid2
      container
      sx={{
        height: "100%", // Ensure it takes full available height
        justifyContent: "flex-end", // Align input section to the bottom
        overflow: "hidden",
      }}
      size={12}
      display="flex"
    >
      {/* Display the attachments popover */}
      {((filesBlob && filesBlob.length > 0) || audioBlob) && (
        <Grid2
          container
          size={12}
          height="40px"
          overflow="auto"
          paddingBottom={1}
          display="flex"
          justifyContent="center"
          gap={1}
        >
          {filesBlob &&
            filesBlob.map((f, i) => {
              return (
                <Grid2 size="auto">
                  <Chip
                    label={(f as File).name.replace(/\.[^/.]+$/, "")}
                    color="primary"
                    variant="outlined"
                    sx={{
                      height: "32px", // Increase the height
                      fontSize: "1.0rem", // Adjust the font size
                    }}
                    onDelete={() => {
                      handleRemoveFile(i);
                    }}
                  />
                </Grid2>
              );
            })}
          {audioBlob && (
            <Chip
              label="Audio record"
              color="error"
              variant="outlined"
              sx={{
                height: "32px", // Increase the height
                fontSize: "1.0rem", // Adjust the font size
              }}
              onClick={() => setDisplayAudioController(true)}
              onDelete={() => {
                setAudioBlob(null);
              }}
            />
          )}
        </Grid2>
      )}

      <Grid2
        container
        size={12}
        alignItems="center"
        sx={{
          backgroundColor: theme.palette.background.paper,
          borderRadius: 4,
          padding: "12px",
          gap: "8px",
        }}
      >
        {/* User Input Section */}
        <Grid2
          container
          size={12} // Take full width
          sx={{
            display: "flex",
            flexDirection: "column",
            gap: "8px", // the space between the buttons attach file recording etc..
          }}
        >
          {/* First the Input Text Area. It is at the top */}
          <Grid2 size={12}>
            {displayAudioRecorder ? (
              // Display the AudioRecorder if recording is in progress
              <AudioRecorder
                height="40px"
                width="100%"
                waveWidth={1}
                color={theme.palette.text.primary}
                isRecording={isRecording}
                onRecordingComplete={(blob: Blob) => {
                  handleAudioChange(blob); // Handle recorded audio
                  setDisplayAudioRecorder(false); // Stop displaying the recorder
                  setDisplayAudioController(true); // Display the controller instead
                }}
                downloadOnSavePress={false}
                downloadFileExtension="mp3"
              />
            ) : audioBlob && displayAudioController ? (
              // Display the AudioController if audio has been recorded
              <>
                <AudioController audioUrl={URL.createObjectURL(audioBlob)} color={theme.palette.text.primary} />
                <Tooltip title="Hide audio controller">
                  <IconButton aria-label="hide-audio" onClick={() => setDisplayAudioController(false)}>
                    <VisibilityOffIcon />
                  </IconButton>
                </Tooltip>
              </>
            ) : (
              // Default InputBase if no recording or audio is displayed
              <InputBase
                fullWidth={true}
                multiline={true}
                maxRows={30}
                id="user-input"
                placeholder="Enter your question here..."
                value={userInput}
                onKeyDown={(event) => handleKeyDown(event)}
                onChange={(event) => setUserInput(event.target.value)}
                sx={{
                  fontSize: "1rem",
                  padding: "12px",
                  width: "100%",
                  maxHeight: "600px",
                  overflow: "auto", // Scrollbar appears when content exceeds maxHeight
                }}
              />
            )}
          </Grid2>

          {/* Next the Buttons Area with on the left the attach and audio and t-on the right the attach */}
          <Grid2
            container
            alignItems="center"
            justifyContent="space-between" // Spread items across the row
            sx={{ width: "100%", marginTop: "4px" }}
          >
            {/* Left Buttons: Attach File */}
            <Grid2 display="flex" gap={1}>
              {/* Attach File Button */}
              {enableFilesAttachment && (
                <Tooltip title="Attach file(s) to the current conversation">
                  <Badge badgeContent={filesBlob ? filesBlob.length : 0} color="primary">
                    <IconButton sx={{ fontSize: "1.6rem", padding: "8px" }} aria-label="attach" component="label">
                      <input type="file" hidden multiple onChange={handleFilesChange} />
                      <AttachFileIcon fontSize="inherit" />
                    </IconButton>
                    <input
                      type="file"
                      style={{ display: "none" }}
                      multiple
                      onChange={(e) => {
                        if (e.target.files) {
                          setFilesBlob((prev) => {
                            const existing = prev ?? [];
                            return [...existing, ...Array.from(e.target.files)];
                          });
                          e.target.value = ""; // reset input so selecting same file again will re-trigger change
                        }
                      }}
                      ref={fileInputRef}
                    />
                  </Badge>
                </Tooltip>
              )}

              {/* Chat Libraries Selection */}
              <ChatLibrariesSelection
                selectedLibrariesIds={selectedDocumentLibrariesIds}
                setSelectedLibrariesIds={setSelectedDocumentLibrariesIds}
                libraryType="document" 
              />
              {/* Chat Libraries Selection */}
              <ChatLibrariesSelection
                selectedLibrariesIds={selectedPromptLibrariesIds}
                setSelectedLibrariesIds={setSelectedPromptLibrariesIds}
                libraryType="prompt" 
              />

              {/* Audio Record Button */}
              {enableAudioAttachment && (
                <Tooltip title={isRecording ? "Stop your recording to submit it" : "Record your question"}>
                  <Badge badgeContent={audioBlob ? 1 : 0} color="primary">
                    <IconButton
                      sx={{ fontSize: "1.6rem", padding: "8px" }}
                      aria-label="record"
                      onClick={handleAudioRecorderDisplay}
                    >
                      {isRecording ? <StopIcon fontSize="inherit" /> : <MicIcon fontSize="inherit" />}
                    </IconButton>
                  </Badge>
                </Tooltip>
              )}
            </Grid2>
            <Grid2 size="auto" ref={sendRef}>
              {isWaiting || (!userInput && !audioBlob && !filesBlob) ? (
                <Badge color="primary" variant="dot" invisible>
                  <IconButton
                    sx={{ fontSize: "1.6rem", padding: "8px" }}
                    aria-label="send"
                    disabled={isWaiting || (!userInput && !audioBlob && !filesBlob)}
                    onClick={handleSend}
                  >
                    <ArrowUpwardIcon fontSize="inherit" />
                  </IconButton>
                </Badge>
              ) : (
                <Tooltip title="Submit your question">
                  <Badge color="primary" variant="dot" invisible>
                    <IconButton
                      sx={{ fontSize: "1.6rem", padding: "8px" }}
                      aria-label="send"
                      disabled={isWaiting || (!userInput && !audioBlob && !filesBlob)}
                      onClick={handleSend}
                    >
                      <ArrowUpwardIcon fontSize="inherit" />
                    </IconButton>
                  </Badge>
                </Tooltip>
              )}
            </Grid2>
          </Grid2>
        </Grid2>
      </Grid2>
    </Grid2>
  );
}
