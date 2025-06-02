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

import React from "react";
import Autocomplete from "@mui/material/Autocomplete";
import TextField from "@mui/material/TextField";
import { useTheme } from "@mui/material/styles";

interface CustomAutoCompleteProps {
  value: any;
  options: any[];
  getOptionLabel: (option: any) => string;
  isOptionEqualToValue: (option: any, value: any) => boolean;
  onChange: (event: React.ChangeEvent<{}>, value: any) => void;
}

const CustomAutoComplete: React.FC<CustomAutoCompleteProps> = ({
  value,
  options,
  getOptionLabel,
  isOptionEqualToValue,
  onChange,
}) => {
  const theme = useTheme();
  return (
    <Autocomplete
      id="custom-autocomplete"
      value={value}
      options={options}
      getOptionLabel={getOptionLabel}
      isOptionEqualToValue={isOptionEqualToValue}
      onChange={onChange}
      fullWidth
      sx={{
        display: "flex",
        alignItems: "center",
        "& .MuiAutocomplete-popupIndicator": {
          color: theme.palette.primary.light,
        },
        "& .MuiAutocomplete-clearIndicator": {
          color: theme.palette.primary.light,
        },
      }}
      renderInput={(params) => (
        <TextField
          {...params}
          sx={{
            "& .MuiOutlinedInput-root": {
              "& fieldset": {
                borderColor: theme.palette.primary.light,
              },
              "&:hover fieldset": {
                borderColor: theme.palette.primary.light,
              },
              "&.Mui-focused fieldset": {
                borderColor: theme.palette.primary.light,
              },
            },
            "& .MuiInputBase-input": {
              textAlign: "center",
            },
          }}
        />
      )}
    />
  );
};

export default CustomAutoComplete;
