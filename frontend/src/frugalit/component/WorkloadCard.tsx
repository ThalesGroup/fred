// Copyright Thales 2025
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

import { Grid2, Typography, Paper, IconButton, Box, Drawer, TableContainer, TableRow, Table, TableCell, TableBody, useTheme, Tooltip } from '@mui/material';
import CropFreeIcon from '@mui/icons-material/CropFree';
import { ResourceIdentityCard } from './ResourceIdentityCard';
import { Workload } from '../../utils/resource';
import { WorkloadAdvanced, WorkloadId, WorkloadEssentials, ClusterOverview } from '../slices/api';
import { ResourceScoreCard } from './ResourceScoreCard';
import MarkdownRenderer from '../../components/markdown/MarkdownRenderer';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FactList } from '../slices/factsStructures';
import { FactMiniatures } from './FactMiniatures';
import { WorkloadSummary } from '../slices/workloadSummaryStructures';
import EmptyIcon from '@mui/icons-material/RemoveCircleOutline';
import { WorkloadScores } from '../slices/scoresStructures';
import { WorkloadEcoScore } from './WorkloadEcoScore';

interface ResourceOverviewProps {
    cluster: ClusterOverview;
    resource: Workload;
    score: WorkloadScores;
    factList: FactList;
    id: WorkloadId;
    namespace: string;
    summary: WorkloadSummary;
    essentials: WorkloadEssentials;
    advanced: WorkloadAdvanced;
}

// Function to truncate Markdown content (by characters or lines)
const truncateMarkdown = (content: string, maxLength: number) => {
    console.log("Content", content);
    return content.length > maxLength ? content.substring(0, maxLength) + ' ...' : content;
};

