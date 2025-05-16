import {
    Button,
    Grid2,
    Paper,
    Skeleton,
    Typography,
    useTheme,
} from "@mui/material";
import dayjs from 'dayjs';
import utc from 'dayjs/plugin/utc';
import timezone from 'dayjs/plugin/timezone';
import 'dayjs/locale/en-gb';
import { useContext, useEffect, useState } from "react";
import { v4 as uuidv4 } from "uuid";
import {ApplicationContext} from "../app/ApplicationContextProvider.tsx";

dayjs.extend(utc);
dayjs.extend(timezone);

export const NamespaceFilter = () => {
    const ctx = useContext(ApplicationContext);
    const [selectAll, setSelectAll] = useState(false);
    const theme = useTheme(); // Access the theme object

    const handleNamespace = (namespace: string) => {
        if (namespace !== null) {
            ctx.updateSingleNamespace(namespace)
        }
    }

    useEffect(() => {
        setSelectAll(ctx.currentNamespaces.length !== ctx.selectedNamespaces.length);
    }, [ctx.selectedNamespaces]);

    const handleSelectAll = () => {
        if (ctx.currentNamespaces.length === ctx.selectedNamespaces.length) {
            ctx.updateSelectedNamespaces([]);
            setSelectAll(true);
        } else {
            ctx.updateSelectedNamespaces(ctx.currentNamespaces);
            setSelectAll(false);
        }
    }

    return (
        <Grid2 container>
            <Paper sx={{ width: "100%", padding: 2 }}>
                <Grid2 container spacing={4} alignItems="center">
                    {/* Left side: Title and Select/Unselect Button */}
                    <Grid2 size={3} container direction="column" alignItems="flex-start" justifyContent="space-between" spacing={3}>
                        {ctx.currentNamespaces.length > 0 ? (
                            <Grid2>
                                <Button
                                    onClick={() => handleSelectAll()}
                                    sx={{
                                        backgroundColor: theme.palette.primary.main, // Using theme background
                                        color: theme.palette.primary.contrastText, // Using theme text color
                                        border: 'none',
                                        textTransform: 'none',
                                        '&:hover': {
                                            backgroundColor: theme.palette.background.default,
                                            textDecoration: 'underline',
                                        },
                                    }}>
                                    <Typography color="primary.contrastText" variant="body2">
                                        {selectAll ? 'Select all namespaces' : 'Unselect all namespaces'}
                                    </Typography>
                                </Button>
                            </Grid2>
                        ) : (
                            <Skeleton animation="wave" width={"50%"} />
                        )}
                    </Grid2>

                    {/* Right side: Namespaces */}
                    <Grid2 size={9} container direction="row" spacing={2} justifyContent="center">
                        {ctx.currentNamespaces.length > 0 ? (
                            ctx.currentNamespaces.map((namespace) => (
                                <Grid2 key={uuidv4()}>
                                    <Button
                                        onClick={() => handleNamespace(namespace)}
                                        sx={{
                                            backgroundColor: ctx.selectedNamespaces.includes(namespace)
                                                ? theme.palette.primary.main 
                                                : theme.palette.text.disabled, 
                                            color: ctx.selectedNamespaces.includes(namespace)
                                                ? theme.palette.text.primary // White text for selected
                                                : theme.palette.text.disabled, // Default text color
                                            border: ctx.selectedNamespaces.includes(namespace)
                                                ? `1px solid ${theme.palette.primary.main}` // Primary border for selected
                                                : `1px solid ${theme.palette.text.disabled}`, // Grey border for unselected
                                            padding: '0.5vh 2vw 0.5vh 2vw',
                                            display: 'flex',
                                            alignItems: 'center',
                                            justifyContent: 'center',
                                            '&:hover': {
                                                backgroundColor: ctx.selectedNamespaces.includes(namespace)
                                                    ? theme.palette.primary.light
                                                    : theme.palette.primary.main, // Switch to primary on hover
                                                color: ctx.selectedNamespaces.includes(namespace)
                                                    ? theme.palette.text.primary
                                                    : theme.palette.common.white, // Switch to white text on hover
                                            },
                                        }}>
                                        <Typography color="primary.contrastText" variant="body2" >{namespace}</Typography>
                                    </Button>
                                </Grid2>
                            ))
                        ) : (
                            <Skeleton animation="wave" width={"100%"} height={"100%"} />
                        )}
                    </Grid2>
                </Grid2>
            </Paper>
        </Grid2>
    );
};
