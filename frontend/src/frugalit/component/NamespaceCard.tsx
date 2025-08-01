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

import { Grid2, Typography, Paper, IconButton, Box, Drawer } from "@mui/material";
import CropFreeIcon from "@mui/icons-material/CropFree";
import { ClusterOverview } from "../slices/api";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { FactList } from "../slices/factsStructures";
import { NamespaceSummary } from "../slices/namespaceSummaryStructures";
import { FactMiniatures } from "./FactMiniatures";
import CustomMarkdownRenderer from "../../components/markdown/CustomMarkdownRenderer";

interface NamespaceCardProps {
  cluster: ClusterOverview;
  factList: FactList;
  namespace: string;
  summary: NamespaceSummary;
}

// Function to truncate Markdown content (by characters or lines)
const truncateMarkdown = (content: string, maxLength: number) => {
  console.log("Content", content);
  return content.length > maxLength ? content.substring(0, maxLength) + " ..." : content;
};

export const NamespaceCard = ({ cluster, factList, namespace, summary }: NamespaceCardProps) => {
  const [open, setOpen] = useState(false);
  const [summaryContent, setSummaryContent] = useState<string>("");
  const navigate = useNavigate();
  const handleOpenSummary = (content: string) => {
    setSummaryContent(content);
    setOpen(true);
  };
  const handleCloseSummary = () => {
    setOpen(false);
  };
  const handleNavigateToFacts = () => {
    navigate(`/facts-namespace?cluster=${cluster.fullname}&namespace=${namespace}`);
  };

  const _summary = summary?.namespace_summary ? summary.namespace_summary : "No summary available";
  const _factList = factList ? factList : { facts: [] };
  console.log("Namespaces", namespace);

  return (
    <Grid2
      container
      spacing={1}
      paddingTop={8}
      paddingBottom={8}
      sx={{ minHeight: "100vh" }}
      alignItems="center"
      justifyContent="center"
    >
      {/* Facts Section */}
      <Grid2 size={{ xs: 12, md: 8 }}>
        <Paper elevation={3} sx={{ padding: 2, display: "flex", flexDirection: "column", gap: 2 }}>
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
        <Paper elevation={3} sx={{ padding: 2, position: "relative" }}>
          <Typography variant="body2">Summary</Typography>
          <CustomMarkdownRenderer content={truncateMarkdown(_summary, 2400)} size="small"/>
          <IconButton sx={{ position: "absolute", top: 8, right: 8 }} onClick={() => handleOpenSummary(_summary)}>
            <CropFreeIcon />
          </IconButton>
        </Paper>
      </Grid2>

      {/* Summary Drawer */}
      <Drawer anchor="right" open={open} onClose={handleCloseSummary}>
        <Box sx={{ width: "50vw", p: 2 }}>
          <Paper sx={{ p: 1, px: 2 }}>
            <CustomMarkdownRenderer content={summaryContent} size="medium"/>
          </Paper>
        </Box>
      </Drawer>
    </Grid2>
  );
};
