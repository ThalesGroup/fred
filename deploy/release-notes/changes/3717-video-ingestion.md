---
schema: 1
title: "Ingest audio and video files with their transcript and scene descriptions"
impact: none
configuration: production
configuration_reason: "The worker processing profiles register audio and video suffixes and gain an optional `video` sampling block with defaults; the chart values carry the same registrations."
no_action_reason: "Existing profiles keep working: the new suffixes and the `video` block have defaults, the Whisper model is already packaged in the worker image, and no database or upload limit changes."
---
## Applicability

Deployments that ingest documents with the Knowledge Flow worker. Chat dictation
also changes: the interface language is sent as a transcription hint and silence
is filtered.

## Prerequisites

Scene descriptions need a vision model admitted for the organization (image
description default model) and a profile with `process_images: true`. Without
one, videos keep their transcript only.

## Configuration

Every profile accepts `.mp3 .wav .ogg .flac .m4a .aac` (audio) and
`.mp4 .mkv .mov .webm .avi` (video). Each profile may set
`processing.profiles.<profile>.video`:

| Key | Default | Meaning |
| --- | --- | --- |
| `scene_threshold` | `0.03` | Share of pixels that must change to start a scene |
| `min_scene_seconds` | `3` | Shortest scene |
| `max_gap_seconds` | `30` | How often a still picture is compared again with its scene start; unchanged, it stays one scene |
| `max_scenes_per_minute` | `2` | Vision budget per minute of video; above it each equal slice keeps its strongest change |
| `max_scenes` | `90` | Absolute cap per video; `null` removes it |
| `frames_per_scene` | `3` | Frames tiled into the image of one scene |
| `parallel_descriptions` | `3` | Vision calls running at the same time per video |

`max_scenes_per_minute × max_gap_seconds` must be at least 60.

## Upgrade

Deploy normally. Transcription runs on the extraction workers' CPU: audio and video
files now use the fast and medium workers too, so watch their memory with long
recordings. Each running activity loads its own Whisper model.

## Validation

Upload a short interview video into a library on a profile with image description
and a vision model: the preview shows one section per scene with "À l'écran" and
"Transcription". On a fast profile the same file shows its timestamped transcript.

## Rollback

Use the normal rollback procedure; this change introduces no data migration.
Documents already ingested keep their Markdown.

## Limitations

Speakers are not distinguished. Uploads keep the existing 100 MiB ceiling, which
limits videos to short or compressed recordings. A very long video can still reach
the input activity timeout on slow vision models; lower `max_scenes` if it happens.
