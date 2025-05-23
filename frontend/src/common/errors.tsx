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

export function getErrorMessage(err: any): string {
  if (typeof err === "string") {
    return err
  }
  if ("message" in err && err.message) {
    return err.message
  }
  if ("error_description" in err && err.error_description !== null) {
    return err.error_description
  }
  if ("data" in err && err.data !== null) {
    return getErrorMessage(err.data)
  }
  if ("error" in err && err.error !== null) {
    return getErrorMessage(err.error)
  }
  if ("status" in err && err.status) {
    return err.status
  }
  return JSON.stringify(err)
}

// This function is used to refresh a query without throwing an error if the query has not been started yet.
// This error is quite hard to anticipate and is not a real error, so we just ignore it.
export function safeRefresh(refresh: () => any) {
  try {
    refresh()
  } catch (e) {
    if (e instanceof Error && e.message === "Cannot refetch a query that has not been started yet.") {
      // Ignore this error
      console.log("Ignoring error", e)
    } else {
      throw e
    }
  }
}