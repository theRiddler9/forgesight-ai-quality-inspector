# Camera and Replay Interface

**Status:** Software contract accepted for mock/replay work; physical camera geometry remains open.

## Purpose

Vision code consumes a frame source, not a camera library directly. The same inspection pipeline must run from a directory of recorded images and from the eventual UVC camera.

## Frame Packet

Every captured or replayed frame provides:

| Field | Type | Rule |
|---|---|---|
| `frame_id` | string | Unique within the source session |
| `captured_at` | UTC datetime | Original capture time or replay emission time |
| `source_id` | string | Stable camera or fixture-set identifier |
| `sequence_number` | non-negative integer | Strictly increasing per source session |
| `width` | positive integer | Pixel width |
| `height` | positive integer | Pixel height |
| `pixel_format` | enum | `BGR8` for the first implementation |
| `image` | image array | OpenCV-compatible unsigned 8-bit, three-channel array |
| `source_uri` | string | Camera URI or recorded fixture path |

Image bytes are passed in memory. Only the URI and SHA-256 reference enter the inspection event.

## Source Operations

Every frame source implements these behaviors:

1. `start()` opens resources and verifies readiness.
2. `capture()` returns one complete frame packet or a typed capture fault.
3. `health()` reports ready, degraded, or unavailable with a reason.
4. `close()` releases resources and is safe to call more than once.

## Source Types

- **Directory replay:** deterministic lexicographic ordering, optional repeat, no hidden augmentation.
- **UVC camera:** exposure, gain, focus, resolution, and frame rate are explicitly configured and logged.
- **Test fixture:** creates controlled arrays for behavior tests; it never enters benchmark or model-accuracy evidence.

## Fault Mapping

| Condition | Fault code | Inspection outcome |
|---|---|---|
| Source cannot start | `CAMERA_UNAVAILABLE` | RECHECK |
| Capture exceeds configured timeout | `CAPTURE_TIMEOUT` | RECHECK |
| Empty or unreadable frame | `INVALID_FRAME` | RECHECK |
| Wrong dimensions or pixel format | `FRAME_FORMAT_MISMATCH` | RECHECK |
| Repeated sequence number | `STALE_FRAME` | RECHECK |

No camera fault may produce PASS.

## Physical Parameters Still Requiring Approval

- Camera model and serial/source identifier scheme.
- Lens focal length.
- Capture resolution and frame rate.
- Camera height, field of view, and allowable part-position tolerance.
- Locked exposure, gain, focus, and LED PWM settings.

These values must be configuration-driven and approved before dataset capture.
