"""Regenerate the explicitly synthetic Stage 2 replay images."""
from pathlib import Path

import cv2

from software.edge.acquisition.synthetic import make_synthetic_part


def main() -> None:
    destination = Path(__file__).parent / "images"
    destination.mkdir(exist_ok=True)
    profiles = {
        "clean": {},
        "heavy_burr": {},  # burr outcome comes from scenario metadata, not these pixels
        "uncertain_burr": {},
        "missing_hole": {"hole": False},
        "no_part": {"part_present": False},
        "misaligned": {"center": (760.0, 480.0)},
    }
    for name, options in profiles.items():
        image = make_synthetic_part(noise_std=0.0, **options)
        if not cv2.imwrite(str(destination / f"{name}.png"), image):
            raise RuntimeError(f"could not write synthetic fixture {name}")


if __name__ == "__main__":
    main()
