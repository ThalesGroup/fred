import React, { useState } from 'react';
import {
  Grid,
  Typography,
  Paper,
  Button,
  TextField,
  Dialog,
  DialogActions,
  DialogContent,
  DialogTitle,
  IconButton, useTheme
} from "@mui/material";
import CloseIcon from '@mui/icons-material/Close';
import { TimePicker } from '@mui/x-date-pickers/TimePicker';
import { LocalizationProvider } from '@mui/x-date-pickers/LocalizationProvider';
import { AdapterDayjs } from '@mui/x-date-pickers/AdapterDayjs';
import dayjs from 'dayjs';
import RRuleGenerator from 'react-rrule-generator';
import { useToast } from '../components/ToastProvider';

interface OptimizationInputFormProps {
  isOpen: boolean;
  onClose: () => void;
  onSubmit?: (optimization: any) => void;
}

export const OptimizationInputForm: React.FC<OptimizationInputFormProps> = ({
                                                                              isOpen,
                                                                              onClose,
                                                                              onSubmit
                                                                            }) => {
  const [optimizationName, setOptimizationName] = useState<string>('');
  const [minInstances, setMinInstances] = useState<number>(0);
  const [maxInstances, setMaxInstances] = useState<number>(10);
  const [rrule, setRrule] = useState<string>('');
  const [duration, setDuration] = useState<string>('');
  const [startTime, setStartTime] = useState<dayjs.Dayjs | null>(null);
  const theme = useTheme();
  const { showError, showSuccess } = useToast(); // Use the toast hook

  const handleRruleChange = (newRrule: string) => {
    setRrule(newRrule);
  };

  const handleSubmit = () => {
    if (!optimizationName || !rrule || !duration || !startTime) {
      showError({
        summary: 'Form Error',
        detail: 'Please fill in all required fields.',
      });
      return;
    }

    if (onSubmit) {
      onSubmit({
        optimizationName,
        minInstances,
        maxInstances,
        rrule,
        duration,
        startTime: startTime
      });
      showSuccess({
        summary: 'Success',
        detail: 'Optimization schedule has been set successfully!',
      });
    }
    onClose();
  };

  return (
      <LocalizationProvider dateAdapter={AdapterDayjs}>
        <Dialog open={isOpen} onClose={onClose} maxWidth="md" fullWidth>
          <DialogTitle>
            <Typography variant="body2" sx={{ fontWeight: 'bold' }}>
              Set Schedule
            </Typography>
            <IconButton
                aria-label="close"
                onClick={onClose}
                sx={{
                  position: 'absolute',
                  right: 8,
                  top: 8,
                  color: (theme) => theme.palette.grey[500],
                }}
            >
              <CloseIcon />
            </IconButton>
          </DialogTitle>
          <DialogContent>
            <Grid container spacing={2}>
              <Grid item xs={12}>
                <TextField
                    label="Optimization Name"
                    value={optimizationName}
                    onChange={(e) => setOptimizationName(e.target.value)}
                    fullWidth
                    required
                    margin="normal"
                />
              </Grid>
              <Grid item xs={12}>
                <Paper elevation={3} sx={{ p: 2, mt: 2 }}>
                  <Typography variant="h6" gutterBottom>Recurrence Rule</Typography>
                  <RRuleGenerator
                      onChange={handleRruleChange}
                      value={rrule}
                      config={{
                        repeat: ['Yearly', 'Monthly', 'Weekly', 'Daily'],
                        yearly: 'on',
                        monthly: 'on',
                        end: ['Never', 'After', 'On date'],
                        weekStartsOnSunday: true,
                      }}
                  />
                </Paper>
              </Grid>
              <Grid item xs={12} md={6}>
                <TimePicker
                    label="Start Time"
                    value={startTime}
                    onChange={(newValue) => setStartTime(newValue)}
                    slotProps={{ textField: { fullWidth: true, margin: 'normal' } }}
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                    label="Duration"
                    value={duration}
                    onChange={(e) => setDuration(e.target.value)}
                    fullWidth
                    required
                    margin="normal"
                    placeholder="e.g., 1h 30m, 2h, 45m"
                    helperText="Enter duration in hours (h) and/or minutes (m)"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                    label="Min Instances"
                    type="number"
                    value={minInstances}
                    onChange={(e) => setMinInstances(Number(e.target.value))}
                    fullWidth
                    InputProps={{ inputProps: { min: 0 } }}
                    margin="normal"
                />
              </Grid>
              <Grid item xs={12} md={6}>
                <TextField
                    label="Max Instances"
                    type="number"
                    value={maxInstances}
                    onChange={(e) => setMaxInstances(Number(e.target.value))}
                    fullWidth
                    InputProps={{ inputProps: { min: 0 } }}
                    margin="normal"
                />
              </Grid>
            </Grid>
          </DialogContent>
          <DialogActions>
            <Button onClick={onClose}>Cancel</Button>
            <Button
                onClick={handleSubmit}
                variant="contained"
                disabled={!optimizationName || !rrule || !duration || !startTime}
                sx={{
                  backgroundColor: theme.palette.primary.main,
                  '&:hover': {
                    backgroundColor: theme.palette.primary.light,
                  }
                }}
            >
              Submit
            </Button>
          </DialogActions>
        </Dialog>
      </LocalizationProvider>
  );
};
