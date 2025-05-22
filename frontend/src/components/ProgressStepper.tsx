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

import { Stepper, Step, StepLabel, StepContent, Typography, Box } from "@mui/material";
import ErrorOutlineIcon from '@mui/icons-material/ErrorOutline';

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

    return (
        <Box sx={{ mt: 3 }}>
            <Stepper
                activeStep={steps.length}
                orientation="vertical">
                {steps.map((step, index) => (
                    <Step key={index}>
                        <StepLabel
                            error={step.status === "error"}
                            optional={step.status === "error" ? (
                                <ErrorOutlineIcon color="error" fontSize="small" />
                            ) : null}
                        >
                            {step.step}
                        </StepLabel>
                        <StepContent>
                            <Typography variant="body2" color="textSecondary">
                               {step.filename} : {step.status}
                            </Typography>
                        </StepContent>
                    </Step>
                ))}
            </Stepper>
        </Box>
    );
};
