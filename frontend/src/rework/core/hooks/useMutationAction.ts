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

interface MutationActionOptions<T> {
  action: () => Promise<T>;
  onError: (error: unknown) => void;
  onSuccess?: (result: T) => void;
}

export function useMutationAction() {
  const runMutationAction = async <T>({ action, onError, onSuccess }: MutationActionOptions<T>): Promise<T | null> => {
    try {
      const result = await action();
      onSuccess?.(result);
      return result;
    } catch (error) {
      onError(error);
      return null;
    }
  };

  return { runMutationAction };
}
