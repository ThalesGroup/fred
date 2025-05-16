import {Box, Button, Typography} from "@mui/material";
import {ImageComponent} from "../utils/image.tsx";
import {ClusterOverview} from "../slices/api.tsx";

export const ClusterScoreCard = (props: {
    scope: ClusterOverview,
    handleUpdateSelectedScopes: (scopeDetail: ClusterOverview) => void
    activate: boolean
}) => {
    return (
        <Box display='flex' flexDirection='column' alignItems='center'>
            <Button
                onClick={function(){props.handleUpdateSelectedScopes(props.scope);}}
                variant='contained'
                sx={{
                    bgcolor: props.activate ? 'primary.main' : 'common.white',
                    color: props.activate ? 'common.white' : 'common.black',
                    border: `1px solid grey`,
                    textTransform: 'none'
                }}>
                <ImageComponent name={props.scope.provider} width="40px" height="40px"/>
                <Typography pl={1}>{props.scope.alias}</Typography>
            </Button>
        </Box>
    );
}