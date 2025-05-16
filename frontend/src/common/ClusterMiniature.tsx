import { Card, CardContent, CardActions, Button, Typography, useTheme, Box, Avatar } from "@mui/material";
import { ImageComponent } from "../utils/image";

interface ClusterMiniatureProps {
    fullname: string;
    alias: string;
    provider: string;
    hadleSelectUnselect: (fullname: string) => void;
    handleFollowSelected: (fullname: string) => void;
    activate: boolean;
}

export const ClusterMiniature = (
    {fullname, alias, provider, hadleSelectUnselect, handleFollowSelected, activate} : ClusterMiniatureProps) => {
    const theme = useTheme();

    return (
        <Card sx={{ 
            minWidth: 200, 
            border: activate ? `1px solid ${theme.palette.primary.light}` : 'none',
            backgroundColor: theme.palette.background.paper 
            }}>
            <CardContent>
                <Box display='flex' flexDirection='row' alignItems='center'>
                <Avatar
                        sx={{
                            width: 40,
                            height: 40,
                            backgroundColor: theme.palette.common.white,
                        }}
                    >
                    <ImageComponent
                        name={provider}
                        width="30px"
                        height="30px"
                    />
                    </Avatar>
                    <Typography 
                        variant="h6" 
                        component="div" 
                        color={activate ? theme.palette.text.primary : theme.palette.text.secondary}
                        pl={2}
                    >
                        {alias}
                    </Typography>
                </Box>
            </CardContent>
            <CardActions sx={{ justifyContent: 'space-between' }}>
                <Button
                    onClick={() => hadleSelectUnselect(fullname)}
                    size="small"
                    sx={{
                        backgroundColor: theme.palette.primary.main,
                        color: theme.palette.primary.contrastText,
                        textTransform: 'none'
                    }}
                >
                    {activate ? 'Unselect' : 'Select'}
                </Button>
                <Button
                    onClick={() => handleFollowSelected(fullname)}
                    size="small"
                    sx={{
                        backgroundColor: theme.palette.primary.main,
                        color: theme.palette.primary.contrastText,
                        textTransform: 'none',
                    }}
                >
                    Details
                </Button>
            </CardActions>
        </Card>
    );
}
