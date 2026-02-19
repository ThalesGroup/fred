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

import React, { createContext, useContext, useState } from "react";
import ContentCopyIcon from "@mui/icons-material/ContentCopy";
import { Snackbar, Alert, AlertColor, Box, Typography, Link, IconButton, Tooltip } from "@mui/material";

// Define the structure for the toast message with summary and detail
interface ToastMessage {
  severity: AlertColor;
  summary: string;
  detail: string;
  duration?: number | null;
  id: number;
}

const renderDetailLines = (detail: string) => {
  const urlRegex = /(https?:\/\/[^\s]+)/g;
  try {
    return detail
      .split(/\r?\n+/) // split by newlines
      .filter((line) => line.trim() !== "")
      .map((line, idx) => {
        const parts = line.split(urlRegex); // break into text and links

        return (
          <Typography
            key={idx}
            variant="body1"
            sx={{
              wordBreak: "break-word",
              whiteSpace: "pre-wrap",
              mb: 0.5,
            }}
          >
            {parts.map((part, i) =>
              urlRegex.test(part) ? (
                <Link key={i} href={part} target="_blank" rel="noopener noreferrer">
                  {part}
                </Link>
              ) : (
                <React.Fragment key={i}>{part}</React.Fragment>
              ),
            )}
          </Typography>
        );
      });
  } catch (error) {
    console.error("Error rendering detail lines:", error);
    return <Typography variant="body1">{detail}</Typography>; // Fallback to plain text if error occurs
  }
};

// Create the ToastContext
const ToastContext = createContext<any>(null);

// ToastProvider component
export const ToastProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [toasts, setToasts] = useState<ToastMessage[]>([]); // Store multiple toasts with unique IDs
  // Function to show a toast message with severity, summary, and detail
  const showToast = (severity: AlertColor, summary: string, detail: string, duration: number | null = 8000) => {
    const newToast: ToastMessage = {
      severity,
      summary,
      detail,
      duration,
      id: new Date().getTime(), // Generate a unique ID for each toast
    };
    setToasts((prevToasts) => [...prevToasts, newToast]); // Add the new toast to the list
  };
  const handleClose = (id: number) => {
    setToasts((prevToasts) => prevToasts.filter((toast) => toast.id !== id)); // Remove the closed toast
  };

  const showSuccess = (message: Omit<ToastMessage, "severity">) => {
    showToast("success", message.summary, message.detail, message.duration);
  };

  const showError = (message: Omit<ToastMessage, "severity">) => {
    // Keep errors visible until the user explicitly closes them.
    showToast("error", message.summary, message.detail, message.duration ?? null);
  };

  const showInfo = (message: Omit<ToastMessage, "severity">) => {
    showToast("info", message.summary, message.detail, message.duration);
  };

  const showWarn = (message: Omit<ToastMessage, "severity">) => {
    console.warn(message);
    showToast("warning", message.summary, message.detail, message.duration);
  };

  const copyToastDetails = async (toast: ToastMessage) => {
    const content = [toast.summary, toast.detail].filter(Boolean).join("\n");
    if (!content.trim()) {
      return;
    }

    try {
      await navigator.clipboard.writeText(content);
    } catch (error) {
      console.error("Failed to copy toast content:", error);
    }
  };

  return (
    <ToastContext.Provider value={{ showSuccess, showError, showInfo, showWarn }}>
      {children}
      {toasts.map((toast, index) => (
        <Snackbar
          key={toast.id + index}
          open={true}
          autoHideDuration={toast.duration === undefined ? 8000 : toast.duration}
          onClose={() => handleClose(toast.id)}
          anchorOrigin={{ vertical: "bottom", horizontal: "right" }}
          style={{ bottom: `${16 + index * 80}px` }} // Adjust the position dynamically based on the index
        >
          <Alert
            onClose={() => handleClose(toast.id)}
            severity={toast.severity}
            sx={{
              width: "100%",
              minWidth: 400,
              maxWidth: 600,
              maxHeight: 300,
              overflowY: "auto",
              whiteSpace: "normal",
              wordBreak: "break-word",
              display: "flex",
              alignItems: "flex-start", // 🔥 Align the icon to the top
              gap: 1,
            }}
          >
            <Box sx={{ width: "100%" }}>
              <Box sx={{ display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 1 }}>
                <Typography variant="subtitle1" fontWeight="bold" gutterBottom sx={{ flex: 1 }}>
                  {toast.summary}
                </Typography>
                {toast.severity === "error" && (
                  <Tooltip title="Copier l'erreur">
                    <IconButton
                      aria-label="Copier l'erreur"
                      size="small"
                      onClick={() => void copyToastDetails(toast)}
                      sx={{ mt: -0.5 }}
                    >
                      <ContentCopyIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                )}
              </Box>
              {renderDetailLines(toast.detail)}
            </Box>
          </Alert>
        </Snackbar>
      ))}
    </ToastContext.Provider>
  );
};

/**
 * useToast
 *
 * Custom hook to access the ToastContext.
 * Provides methods to show informational, error, warning, or success toasts
 * anywhere inside the application.
 *
 * @returns {Object} Toast context methods (e.g., showInfo, showError, showWarning, showSuccess)
 */
export const useToast = () => {
  return useContext(ToastContext);
};
