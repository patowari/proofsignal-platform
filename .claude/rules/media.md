# Media pipeline rules

## Resource limits

Every limit is configurable (`MAX_IMAGE_BYTES`, `MAX_VIDEO_BYTES`,
`MAX_VIDEO_DURATION`, `MAX_VIDEO_RESOLUTION`, `MAX_KEYFRAMES`,
`MAX_TRANSCRIPT_CHARS`). Never hardcode generous limits. Every media job has a
wall-clock timeout; every subprocess has its own timeout and is killed on expiry.

## FFmpeg

Invoke via argv list with `shell=False`. User values (filenames, captions) never
appear in an ffmpeg argument except as an input path we generated ourselves.
Prefix untrusted-looking paths so they cannot be parsed as flags. Probe with
`ffprobe -v quiet -print_format json` and validate the JSON before use — a
malformed file must raise, not produce partial garbage.

Reject before decoding: duration over limit, resolution over limit, stream count
anomalies, and container/codec mismatches with the declared type.

## Sampling

Never feed every frame to a vision model. Scene-change detection selects
candidates, capped at `MAX_KEYFRAMES`, deduplicated by perceptual hash before any
model call.

## Integrity vs context

`MediaAnalysis` reports integrity signals (EXIF, hashes, dimensions, manipulation
heuristics) separately from contextual claim analysis. Never merge them into one
score. We do not have reverse image search — say so; state that matching is
limited to our own indexed corpus, and never invent an original source.

## Degradation

OCR and speech-to-text are optional. If Tesseract or faster-whisper is missing the
stage records `unavailable` with a reason and the pipeline continues on the
remaining signals. A missing tool is never reported as "no text found".
