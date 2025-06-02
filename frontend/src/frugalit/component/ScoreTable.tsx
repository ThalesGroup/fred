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

import React, { useState } from "react";
import {
  Box,
  Collapse,
  IconButton,
  Table,
  TableBody,
  TableCell,
  TableContainer,
  TableHead,
  TableRow,
  Typography,
  Paper,
  TablePagination,
} from "@mui/material";
import KeyboardArrowDownIcon from "@mui/icons-material/KeyboardArrowDown";
import KeyboardArrowUpIcon from "@mui/icons-material/KeyboardArrowUp";
import { ClusterScore, Workload } from "../slices/scoresStructures.tsx";
import { ScoreLetter, WorkloadEcoScore } from "./WorkloadEcoScore.tsx";

interface RowProps {
  workload: Workload;
}

const WorkloadRow: React.FC<RowProps> = ({ workload }) => {
  const [open, setOpen] = React.useState(false);

  return (
    <React.Fragment>
      {/* Main Row */}
      <TableRow sx={{ "& > *": { borderBottom: "unset" } }}>
        <TableCell>
          <IconButton aria-label="expand row" size="small" onClick={() => setOpen(!open)}>
            {open ? <KeyboardArrowUpIcon /> : <KeyboardArrowDownIcon />}
          </IconButton>
        </TableCell>
        <TableCell align="center">{workload.name}</TableCell>
        <TableCell align="center">{workload.namespace}</TableCell>
        <TableCell align="center">{workload.kind}</TableCell>
        <TableCell align="center">
          <WorkloadEcoScore workload_scores={workload.scores} />
        </TableCell>
      </TableRow>
      {/* Collapsible Sub-rows */}
      <TableRow>
        <TableCell style={{ paddingBottom: 0, paddingTop: 0 }} colSpan={5}>
          <Collapse in={open} timeout="auto" unmountOnExit>
            <Box sx={{ margin: 1 }}>
              <Typography variant="h6" gutterBottom component="div">
                Scores
              </Typography>
              <Table size="small" aria-label="scores">
                <TableHead>
                  <TableRow>
                    <TableCell>Score</TableCell>
                    <TableCell>Attribute</TableCell>
                    <TableCell align="center">Reason</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {Object.entries(workload.scores).map(([attribute, score]) => (
                    <TableRow key={attribute}>
                      <TableCell align="center">
                        <ScoreLetter score={score.score} />
                      </TableCell>
                      <TableCell>{attribute}</TableCell>
                      <TableCell>{score.reason}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Collapse>
        </TableCell>
      </TableRow>
    </React.Fragment>
  );
};

interface ClusterScoresTableProps {
  clusterScores: ClusterScore;
}

const ClusterScoresTable: React.FC<ClusterScoresTableProps> = ({ clusterScores }) => {
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(10);

  const handleChangePage = (_event: unknown, newPage: number) => {
    setPage(newPage);
  };

  const handleChangeRowsPerPage = (event: React.ChangeEvent<HTMLInputElement>) => {
    setRowsPerPage(parseInt(event.target.value, 10));
    setPage(0);
  };

  // Paginate workloads
  const paginatedWorkloads = clusterScores.workload_scores.slice(page * rowsPerPage, page * rowsPerPage + rowsPerPage);

  return (
    <Paper>
      <TableContainer>
        <Table aria-label="collapsible table">
          <TableHead>
            <TableRow>
              <TableCell />
              <TableCell align="center">Workload</TableCell>
              <TableCell align="center">Namespace</TableCell>
              <TableCell align="center">Kind</TableCell>
              <TableCell align="center">Score</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {paginatedWorkloads.map((workload) => (
              <WorkloadRow key={workload.name} workload={workload} />
            ))}
          </TableBody>
        </Table>
      </TableContainer>
      <TablePagination
        rowsPerPageOptions={[10, 30, 100]}
        component="div"
        count={clusterScores.workload_scores.length}
        rowsPerPage={rowsPerPage}
        page={page}
        onPageChange={handleChangePage}
        onRowsPerPageChange={handleChangeRowsPerPage}
      />
    </Paper>
  );
};

export default ClusterScoresTable;
