# Knowledge Flow Worker PDF Ingestion Benchmark

## Table of Contents

- [Context](#context)
- [Profile Configuration Used](#profile-configuration-used)
- [Important Scope Note](#important-scope-note)
- [Single Ingestion Results](#single-ingestion-results)
- [Parallel Ingestion Results](#parallel-ingestion-results)
- [Rich `images_scale` Sensitivity](#rich-imagesscale-sensitivity)
- [Rich PDF Backend Comparison](#rich-pdf-backend-comparison)
- [Rich Threaded Pipeline Tuning](#rich-threaded-pipeline-tuning)
- [Rich Optimized Tuning: `docling_parse` vs `pypdfium2`](#rich-optimized-tuning-docling_parse-vs-pypdfium2)
- [Rich Current vs Optimized Configuration](#rich-current-vs-optimized-configuration)
- [Rich `AcceleratorOptions(num_threads=1)` Impact](#rich-acceleratoroptionsnum_threads1-impact)
- [Rich Local vs Remote OCR Without Image Description](#rich-local-vs-remote-ocr-without-image-description)
- [Interpretation](#interpretation)
- [Recommended Next Step](#recommended-next-step)

## Context

This benchmark was run locally against the ANSSI PDF:

`knowledge-flow-backend/tests/assets/anssi-guide-recommendations-linux_configuration-fr-v1.2_0.pdf`

Document characteristics:
- 64 pages
- 0.951 MiB (`997,307` bytes)
- PDF version 1.5

The benchmark was aligned with the production `knowledge-flow-worker` provided configuration:

- Worker memory limit: `7 GiB`
- Worker CPU limit: `3500m` (`3.5` vCPU)
- Temporal ingestion concurrency:
  - `ingestion_workflow_parallelism: 1`
  - `ingestion_max_concurrent_workflow_tasks: 1`
  - `ingestion_max_concurrent_activities: 1`

## Profile Configuration Used

### Fast

- Backend: `pypdfium2`
- OCR: disabled
- Table structure: disabled
- `force_full_page_ocr`: not applicable

### Medium

- Backend: `docling_parse`
- OCR: enabled
- Table structure: enabled
- `force_full_page_ocr: false`
- `process_images: false`

### Rich

- Backend: `docling_parse`
- OCR: enabled
- Table structure: enabled
- `force_full_page_ocr: false`
- `images_scale: 2.0`
- `generate_picture_images: true`
- `process_images: true`

## Important Scope Note

These measurements cover the PDF-to-Markdown ingestion stage, focusing on the Docling/OCR processing path.

They do **not** represent the full end-to-end workflow cost including:
- embeddings generation
- vector storage / OpenSearch writes
- downstream output processing overhead

As a result, this benchmark is well suited to validate whether Docling/OCR is a major memory consumer, but it is not yet a full production workflow benchmark.

## Single Ingestion Results

| Mode | Peak RSS | Wall Time | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Fast | 797.8 MiB | 8.41 s | 1.40 cores | 9.29 cores |
| Medium | 3.825 GiB | 82.93 s | 4.97 cores | 11.14 cores |
| Rich | 4.083 GiB | 85.93 s | 4.97 cores | 12.78 cores |

## Parallel Ingestion Results

### 2 simultaneous ingestions

| Mode | Peak Aggregate RSS | Wall Time | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Fast x2 | 1.557 GiB | 8.82 s | 2.38 cores | 8.44 cores |
| Medium x2 | 7.503 GiB | 118.01 s | 10.07 cores | 15.37 cores |
| Rich x2 | 7.826 GiB | 127.47 s | 9.84 cores | 15.33 cores |

### 3 simultaneous ingestions

| Mode | Peak Aggregate RSS | Wall Time | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Fast x3 | 2.337 GiB | 9.21 s | 3.58 cores | 13.68 cores |
| Medium x3 | 11.409 GiB | 186.87 s | 12.83 cores | 15.62 cores |
| Rich x3 | 11.868 GiB | 191.80 s | 12.76 cores | 15.57 cores |

## Rich `images_scale` Sensitivity

An additional `rich` benchmark was run on the same ANSSI PDF with the same `openvino` OCR backend, comparing:

- `images_scale=2.0`
- `images_scale=1.0`

| Setting | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| `images_scale=2.0` | 84.13 s | 3.967 GiB | 5.05 cores | 10.72 cores |
| `images_scale=1.0` | 87.54 s | 3.392 GiB | 4.95 cores | 12.88 cores |

Observed delta when moving from `2.0` to `1.0`:

- memory: `-0.575 GiB`
- wall time: `+3.41 s`
- average CPU: `-0.10` cores

The generated Markdown remained identical for this document.

This makes `images_scale` a strong tuning lever for reducing worker memory pressure in `rich` mode.

## Rich PDF Backend Comparison

An additional `rich` benchmark was run with:

- OCR backend fixed to `openvino`
- `images_scale=1.0`
- two PDF backends:
  - `docling_parse`
  - `pypdfium2`

| PDF Backend | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| `docling_parse` | 89.74 s | 3.409 GiB | 4.88 cores | 12.85 cores |
| `pypdfium2` | 81.32 s | 2.938 GiB | 5.30 cores | 13.53 cores |

Observed delta when moving from `docling_parse` to `pypdfium2`:

- memory: `-0.471 GiB`
- wall time: `-8.42 s`
- average CPU: `+0.42` cores

However, unlike the `images_scale` comparison, the generated Markdown was **not** identical between the two backends.

This means `pypdfium2` is promising as a lower-memory alternative for `rich`, but it should be treated as a quality/performance tradeoff rather than a drop-in replacement.

## Rich Threaded Pipeline Tuning

An additional `rich` benchmark was run with:

- OCR backend fixed to `openvino`
- PDF backend fixed to `docling_parse`
- `images_scale=1.0`
- two threaded pipeline settings:
  - Docling defaults: `ocr_batch_size=4`, `layout_batch_size=4`, `table_batch_size=4`, `queue_max_size=100`, `batch_polling_interval_seconds=0.5`
  - conservative tuning: `ocr_batch_size=1`, `layout_batch_size=1`, `table_batch_size=1`, `queue_max_size=1`, `batch_polling_interval_seconds=0.05`

| Threaded Setting | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Docling defaults | 74.20 s | 3.457 GiB | 5.33 cores | 12.38 cores |
| Conservative tuning | 67.79 s | 2.958 GiB | 4.79 cores | 10.54 cores |

Observed delta when moving from Docling defaults to conservative tuning:

- memory: `-0.499 GiB`
- wall time: `-6.41 s`
- average CPU: `-0.54` cores
- peak CPU: `-1.84` cores

The generated Markdown remained identical for this document.

This suggests that for this workload, the biggest gain does not come from switching to `ThreadedPdfPipelineOptions` as a type, but from explicitly tuning the threaded pipeline's batch sizes and queue depth to reduce in-flight page buffering.

## Rich Optimized Tuning: `docling_parse` vs `pypdfium2`

An additional `rich` benchmark was run on the same ANSSI PDF to compare the two PDF backends under the same optimized local OCR tuning:

- `ocr_backend=openvino`
- `force_full_page_ocr=false`
- `images_scale=1.0`
- `ocr_batch_size=1`
- `layout_batch_size=1`
- `table_batch_size=1`
- `queue_max_size=1`
- `batch_polling_interval_seconds=0.05`
- no image description

| PDF Backend | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| `docling_parse` | 108.83 s | 2.558 GiB | 4.50 cores | 10.19 cores |
| `pypdfium2` | 90.57 s | 2.654 GiB | 5.11 cores | 10.24 cores |

Observed delta when moving from optimized `docling_parse` to optimized `pypdfium2`:

- memory: `+0.096 GiB`
- wall time: `-18.26 s`
- average CPU: `+0.61` cores
- peak CPU: `+0.05` cores

The generated Markdown was not identical between the two backends (`133,871` vs `135,006` characters).

This means that with the optimized threaded tuning already in place, `pypdfium2` is faster, but it is no longer the lower-memory option on this document. It should still be treated as a quality/performance tradeoff rather than a drop-in replacement.

## Rich `queue_max_size` 1 vs 5

An additional `rich` benchmark was run on the same ANSSI PDF to isolate the impact of raising `queue_max_size` from `1` to `5`, while keeping the rest of the optimized local OCR configuration unchanged:

- `backend=docling_parse`
- `ocr_backend=openvino`
- `force_full_page_ocr=false`
- `images_scale=1.0`
- `ocr_batch_size=1`
- `layout_batch_size=1`
- `table_batch_size=1`
- `batch_polling_interval_seconds=0.05`
- no image description

| `queue_max_size` | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| `1` | 66.70 s | 2.557 GiB | 4.75 cores | 9.94 cores |
| `5` | 64.91 s | 2.715 GiB | 5.28 cores | 13.59 cores |

Observed delta when moving from `1` to `5`:

- memory: `+0.158 GiB`
- wall time: `-1.78 s`
- average CPU: `+0.53` cores
- peak CPU: `+3.65` cores

The generated Markdown remained identical for this document (`133,940` characters).

This means `queue_max_size=5` is a reasonable throughput-oriented compromise if a small memory increase is acceptable. It is slightly faster than `1`, but it also increases both memory and CPU usage.

## Rich Current vs Optimized Configuration

An additional end-to-end `rich` comparison was run on the same ANSSI PDF to combine the improvements that preserved output fidelity in previous experiments.

Current `rich` configuration:

- `backend=docling_parse`
- `ocr_backend=openvino`
- `force_full_page_ocr=false`
- `images_scale=2.0`
- `ocr_batch_size=4`
- `layout_batch_size=4`
- `table_batch_size=4`
- `queue_max_size=100`
- `batch_polling_interval_seconds=0.5`

Optimized `rich` configuration:

- `backend=docling_parse`
- `ocr_backend=openvino`
- `force_full_page_ocr=false`
- `images_scale=1.0`
- `ocr_batch_size=1`
- `layout_batch_size=1`
- `table_batch_size=1`
- `queue_max_size=1`
- `batch_polling_interval_seconds=0.05`

| Rich Configuration | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Current | 71.77 s | 4.061 GiB | 5.40 cores | 11.04 cores |
| Optimized | 70.77 s | 3.358 GiB | 4.92 cores | 10.64 cores |

Observed delta when moving from current to optimized:

- memory: `-0.703 GiB`
- wall time: `-1.00 s`
- average CPU: `-0.48` cores
- peak CPU: `-0.40` cores

The generated Markdown remained identical for this document.

This is the strongest output-safe tuning combination found so far on this workload.

## Rich `AcceleratorOptions(num_threads=1)` Impact

An additional `rich` benchmark was run on the same ANSSI PDF to isolate the effect of forcing Docling accelerator threads to `1` while keeping the current production-like `rich` configuration unchanged otherwise.

Compared configurations:

- current production-like `rich`
- current production-like `rich` + `AcceleratorOptions(num_threads=1)`

| Rich Configuration | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Current | 71.57 s | 4.120 GiB | 5.45 cores | 12.23 cores |
| Current + `num_threads=1` | 160.77 s | 4.725 GiB | 1.48 cores | 7.16 cores |

Observed delta when forcing `num_threads=1`:

- memory: `+0.605 GiB`
- wall time: `+89.20 s`
- average CPU: `-3.97` cores
- peak CPU: `-5.07` cores

The generated Markdown remained identical for this document.

This means `num_threads=1` is effective if the goal is only to clamp CPU usage, but it is a poor tradeoff for this workload because it significantly increases latency and also increases peak memory usage.

## Rich Local vs Remote OCR Without Image Description

An additional `rich` benchmark was run on the same ANSSI PDF with `process_images=false` to isolate OCR/parsing costs and avoid mixing in image-description API latency.

Compared configurations:

- current production-like local OCR:
  - `backend=docling_parse`
  - `ocr_backend=openvino`
  - `images_scale=2.0`
  - `ocr_batch_size=4`
  - `layout_batch_size=4`
  - `table_batch_size=4`
  - `queue_max_size=100`
  - `batch_polling_interval_seconds=0.5`
- optimized local OCR:
  - `backend=docling_parse`
  - `ocr_backend=openvino`
  - `images_scale=1.0`
  - `ocr_batch_size=1`
  - `layout_batch_size=1`
  - `table_batch_size=1`
  - `queue_max_size=1`
  - `batch_polling_interval_seconds=0.05`
- remote OCR:
  - same `rich` profile
  - local Docling OCR bypassed through `ocr_model`
  - no image description

| Rich Configuration | Wall Time | Peak RSS | Avg CPU | Peak CPU |
|---|---:|---:|---:|---:|
| Current local OCR | 79.42 s | 3.945 GiB | 5.39 cores | 11.36 cores |
| Optimized local OCR | 73.57 s | 3.325 GiB | 4.86 cores | 10.29 cores |
| Remote OCR | 5.86 s | 1.551 GiB | 0.12 cores | 0.10 cores |

Observed deltas:

- optimized local vs current local:
  - memory: `-0.620 GiB`
  - wall time: `-5.85 s`
  - average CPU: `-0.53` cores
  - peak CPU: `-1.06` cores
- remote OCR vs current local:
  - memory: `-2.394 GiB`
  - wall time: `-73.55 s`
  - average CPU: `-5.27` cores
  - peak CPU: `-11.26` cores

In practical terms, moving from the current local OCR path to remote OCR reduced ingestion time from `79.42 s` to `5.86 s`, which is a **13.5x speed-up** on this document and saves about **92.6%** of the wall time.

The optimized local OCR configuration preserves the same Markdown size as the current local OCR run on this document (`133,940` characters), while remote OCR produced a smaller Markdown output (`119,500` characters), which suggests a real output-shape difference even though the performance gains are substantial.

## Interpretation

### Memory

- `Fast` is lightweight and leaves a large safety margin under a `7 GiB` pod limit.
- `Medium` reaches about `3.8 GiB` for a single ingestion, which is significant but still below the pod limit.
- `Rich` reaches about `4.1 GiB` for a single ingestion, also below the `7 GiB` limit, but already consuming a large share of available pod memory.

### CPU

- `Medium` and `Rich` both average around `5` CPU cores locally during single ingestion.
- This is above the production worker CPU limit of `3.5` vCPU, so CPU throttling is likely in production.
- CPU throttling alone does not explain `OOMKilled` on Kubernetes pods, but it may increase processing duration and contention.

### Parallelism

The production worker configuration is explicitly serialized:

- `ingestion_workflow_parallelism = 1`
- `ingestion_max_concurrent_workflow_tasks = 1`
- `ingestion_max_concurrent_activities = 1`

Because of that, the `x2` and `x3` local parallel runs should **not** be interpreted as expected per-pod production behavior. In production, multiple concurrent ingestions should normally spread across multiple worker pods rather than stack inside a single worker pod.

Those parallel results are therefore more useful as:
- overall fleet-capacity indicators
- upper-bound stress measurements
- evidence that `medium` and `rich` scale poorly in aggregate memory usage
