"""
Zona de interes (ROI) de la escena.

El rectangulo se marca con el mouse sobre la foto 1 (ya corregida la
distorsion) desde la ventana principal. La reconstruccion busca
keypoints solo dentro de esa zona, ampliada por ROI_MARGIN, en las 3
fotos. Asi el fondo no aporta coincidencias falsas.
"""

import json
import os

import cv2
import numpy as np

from config import CALIBRATION_FILE, IMAGE1, ROI_FILE, ROI_MARGIN


def load_roi():
    """Devuelve (x, y, w, h) guardado, o None si no hay zona."""
    if not os.path.exists(ROI_FILE):
        return None

    with open(ROI_FILE) as f:
        data = json.load(f)

    return data["x"], data["y"], data["w"], data["h"]


def save_roi(x, y, w, h):
    with open(ROI_FILE, "w") as f:
        json.dump({"x": int(x), "y": int(y), "w": int(w), "h": int(h)}, f)


def clear_roi():
    if os.path.exists(ROI_FILE):
        os.remove(ROI_FILE)


def reference_image():
    """Foto 1 corregida (la que usa la reconstruccion), o None."""
    img = cv2.imread(IMAGE1) if os.path.exists(IMAGE1) else None

    if img is not None and os.path.exists(CALIBRATION_FILE):
        calib = np.load(CALIBRATION_FILE)
        img = cv2.undistort(img, calib["K"], calib["dist"])

    return img


def roi_mask(shape):
    """
    Mascara para SIFT con la zona ampliada por ROI_MARGIN.
    Devuelve None (imagen completa) si no hay zona definida.
    """
    roi = load_roi()

    if roi is None:
        return None

    height, width = shape[:2]
    x, y, w, h = roi

    mx = int(ROI_MARGIN * width)
    my = int(ROI_MARGIN * height)

    x0, y0 = max(0, x - mx), max(0, y - my)
    x1, y1 = min(width, x + w + mx), min(height, y + h + my)

    mask = np.zeros((height, width), dtype=np.uint8)
    mask[y0:y1, x0:x1] = 255

    return mask
