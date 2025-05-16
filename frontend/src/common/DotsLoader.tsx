import { useTheme } from '@mui/material';
import React from 'react';

const DotsLoader = (props: {
  dotSize?: string;
  dotColor?: string;
}) => {
  const theme = useTheme();
  // Define inline styles
  const loaderStyle: React.CSSProperties = {
    display: 'flex',
  };

  const dotStyle: React.CSSProperties = {
    width: props.dotSize || '5px',
    height: props.dotSize || '5px',
    margin: '0 3px',
    backgroundColor: props.dotColor || theme.palette.primary.light,
    borderRadius: '50%',
    animation: 'bounce 0.6s infinite alternate',
  };

  return (
    <div style={loaderStyle}>
      <span style={{ ...dotStyle, animationDelay: '0s' }}></span>
      <span style={{ ...dotStyle, animationDelay: '0.2s' }}></span>
      <span style={{ ...dotStyle, animationDelay: '0.4s' }}></span>

      {/* Inline CSS for animation */}
      <style>
        {`
          @keyframes bounce {
            from {
              transform: translateY(0);
            }
            to {
              transform: translateY(-10px);
            }
          }
        `}
      </style>
    </div>
  );
};

export default DotsLoader;
