# Dataset manifest and annotation guide

Keep real images and annotations in an ignored directory such as `data/datasets/<version>/`; commit only code and small synthetic test logic. The strict manifest in `software/dataset/manifest.py` records dataset version and, per image: ID, source, license, `profile@version`, capture session, physical part and batch IDs when known, relative image and annotation paths, SHA-256, pixel dimensions, annotation format, labels, review status, and split. Capture the source license exactly as supplied; a nonempty field is not a grant of rights.

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
python -m software.dataset split data/datasets/v1/manifest.json --group-by physical_part_id --seed 42 --output data/datasets/v1/split-manifest.json
```

`validate` checks image hashes, decoding, dimensions, annotation shape, bounds, and label agreement. `report` counts profiles, labels, reviews, splits, exact SHA duplicates, cross-split duplicates, and group leakage. `split` allocates complete groups deterministically and refuses missing grouping IDs or fewer than three independent groups. The requested fractions apply approximately by **group count**, so class balance and image ratios require manual review. Exact duplicate detection does not detect near-duplicates. An output path must be new; no source manifest is overwritten. Use physical part IDs where available; session, batch, or source grouping provides weaker protection. If no reliable grouping key exists, do not claim a leakage-free evaluation.
