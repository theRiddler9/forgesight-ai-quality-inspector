# Dataset manifest and annotation guide

Keep real images and annotations in an ignored directory such as `data/datasets/<version>/`; commit only code and small synthetic test logic. The strict manifest in `software/dataset/manifest.py` records dataset version and, per image: ID, source, license, `profile@version`, capture session, physical part and batch IDs when known, relative image and annotation paths, SHA-256, pixel dimensions, annotation format, labels, review status, and split. Capture the source license exactly as supplied; a nonempty field is not a grant of rights.

Local intake accepts a directory or an explicitly supplied ZIP archive. It validates paths, symlinks, size, decoding, and metadata before atomically publishing a **new** destination; raw files are addressed by content hash and never overwritten. Intake does not fetch URLs or execute archive contents. Its report records the license claim with `provenance_verified: false`; a human must verify ownership or terms. Intake leaves part/batch IDs, annotations, and review status unresolved for later curation.

Supported annotation format `bbox_json_v1` is JSON of the form `{"boxes":[{"label":"heavy_burr","xywh_normalized":[0.1,0.2,0.3,0.4]}]}`. Coordinates are fractions of image width/height, originate at the upper left, and must enclose the visible defect. Empty boxes plus empty `defect_labels` represent a reviewed clean image. Boxes are not physical dimensions. Save ambiguous/occluded observations for review instead of forcing a heavy-burr label. Record poor focus, glare, partial visibility, and lighting changes in capture-session notes before review. At least two reviewers should resolve disputed boundary cases before they enter a held-out set.

## Provisional labels

| Label | Visual annotation rule | Limitation |
|---|---|---|
| Clean edge | No visible attached protrusion on a clearly visible inspected edge | Does not prove physical tolerance compliance |
| Minor burr | Visible edge protrusion judged minor under a **future approved visual guide** | No physical size threshold established |
| Heavy burr | Visible pronounced attached edge protrusion judged severe under a **future approved visual guide** | Requires manufacturing tolerance agreement and representative real samples |
| Ambiguous edge condition | Glare, occlusion, blur, or borderline protrusion prevents a reliable label | Exclude from definitive test labels until reviewed |
| Other surface defect | Visible non-burr mark such as scratch/crack/contamination | Use a more specific class only after label policy approval |
| Geometry defect | Missing hole, wrong contour, or mispositioned part | Record separately from edge-burr boxes and Poka-Yoke outcome |

RGB images reveal appearance from a particular camera and lighting setup. They cannot establish burr height, sharpness, material integrity, or tolerance violation in millimeters without calibrated imaging and independent measurements. The label guide is provisional until a manufacturing partner approves acceptable and unacceptable examples.

## Utilities

From the repository root after installing `software/requirements-dev.txt`:

```sh
python -m software.dataset validate data/datasets/v1/manifest.json
python -m software.dataset report data/datasets/v1/manifest.json --group-by physical_part_id
python -m software.dataset split data/datasets/v1/manifest.json --group-by physical_part_id --seed 42 --fractions 0.7 0.15 0.15 --output data/datasets/v1/split-manifest.json
python -m software.dataset import path/to/approved-local-images --output data/datasets/v2 --dataset-version 2.0.0 --profile metal-plate-v1@1.0.0 --source-name team-capture --source-license team-owned --capture-session session-01 --dry-run
python -m software.dataset export-yolo data/datasets/v1/split-manifest.json --class-map data/datasets/v1/class-map.json --output data/datasets/v1/yolo-export --dry-run
```

Remove `--dry-run` only after reviewing the reported source, license claim, and destination. For ZIP intake, give a local `.zip` path explicitly. Add verified physical part IDs and reviewed annotations to a **new versioned manifest** before splitting. A class-map file is JSON such as `{"heavy_burr":0}`; the label must match the reviewed annotation vocabulary and the selected model profile.

`validate` checks image hashes, decoding, dimensions, annotation shape, bounds, and label agreement. `report` counts profiles, labels, reviews, splits, exact SHA duplicates, and explicit cross-split part/session/image leakage. `split` connects shared physical parts, capture sessions, and identical hashes before assigning whole groups. It records seed, fractions, grouping rule, and input hash, and refuses to regenerate assigned splits. The requested fractions apply approximately by **group count**, so class balance and image ratios require manual review. Training preflight also detects images with identical decoded pixels even if file bytes differ. These checks do not prove the absence of near duplicates or unknown part relationships. A split audit fails when part/session IDs are missing or validation/test annotations are unreviewed. Output paths must be new; source files are not overwritten.

`export-yolo` requires every image to be reviewed with a canonical annotation JSON, including `{"boxes":[]}` for a clean edge. It rejects unknown classes, duplicate/invalid boxes, missing annotations, and unassigned splits. It copies images and derived YOLO labels to a new directory, retains the original JSON, and writes a reviewable export manifest. An image-level label alone is insufficient for detector localization training.
