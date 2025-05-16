import React from 'react';
import { Box, Tooltip, Typography } from '@mui/material';
import { SvgIconComponent } from '@mui/icons-material';
import { useTheme } from '@mui/material/styles';

interface ChipComponentProps {
  name: string;
  tooltipText: string;
  Icon: SvgIconComponent;
}

const ChipComponent: React.FC<ChipComponentProps> = ({ name, tooltipText, Icon }) => {
  const theme = useTheme();

  return (
    <Tooltip title={tooltipText}>
      <Box
        display="flex"
        alignItems="center"
        sx={{
          backgroundColor: theme.palette.mode === 'dark' ? theme.palette.text.disabled : "#dedfe0",
          borderRadius: '15px',
          padding: '5px',
          marginRight: '2%',
          minWidth: '90px',
          fontSize: '0.75rem',
          height: '24px'
        }}
      >
        <Icon sx={{ fontSize: '20px', mr: 0.5, color: theme.palette.text.secondary, marginLeft: '5px' }} />
        <Typography
          variant="subtitle1"
          sx={{
            marginLeft: '10px',
            marginRight: '5px',
            whiteSpace: 'nowrap',
          }}
        >
          {name}
        </Typography>
      </Box>
    </Tooltip>
  );
};

export default ChipComponent;