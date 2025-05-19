import {
    Typography,
    Paper,
    IconButton,
    Box,
    Drawer,
    Grid2,
} from '@mui/material';
import CropFreeIcon from '@mui/icons-material/CropFree';
import MarkdownRenderer from '../../components/markdown/MarkdownRenderer';
import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { FactList } from '../slices/factsStructures';
import { FactMiniatures } from './FactMiniatures';
import { ClusterOverview } from '../slices/api';
import { ClusterSummary } from './clusterSummaryStructures';

interface ClusterCardProps {
    cluster: ClusterOverview;
    factList: FactList;
    summary: ClusterSummary;
}

// Function to truncate Markdown content
const truncateMarkdown = (content: string, maxLength: number) => {
    return content.length > maxLength ? content.substring(0, maxLength) + ' ...' : content;
};

export const ClusterCard = ({ cluster, factList, summary }: ClusterCardProps) => {
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

    const handleNavigateToFacts = () => {
        navigate(`/facts-cluster?cluster=${cluster.fullname}`);
    };

    const _summary = summary?.cluster_summary || 'No summary available';
    const _factList = factList?.facts.length ? factList : { facts: [] };

    return (
        <Grid2
            container
            spacing={1}
            paddingTop={8}
            paddingBottom={8}
            sx={{ minHeight: '100vh' }}
            alignItems="center"
            justifyContent="center"
        >
            {/* Facts Section */}
            <Grid2 size={{ xs: 12, md: 8 }}>
                <Paper elevation={3} sx={{ padding: 2, display: 'flex', flexDirection: 'column', gap: 2 }}>
                    <Box display="flex" justifyContent="space-between" alignItems="center">
                        <Typography variant="body2">Facts</Typography>
                        <IconButton onClick={handleNavigateToFacts}>
                            <CropFreeIcon />
                        </IconButton>
                    </Box>
                    <FactMiniatures facts={_factList.facts} />
                </Paper>
            </Grid2>

            {/* Summary Section */}
            <Grid2 size={{ xs: 12, md: 8 }}>
                <Paper elevation={3} sx={{ padding: 2, position: 'relative' }}>
                    <Typography variant="body2">Summary</Typography>
                    <MarkdownRenderer content={truncateMarkdown(_summary, 2400)} />
                    <IconButton
                        sx={{ position: 'absolute', top: 8, right: 8 }}
                        onClick={() => handleOpenSummary(_summary)}
                    >
                        <CropFreeIcon />
                    </IconButton>
                </Paper>
            </Grid2>

            {/* Summary Drawer */}
            <Drawer anchor="right" open={open} onClose={handleCloseSummary}>
                <Box sx={{ width: '50vw', p: 2 }}>
                    <Paper sx={{ p: 1, px: 2 }}>
                        <MarkdownRenderer size="medium" content={summaryContent} />
                    </Paper>
                </Box>
            </Drawer>
        </Grid2>
    );
};