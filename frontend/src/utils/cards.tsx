import { Box, Typography } from "@mui/material";
import {LogoComponent} from "./image.tsx";

interface AppCardProps {
    guessed_application: string;
}

export const ApplicationCard = ({ guessed_application }: AppCardProps) => {
    return (
            <Box p={0} paddingTop={1}
                 display="flex" flexDirection="column" alignItems="center" justifyContent="center">
                {
                    <LogoComponent
                        name={guessed_application}
                        width="30px"
                        height="auto"
                    />}

                <Typography align="center" fontSize={"small"} paddingTop={0} paddingBottom={1}>
                    {guessed_application}
                </Typography>
            </Box>
    );
};
