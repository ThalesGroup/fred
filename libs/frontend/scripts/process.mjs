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

import { execFile, spawn } from "node:child_process";
import { promisify } from "node:util";

const execFileAsync = promisify(execFile);

export async function run(command, arguments_, options = {}) {
  if (options.stdio === "inherit") {
    await new Promise((resolve, reject) => {
      const child = spawn(command, arguments_, options);
      child.once("error", reject);
      child.once("exit", (code, signal) => {
        if (code === 0) resolve();
        else {
          const error = new Error(
            `${command} ${arguments_.join(" ")} failed${signal ? ` with signal ${signal}` : ` with exit code ${code}`}`,
          );
          error.exitCode = code;
          reject(error);
        }
      });
    });
    return { stdout: "", stderr: "" };
  }
  try {
    return await execFileAsync(command, arguments_, {
      encoding: "utf8",
      maxBuffer: 10 * 1024 * 1024,
      ...options,
    });
  } catch (error) {
    const detail = [error.stdout, error.stderr]
      .filter(Boolean)
      .join("\n")
      .trim();
    throw new Error(
      `${command} ${arguments_.join(" ")} failed${detail ? `:\n${detail}` : ""}`,
      {
        cause: error,
      },
    );
  }
}
