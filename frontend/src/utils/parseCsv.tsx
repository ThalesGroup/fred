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

import Papa from "papaparse";
import { useState, useEffect } from "react";

// Function to parse the CSV
const parseCSV = (csvData) => {
  const parsedData = Papa.parse(csvData, {
    header: true,
    skipEmptyLines: true,
  }).data;

  return parsedData.map((row) => ({
    timestamp: row["timestamp"],
    renewablePercentage: parseFloat(row["Renewable Percentage"]),
    lowCarbonPercentage: parseFloat(row["Low Carbon Percentage"]),
    carbonIntensity: parseFloat(row["Carbon Intensity gCO₂eq/kWh (direct)"]),
  }));
};

// Example component using CSV parsing
const EnergyDataComponent = () => {
  const [data, setData] = useState([]);
  const csvData = `timestamp,Country,Zone Name,Zone Id,Carbon Intensity gCO₂eq/kWh (direct),Carbon Intensity gCO₂eq/kWh (LCA),Low Carbon Percentage,Renewable Percentage,Data Source,Data Estimated,Data Estimation Method
2024-01-01 00:00:00,France,France,FR,35.34,56.64,92.78,40.96,opendata.reseaux-energies.fr,False,
2024-01-01 01:00:00,France,France,FR,36.53,58.17,92.56,40.1,opendata.reseaux-energies.fr,False,
2024-01-01 02:00:00,France,France,FR,35.16,56.65,92.67,39.42,opendata.reseaux-energies.fr,False,
2024-01-01 03:00:00,France,France,FR,36.15,57.9,92.49,38.88,opendata.reseaux-energies.fr,False,
2024-01-01 04:00:00,France,France,FR,36.0,57.72,92.47,37.92,opendata.reseaux-energies.fr,False,
2024-01-01 05:00:00,France,France,FR,39.31,61.81,91.91,37.69,opendata.reseaux-energies.fr,False,
2024-01-01 06:00:00,France,France,FR,40.99,63.92,91.55,37.76,opendata.reseaux-energies.fr,False,
2024-01-01 07:00:00,France,France,FR,42.44,65.8,91.29,37.39,opendata.reseaux-energies.fr,False,
2024-01-01 08:00:00,France,France,FR,39.62,62.76,91.73,39.37,opendata.reseaux-energies.fr,False,`;

  useEffect(() => {
    const plottableData = parseCSV(csvData);
    setData(plottableData);
  }, []);

  return (
    <div>
      <h2>Energy Data Parsed</h2>
      {/* Now you have your data in `data` state */}
      <pre>{JSON.stringify(data, null, 2)}</pre>
    </div>
  );
};

export default EnergyDataComponent;
