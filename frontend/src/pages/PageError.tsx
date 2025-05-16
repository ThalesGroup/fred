import { Box, Button, Typography } from "@mui/material";
import ExploreIcon from '@mui/icons-material/Explore';
import { PageBodyWrapper } from "../common/PageBodyWrapper.tsx";
import { useNavigate } from "react-router-dom";

export const PageError = ({ title = 'Page Not Found', message = 'Resource not found' }) => {
  const navigate = useNavigate();
  return (
    <PageBodyWrapper>
      <Box height='100%' width='100%' display='flex' flexDirection='column' justifyContent='center' alignItems='center'>
        <ExploreIcon
          sx={{
            fontSize: 100,
            color: 'error.main',
          }}></ExploreIcon>
        <Typography variant="h5" gutterBottom>{title}</Typography>
        <Typography variant="h6" gutterBottom>
          {message}
        </Typography>
        <Button
          variant="outlined" color="primary" onClick={() => navigate('/')}>
          Back to Home
        </Button>
      </Box>
    </PageBodyWrapper>
  )
}
