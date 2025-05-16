import { useState, useEffect } from "react";
import {
    Table,
    TableBody,
    TableCell,
    TableContainer,
    TableHead,
    TableRow,
    TablePagination,
    Typography,
    useTheme,
} from "@mui/material";

const FactsTable = ({ hexData, selectedFact, setSelectedFact }) => {
    const theme = useTheme();
    const [page, setPage] = useState(0); // Current page
    const [rowsPerPage, setRowsPerPage] = useState(5); // Number of rows per page

    // Handle page change
    const handlePageChange = (_event, newPage) => {
        setPage(newPage);
    };

    // Handle rows per page change
    const handleRowsPerPageChange = (event) => {
        console.log("Rows per page changed to", event.target.value);
        setRowsPerPage(parseInt(event.target.value, 10));
        setPage(0); // Reset to the first page
    };

    // Paginated data
    const paginatedData = hexData.slice(
        page * rowsPerPage,
        page * rowsPerPage + rowsPerPage
    );

    // Automatically navigate to the correct page when a fact is selected
    useEffect(() => {
        if (selectedFact) {
            const index = hexData.findIndex(({ fact }) => fact.title === selectedFact.title);
            if (index !== -1) {
                const newPage = Math.floor(index / rowsPerPage);
                if (newPage !== page) {
                    setPage(newPage);
                }
            }
        }
    }, [selectedFact, hexData, rowsPerPage, page]);
    console.log("selectedFact", selectedFact);
    return (
        <TableContainer>
            <Table stickyHeader size="small">
                <TableHead>
                    <TableRow 
                    >
                        <TableCell
                            sx={{
                                fontWeight: "bold",
                                color: theme.palette.primary.contrastText,
                                backgroundColor: theme.palette.primary.main,
                            }}
                        >
                            Title
                        </TableCell>
                        <TableCell
                            sx={{
                                fontWeight: "bold",
                                color: theme.palette.primary.contrastText,
                                backgroundColor: theme.palette.primary.main,
                            }}
                        >
                            User
                        </TableCell>
                        <TableCell
                            sx={{
                                fontWeight: "bold",
                                color: theme.palette.primary.contrastText,
                                backgroundColor: theme.palette.primary.main,
                            }}
                        >
                            Date
                        </TableCell>
                        <TableCell
                            sx={{
                                fontWeight: "bold",
                                color: theme.palette.primary.contrastText,
                                backgroundColor: theme.palette.primary.main,
                            }}
                        >
                            Content
                        </TableCell>
                    </TableRow>
                </TableHead>
                <TableBody>
                    {paginatedData.map(({ fact }, index) => (
                        <TableRow
                            key={index}
                            hover
                            onClick={() => setSelectedFact(fact)} // Handle row click
                            sx={{
                                cursor: "pointer",
                                backgroundColor: selectedFact?.title === fact.title
                                    ? theme.palette.primary.main // Apply selected color
                                    : "inherit", // Default background for unselected rows
                                "&:hover": {
                                    backgroundColor: selectedFact?.title === fact.title
                                        ? theme.palette.primary.main // Keep selected row color on hover
                                        : theme.palette.action.hover, // Apply hover color for unselected rows
                                },
                            }}
                        >
                            <TableCell>
                                <Typography variant="body2">
                                    {fact.title}
                                </Typography>
                            </TableCell>
                            <TableCell>
                                <Typography variant="body2">
                                    {fact.user}
                                </Typography>
                            </TableCell>
                            <TableCell sx={{
                                whiteSpace: "nowrap", // Prevent text wrapping
                                overflow: "hidden", // Handle long text
                                textOverflow: "ellipsis", // Add ellipsis if text is too long
                            }}>
                                <Typography variant="body2">
                                    {new Date(fact.date).toLocaleDateString("en-US", {
                                        year: "numeric",
                                        month: "short",
                                        day: "numeric",
                                    })}
                                </Typography>
                            </TableCell>
                            <TableCell>
                                <Typography variant="body2" sx={{  fontWeight: "bold",fontStyle: "italic" }}>
                                    {fact.content}
                                </Typography>
                            </TableCell>
                        </TableRow>
                    ))}
                </TableBody>
            </Table>
            {/* Pagination Controls */}
            <TablePagination
                rowsPerPageOptions={[4, 8, 16]}
                component="div"
                count={hexData.length}
                rowsPerPage={rowsPerPage}
                page={page}
                onPageChange={handlePageChange}
                onRowsPerPageChange={handleRowsPerPageChange}
            />
        </TableContainer>
    );
};

export default FactsTable;
