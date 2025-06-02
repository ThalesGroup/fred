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

export function extractHttpErrorMessage(error: any): string {
  let httpErrorMsg = "Unknown error";
  if (error.status) {
    if (error.status == 502) {
      httpErrorMsg = `Bad Gateway: ${error.status} : the server is down.`;
    } else if (error.status == 404) {
      httpErrorMsg = `Not Found: ${error.status}`;
    } else if (error.status == 401) {
      httpErrorMsg = `Unauthorized: ${error.status}`;
    } else if (error.status == 403) {
      httpErrorMsg = `Forbidden: ${error.status}`;
    } else if (error.status == 500) {
      httpErrorMsg = `Internal Server Error: ${error.status}`;
    } else if (error.status == 503) {
      httpErrorMsg = `Service Unavailable: ${error.status}`;
    } else {
      httpErrorMsg = `Unknown error: ${error.status}`;
    }
  }
  if (!error.data) {
    return httpErrorMsg;
  }
  return `HTTP Error: ${httpErrorMsg} - ${error.data?.message || "Unknown error"}`;
}
