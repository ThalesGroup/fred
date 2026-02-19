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

import { useEffect, useState } from "react";
import { loadPermissions } from "../common/config";

// Hook to check permissions
export const usePermissions = () => {
  const [permissions, setPermissions] = useState<string[] | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    let mounted = true;
    (async () => {
      try {
        const perms = await loadPermissions();
        if (mounted) setPermissions(perms);
      } finally {
        if (mounted) setLoading(false);
      }
    })();
    return () => {
      mounted = false;
    };
  }, []);

  const can = (resource: string, action: string) => {
    const list = permissions ?? [];
    return list.some((p) => p.toLowerCase() === `${resource}:${action}`.toLowerCase());
  };

  const refreshPermissions = async () => {
    setLoading(true);
    try {
      const perms = await loadPermissions();
      setPermissions(perms);
    } finally {
      setLoading(false);
    }
  };

  return { permissions: permissions ?? [], loading, can, refreshPermissions };
};
