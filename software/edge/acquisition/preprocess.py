import cv2
import numpy as np


def adjust_contrast(gray: np.ndarray, clip_limit: float = 2.0, tile: int = 8) -> np.ndarray:
    """CLAHE contrast adjustment for the AI branch (Poka-Yoke uses the raw frame)."""
    clahe = cv2.createCLAHE(clipLimit=clip_limit, tileGridSize=(tile, tile))
    return clahe.apply(gray)