const renderCompactKeyValueTable = (data: object) => {
    const theme = useTheme();
    if (!data) {
        return (
            <Tooltip title="No advanced information available" arrow>
                <Box display="flex" alignItems="center" justifyContent="center">
                    <EmptyIcon color="disabled" />
                </Box>
            </Tooltip>);
    }
    return (
        <TableContainer component={Paper} elevation={0} sx={{ maxHeight: '200px' }}>
            <Table size="small" aria-label="key-value table">
                {/*  <TableHead>
                    <TableRow>
                        <TableCell><Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>Key</Typography></TableCell>
                        <TableCell><Typography variant="subtitle2" sx={{ fontWeight: 'bold' }}>Value</Typography></TableCell>
                    </TableRow>
                </TableHead> */}
                <TableBody>
                    {Object.entries(data).map(([key, value], index) => (
                        <TableRow key={key} sx={{
                            backgroundColor: index % 2 === 0
                                ? (theme.palette.mode === 'light' ? theme.palette.grey[100] : theme.palette.grey[800])  // Even rows
                                : (theme.palette.mode === 'light' ? theme.palette.common.white : theme.palette.grey[900])  // Odd rows
                        }}>
                            <TableCell component="th" scope="row">
                                <Typography variant="caption">{key}</Typography>
                            </TableCell>
                            <TableCell align="right">
                                <Typography variant="caption">
                                    {typeof value === 'object' ? JSON.stringify(value, null, 2) : value}
                                </Typography>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
        </TableContainer>
    );
};
export const WorkloadCard = ({
    cluster, resource, score, factList, id, summary, essentials, advanced }: ResourceOverviewProps) => {
    const [open, setOpen] = useState(false);
    const [summaryContent, setSummaryContent] = useState<string>('');
    const navigate = useNavigate();
    const handleOpenSummary = (content: string) => {
        setSummaryContent(content);
        setOpen(true);
    };
    const handleCloseSummary = () => {
        setOpen(false);
    };
    const handleNavigateToScoreDetail = () => {
        navigate(`/score/${cluster.alias}/${resource.namespace}/${resource.name}?kind=${resource.kind}`, { state: { score } });
    };
    const handleNavigateToFacts = () => {
        navigate(`/facts-workload?cluster=${cluster.fullname}&namespace=${resource.namespace}&workload=${resource.name}&kind=${resource.kind}`, { state: { score } });
    };
    const _summary = summary?.workload_summary ? summary.workload_summary : 'No summary available';
    const _factList = factList ? factList : { facts: [] };
    return (
        <Grid2 container spacing={2} padding={2} sx={{ minHeight: '100vh' }}>
            {/* Left Column with 4 vertically stacked items */}
            <Grid2 size={{ xs: 12, md: 6 }} sx={{ display: 'flex', flexDirection: 'column', flexGrow: 0 }}>
                <Paper elevation={3} sx={{ padding: 2, marginBottom: 2 }}>
                    <ResourceIdentityCard
                        resource_name={id.workload_id}
                        resource_kind={resource.kind}
                        resource_id={resource.name}
                        resource_namespace={resource.namespace} />
                </Paper>
                <Paper
                    elevation={3}
                    sx={{
                        padding: 2,
                        marginBottom: 2,
                        display: 'flex',
                        flexDirection: 'column', // Stack items vertically
                        width: '100%',
                    }}
                >
                    <Box
                        sx={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            width: '100%',
                        }}
                    >
                        {/* Facts label */}
                        <Typography variant="body2" sx={{ minWidth: '100px', flexShrink: 0 }}>
                            Facts
                        </Typography>
                        {/* Icon button on the right */}
                        <IconButton onClick={handleNavigateToFacts} sx={{ flexShrink: 0 }}>
                            <CropFreeIcon />
                        </IconButton>
                    </Box>

                    {/* Centered Miniatures below the header */}
                    <Box
                        sx={{
                            display: 'flex',
                            justifyContent: 'center',
                            marginTop: 0, // Space between header and miniatures
                        }}
                    >
                        <FactMiniatures facts={_factList.facts} />
                    </Box>
                </Paper>

                {/* Adjust flexGrow for Score Card based on facts/optimizations */}
                <Paper
                    elevation={3}
                    sx={{
                        flexGrow: 0, // Always allow the score card to take the remaining space
                        minHeight: '600px',
                        padding: 2,
                        marginBottom: 2,
                        display: 'flex',
                        flexDirection: 'column'
                    }}
                >
                    <Grid2 container size={{ xs: 12 }} alignItems="center" justifyContent="space-between" sx={{ marginBottom: 0 }}>
                        <Grid2 size={{ xs: 4 }} sx={{ display: "flex", justifyContent: "center", alignItems: "flex-start" }}>
                            <WorkloadEcoScore workload_scores={score}/>
                        </Grid2>
                        <Grid2 size={{ xs: 6 }} sx={{ display: "flex", justifyContent: "center", alignItems: "flex-start" }}>
                            <Typography variant="body2">Eco-Score</Typography>
                        </Grid2>
                        <Grid2 size={{ xs: 2 }} display="flex" justifyContent="flex-end">
                            <IconButton
                                sx={{ position: 'relative' }}
                                onClick={() => handleNavigateToScoreDetail()}>
                                <CropFreeIcon />
                            </IconButton>
                        </Grid2>
                    </Grid2>
                    <Box sx={{ flexGrow: 1, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <ResourceScoreCard name={id.workload_id} score={score} />
                    </Box>
                </Paper>

            </Grid2>

            {/* Right Column with Essentials and Advanced sections */}
            <Grid2 size={{ xs: 12, md: 6 }} sx={{ display: 'flex', flexDirection: 'column', flexGrow: 1 }}>
                <Paper elevation={3} sx={{ flex: 0, padding: 2, marginBottom: 2, position: 'relative' }}>
                    <Typography variant="body2">Summary</Typography>
                    <MarkdownRenderer content={truncateMarkdown(_summary, 1200)} />
                    <IconButton
                        sx={{ position: 'absolute', top: 8, right: 8 }}
                        onClick={() => handleOpenSummary(_summary)}>
                        <CropFreeIcon />
                    </IconButton>
                </Paper>
                <Paper elevation={3}
                    sx={{
                        flex: 1,
                        flexGrow: essentials && Object.keys(essentials).length > 0 ? 1 : 0, // Allow it to grow only if content exists
                        minHeight: essentials && Object.keys(essentials).length > 0 ? '150px' : 'auto', // Minimum height only if there is content
                        padding: 2,
                        marginBottom: 2
                    }}>
                    <Typography variant="body2">Essentials</Typography>
                    {renderCompactKeyValueTable(essentials)}  {/* Render essentials as key-value pairs */}
                </Paper>

                <Paper elevation={3}
                    sx={{
                        flex: 1,
                        flexGrow: advanced && Object.keys(advanced).length > 0 ? 1 : 0, // Allow it to grow only if content exists
                        minHeight: advanced && Object.keys(advanced).length > 0 ? '150px' : 'auto', // Minimum height only if there is content
                        padding: 2,
                        marginBottom: 2
                    }}>
                    <Typography variant="body2">Advanced</Typography>
                    {renderCompactKeyValueTable(advanced)}  {/* Render advanced as key-value pairs */}
                </Paper>
            </Grid2>
            <Drawer
                anchor="right"
                open={open}
                onClose={handleCloseSummary}
            >
                <Box sx={{ width: '50vw', p: 2 }}>
                    <Paper sx={{ p: 1, px: 2, width: "100%" }}>
                        <MarkdownRenderer size="medium" content={summaryContent} />
                    </Paper>
                </Box>
            </Drawer>
        </Grid2>
    );
};
