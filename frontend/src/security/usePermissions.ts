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

import { useCallback, useMemo } from "react";
import { useFrontendBootstrap } from "../hooks/useFrontendBootstrap";

/**
 * Read the flattened frontend permission summary from control-plane bootstrap.
 *
 * Why this hook exists:
 * - route guards and UI affordances should use the same bootstrap-owned
 *   permission list instead of triggering a second legacy permissions call
 *
 * How to use it:
 * - call from components or guards that need `resource:action` checks
 * - use `loading` to avoid false negatives while bootstrap is still resolving
 *
 * Example:
 * - `const { can, loading } = usePermissions();`
 */
export const usePermissions = () => {
  const { permissionItems, isLoading, refetch } = useFrontendBootstrap();

  const permissions = useMemo(() => permissionItems, [permissionItems]);

  const can = useCallback(
    (resource: string, action: string) => {
      const expected = `${resource}:${action}`.toLowerCase();
      return permissions.some((permission) => permission.toLowerCase() === expected);
    },
    [permissions],
  );

  const refreshPermissions = useCallback(async () => {
    await refetch();
  }, [refetch]);

  return { permissions, loading: isLoading, can, refreshPermissions };
};
