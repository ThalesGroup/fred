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
