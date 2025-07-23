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

/**
 * The Application context keeps track of all the clusters known to frugal IT.
 * If a cluster is selected as the current cluster, its namespaces will be
 * loaded.
 *
 * These two levels cluster and namespaces are shared among components.
 */
export interface ApplicationContextStruct {
  /**
   * Whether the sidebar is collapsed or not.
   */
  isSidebarCollapsed: boolean;

  /**
   * Whether the application is in dark mode or not.
   */
  darkMode: boolean;

  /**
   * Toggles the sidebar collapsed state.
   */
  toggleSidebar: () => void;

  /**
   * Toggles between dark and light mode.
   */
  toggleDarkMode: () => void;
}
