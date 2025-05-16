import { Box, LinearProgress, Typography } from '@mui/material';

const LoadingWithProgress = () => {
  return (
    <Box display="flex" flexDirection="column" alignItems="center" justifyContent="center" mt={2}>
      {/* Loading text */}
      <Typography variant="body2" color="textSecondary" gutterBottom>
        Loading, please wait...
      </Typography>
      {/* Progress bar */}
      <LinearProgress color='warning' style={{ width: '100%', maxWidth: '200px' }} />
    </Box>
  );
};


export default LoadingWithProgress;
