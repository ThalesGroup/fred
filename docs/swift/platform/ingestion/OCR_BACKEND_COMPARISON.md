# OCR Backend Comparison for PDF Ingestion

## Scope

This note compares the RapidOCR inference backend used by Docling during PDF ingestion:

- `openvino`
- `onnxruntime`

The benchmark was run on:

- input file: `knowledge-flow-backend/tests/assets/anssi-guide-recommendations-linux_configuration-fr-v1.2_0.pdf`
- document size: `997,307` bytes
- page count: `64`

The goal was to isolate the OCR backend impact while keeping the rest of the Docling pipeline identical.

## Configuration Used

### Medium

- Docling backend: `docling_parse`
- `do_ocr: true`
- `do_table_structure: true`
- `force_full_page_ocr: false`
- `process_images: false`
- `images_scale: 1.5`
- `generate_picture_images: false`

### Rich

- Docling backend: `docling_parse`
- `do_ocr: true`
- `do_table_structure: true`
- `force_full_page_ocr: false`
- `process_images: true`
- `images_scale: 2.0`
- `generate_picture_images: true`

## Results

| Case | Wall Time | Peak RSS | Avg CPU | Peak CPU | Markdown Output |
|---|---:|---:|---:|---:|---|
| Medium + OpenVINO | 81.92 s | 3.844 GiB | 5.00 cores | 11.03 cores | `target/backend-bench/medium_openvino.md` |
| Medium + ONNX Runtime | 87.55 s | 3.302 GiB | 5.21 cores | 12.88 cores | `target/backend-bench/medium_onnxruntime.md` |
| Rich + OpenVINO | 84.13 s | 3.967 GiB | 5.05 cores | 10.72 cores | `target/backend-bench/rich_openvino.md` |
| Rich + ONNX Runtime | 82.94 s | 3.599 GiB | 5.18 cores | 13.88 cores | `target/backend-bench/rich_onnxruntime.md` |

## Markdown Output Comparison

The generated Markdown was identical for both OCR backends within the same profile:

- `medium_openvino.md` and `medium_onnxruntime.md`
  - chars: `133,940`
  - words: `19,088`
  - SHA-256: `36056c8eed8dfb9ebaeebf43fe11b9618440d834dde5bd53dfbb7c4e1dc366bb`
- `rich_openvino.md` and `rich_onnxruntime.md`
  - chars: `137,720`
  - words: `19,718`
  - SHA-256: `bb635e16a0e13baead2036cf13e9e6b21e40d20cc31bad152052772d802b73b8`

This means the backend switch changed runtime characteristics, but not the final Markdown output for this document.

## Interpretation

For this benchmark, `openvino` was not the main reason for higher runtime cost.

What we observed instead:

- `openvino` was slightly faster than `onnxruntime` in `medium`
- `onnxruntime` was slightly faster than `openvino` in `rich`
- `onnxruntime` consistently used less peak RAM than `openvino`
- `onnxruntime` showed higher peak CPU bursts than `openvino`

In short:

- `openvino` tends to trade some extra memory for slightly smoother peak CPU behavior
- `onnxruntime` tends to use less memory but can spike CPU harder

For this PDF, the memory delta was meaningful:

- `medium`: about `0.54 GiB` lower with `onnxruntime`
- `rich`: about `0.37 GiB` lower with `onnxruntime`

## Why Is It So Heavy If the Docling Artifacts Are Small?

The disk size of the Docling and RapidOCR artifacts is not the main driver of runtime memory.

The heavy part comes from the in-memory working set created during inference and PDF processing:

1. PDF pages are rasterized into images before OCR can run.
   - This is especially expensive when `images_scale` is greater than `1.0`.
   - `rich` uses `images_scale: 2.0`, which increases pixel count significantly.

2. OCR does not operate on the compressed model files directly.
   - Models are loaded into runtime structures, execution graphs, and internal buffers.
   - Memory usage at runtime is much larger than the model file size on disk.

3. Intermediate tensors are created during detection, classification, and recognition.
   - RapidOCR runs several stages, not just a single pass.
   - Each stage creates activations, temporary arrays, and backend-specific work buffers.

4. Docling keeps a full document representation in memory.
   - OCR output, detected blocks, tables, pictures, and document structure coexist before export.

5. Markdown export is only the last step.
   - By the time `output.md` is written, the expensive work has already happened in memory.

6. `rich` adds image-related work on top of OCR.
   - `generate_picture_images: true`
   - `process_images: true`
   - this increases the in-memory payload even before any external vision call is considered

So the key distinction is:

- artifacts on disk are the static inputs
- runtime RAM is dominated by decoded page images, model execution buffers, tensors, and Docling document state

## Practical Takeaway

For this benchmark document:

- switching from `openvino` to `onnxruntime` reduced memory usage
- the reduction was visible in both `medium` and `rich`
- Markdown output quality was unchanged

This suggests that, if production memory pressure is the priority, `onnxruntime` is worth evaluating as a lower-RAM OCR backend for this workload.

However, the OCR backend is only one part of the story. The biggest structural cost still comes from:

- page rasterization
- OCR/tables pipeline
- high `images_scale`
- picture generation and image processing in `rich`
