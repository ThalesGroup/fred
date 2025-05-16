import { Box, Typography } from "@mui/material";

interface LabelValuePairProps {
    label: string;
    value: string;
}

export const LabelValuePair = ({ label, value }: LabelValuePairProps) => {

    return (
        <Box display="flex" flexDirection="column" alignItems="center" gap={0.5}>
            <Typography variant="caption" color="primary.light">
                {label}
            </Typography>
            <Typography variant="body2" noWrap={false} sx={{ wordWrap: 'break-word' }}>
                {value}
            </Typography>
        </Box>
    );
};
