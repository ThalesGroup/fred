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

import CheckCircleIcon from "@mui/icons-material/CheckCircle";
import ErrorOutlineIcon from "@mui/icons-material/ErrorOutline";
import HourglassEmptyIcon from "@mui/icons-material/HourglassEmpty";
import {
  Box,
  CircularProgress,
  Divider,
  Paper,
  Step,
  StepContent,
  StepLabel,
  Stepper,
  Typography,
} from "@mui/material";

export interface ProgressStep {
  step: string;
  filename: string;
  status: string;
}

export interface ProgressStepperProps {
  steps: ProgressStep[];
}

export const ProgressStepper = ({ steps }: ProgressStepperProps) => {
  if (!steps.length) return null;

  const stepsByFile = steps.reduce((acc, step) => {
    if (!acc[step.filename]) acc[step.filename] = [];
    acc[step.filename].push(step);
    return acc;
  }, {} as Record<string, ProgressStep[]>);

  const getIcon = (status: string) => {
    switch (status) {
      case "in_progress":
        return <CircularProgress size={18} color="primary" thickness={6} />;
      case "success":
      case "finished":
        return <CheckCircleIcon color="success" fontSize="medium" />;
      case "error":
        return <ErrorOutlineIcon color="error" fontSize="medium" />;
      default:
        return <HourglassEmptyIcon color="disabled" fontSize="medium" />;
    }
  };

  return (
    <Box sx={{ mt: 3, display: "flex", flexDirection: "column", gap: 2 }}>
      {Object.entries(stepsByFile).map(([filename, fileSteps]) => (
        <Paper
          key={filename}
          variant="outlined"
          sx={{
            p: 2,
            borderRadius: 2,
            boxShadow: "none",
            borderColor: "divider",
            backgroundColor: "background.default",
            width: "100%",
            maxWidth: "100%",
          }}
        >
          <Typography
            variant="subtitle1"
            fontWeight="bold"
            gutterBottom
            sx={{
              display: "block",
              whiteSpace: "nowrap",
              overflow: "hidden",
              textOverflow: "ellipsis",
              maxWidth: "100%",
              mb: 1,
            }}
          >
            {filename}
          </Typography>

          <Divider sx={{ mb: 1 }} />

          <Stepper
            activeStep={fileSteps.length}
            orientation="vertical"
            sx={{ pl: 1 }}
          >
            {fileSteps.map((step, index) => (
              <Step key={index}>
                <StepLabel
                  icon={getIcon(step.status)}
                  error={step.status === "error"}
                >
                  <Typography
                    variant="body1"
                    fontWeight="medium"
                    sx={{
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                      maxWidth: "calc(100% - 32px)",
                    }}
                  >
                    {step.step}
                  </Typography>
                </StepLabel>
                <StepContent>
                  <Typography
                    variant="body2"
                    color="textSecondary"
                    sx={{ ml: 1, maxWidth: "100%" }}
                  >
                    {step.status}
                  </Typography>
                </StepContent>
              </Step>
            ))}
          </Stepper>
        </Paper>

      ))}
    </Box>
  );
};
