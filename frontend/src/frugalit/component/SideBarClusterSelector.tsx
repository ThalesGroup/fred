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
