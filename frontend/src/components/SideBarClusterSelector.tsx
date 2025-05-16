import { Select, MenuItem, Typography, FormControl, FormHelperText } from '@mui/material';
import { useTheme } from '@mui/material/styles';

// Assuming ctx is passed as props or accessed via context in this component
export const SideBarClusterSelector = ({ currentClusterOverview, allClusters, setCurrentClusterOverview }) => {
  const theme = useTheme();

  const handleClusterChange = (event) => {
    const selectedClusterAlias = event.target.value;
    const selectedCluster = allClusters.find((cluster) => cluster.alias === selectedClusterAlias);
    if (selectedCluster) {
      setCurrentClusterOverview(selectedCluster.fullname);  
    }
  };
  const isClusterSelected = Boolean(currentClusterOverview?.alias);

  return (
    <FormControl 
      sx={{ m: 1, minWidth: 120 }} 
      error={!isClusterSelected}
      >
        <Select
        value={currentClusterOverview?.alias || ''}
        onChange={handleClusterChange}
        displayEmpty
        size="small"
        variant="outlined"
      >
        {/* If no cluster is selected, display 'None' */}
        <MenuItem value="">
          <Typography variant="body2" color={theme.palette.error.main}>
          <em>None</em> 
          </Typography>
        </MenuItem>
        {/* Display clusters in MenuItems */}
        {allClusters?.map((cluster) => (
          <MenuItem key={cluster.alias} value={cluster.alias}>
              <Typography variant="body2">{cluster.alias}</Typography>
          </MenuItem>
        ))}
      </Select>
      {/* Optionally display a helper text when no cluster is selected */}
      {!isClusterSelected && (
        <FormHelperText>Please select a cluster</FormHelperText>
      )}
    </FormControl>
  );
};
