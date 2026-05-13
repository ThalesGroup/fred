# Knowledge Flow Worker PDF Ingestion Benchmark

## Context

This benchmark was run locally against the ANSSI PDF:

`knowledge-flow-backend/tests/assets/anssi-guide-recommendations-linux_configuration-fr-v1.2_0.pdf`

Document characteristics:
- 64 pages
- 0.951 MiB (`997,307` bytes)
- PDF version 1.5

The benchmark was aligned with the production `knowledge-flow-worker` configuration you provided:

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

## Interpretation

### Memory

- `Fast` is lightweight and leaves a large safety margin under a `7 GiB` pod limit.
- `Medium` reaches about `3.8 GiB` for a single ingestion, which is significant but still below the pod limit.
- `Rich` reaches about `4.1 GiB` for a single ingestion, also below the `7 GiB` limit, but already consuming a large share of available pod memory.

### CPU

- `Medium` and `Rich` both average around `5` CPU cores locally during single ingestion.
- This is above the production worker CPU limit of `3.5` vCPU, so CPU throttling is likely in production.
- CPU throttling alone does not explain `OOMKilled`, but it may increase processing duration and contention.

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


## Recommended Next Step

The most useful follow-up would be a local **end-to-end ingestion benchmark on k3d**, with:
- real upload flow
- real worker pod observation
- memory tracking throughout the full workflow lifecycle

That would let us distinguish between:
- `Docling/OCR memory cost only`
- `full worker memory cost during actual ingestion`
