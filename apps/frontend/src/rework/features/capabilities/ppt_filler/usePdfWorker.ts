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

// One pdf.js module worker per react-pdf <Document> mount. A port shared across
// remounts throws "PDFWorker.fromPort - the worker is being destroyed" when the
// next mount races the previous unmount's destroy(); `workerSrc` alone yields a
// fake worker that fails to import the bundled asset.

import { useEffect, useMemo, useRef } from "react";
import { pdfjs } from "react-pdf";

// Resolved by Vite to the bundled pdf.js worker asset.
const pdfWorkerUrl = new URL("pdfjs-dist/build/pdf.worker.min.mjs", import.meta.url);

/** Provision a fresh worker for each `remountKey` (the <Document> key) while
 *  `active`, and terminate it once it is orphaned or the caller unmounts. */
export function usePdfWorker(remountKey: string, active: boolean): void {
  // useMemo runs during render, before the child <Document> reads GlobalWorkerOptions.
  const workerRef = useRef<Worker | null>(null);
  useMemo(() => {
    if (!active) {
      // Releasing the port lets the outgoing worker's cleanup see itself orphaned.
      pdfjs.GlobalWorkerOptions.workerPort = null;
      workerRef.current = null;
      return;
    }
    if (typeof Worker === "undefined") {
      pdfjs.GlobalWorkerOptions.workerSrc = pdfWorkerUrl.toString();
      workerRef.current = null;
      return;
    }
    const worker = new Worker(pdfWorkerUrl, { type: "module" });
    workerRef.current = worker;
    pdfjs.GlobalWorkerOptions.workerPort = worker;
  }, [remountKey]);

  // StrictMode replays mount/cleanup/mount synchronously: this tells a final unmount apart.
  const isAliveRef = useRef(true);
  useEffect(() => {
    isAliveRef.current = true;
    return () => {
      isAliveRef.current = false;
    };
  }, []);

  // Terminate an orphaned worker now; otherwise wait one tick, so a StrictMode
  // remount or another consumer's port swap wins before a final-unmount check.
  useEffect(() => {
    const worker = workerRef.current;
    return () => {
      if (!worker) return;
      if (pdfjs.GlobalWorkerOptions.workerPort !== worker) {
        worker.terminate();
        return;
      }
      setTimeout(() => {
        if (pdfjs.GlobalWorkerOptions.workerPort !== worker || !isAliveRef.current) {
          worker.terminate();
        }
      }, 0);
    };
  }, [remountKey]);
}
