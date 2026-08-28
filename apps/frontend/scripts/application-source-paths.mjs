// Copyright Thales 2026
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

import { existsSync, lstatSync, readdirSync } from "node:fs";
import { resolve } from "node:path";

function containsSymbolicLink(directory) {
  for (const entry of readdirSync(directory, { withFileTypes: true })) {
    if (entry.isSymbolicLink()) {
      return true;
    }
    if (entry.isDirectory() && containsSymbolicLink(resolve(directory, entry.name))) {
      return true;
    }
  }
  return false;
}

export function discoverApplicationFrontendDirectories(applicationsDirectory) {
  if (!existsSync(applicationsDirectory)) {
    return [];
  }

  const frontendDirectories = [];
  const packages = readdirSync(applicationsDirectory, { withFileTypes: true });
  for (const applicationPackage of packages.sort((left, right) => left.name.localeCompare(right.name))) {
    if (!applicationPackage.isDirectory()) {
      continue;
    }
    const frontendDirectory = resolve(applicationsDirectory, applicationPackage.name, "frontend");
    if (!existsSync(frontendDirectory)) {
      continue;
    }
    const stats = lstatSync(frontendDirectory);
    if (stats.isDirectory() && !stats.isSymbolicLink() && !containsSymbolicLink(frontendDirectory)) {
      frontendDirectories.push(frontendDirectory);
    }
  }
  return frontendDirectories;
}
