"""
Captura en vivo de fotos del tablero para la calibracion.

Logica de la sesion de captura, sin interfaz propia: la ventana principal
(main.py) muestra el video, llama a process() en cada frame y a capture()
cuando el usuario guarda una foto.
"""

import glob
import os

import cv2

from config import (
    CALIBRATION_IMAGES_DIR,
    CAPTURE_HEIGHT,
    CAPTURE_WIDTH,
    CHECKERBOARD,
)

MIN_IMAGES = 8

# Resoluciones a probar: la configurada y una alternativa si no entrega imagen
CAMERA_SIZES = [(CAPTURE_WIDTH, CAPTURE_HEIGHT), (640, 480)]

TITLE = "Captura de calibracion"

GUIDE = [
    "- Tablero impreso o en pantalla,",
    "  plano y completo en la imagen.",
    "- Que se vea grande: la mitad del",
    "  ancho de la imagen o mas.",
    f"- Minimo {MIN_IMAGES} fotos (ideal 10-15).",
    "- Variar angulo y posicion: llevalo",
    "  a los bordes y esquinas.",
    "- Evitar fotos movidas o con reflejos.",
]

KEYS = "ESPACIO: guardar   ESC: terminar y calibrar"


def count_images():
    return len(glob.glob(os.path.join(CALIBRATION_IMAGES_DIR, "*.png")))


def next_index():
    """Devuelve el siguiente numero libre para capture_XX.png."""
    existing = glob.glob(os.path.join(CALIBRATION_IMAGES_DIR, "capture_*.png"))
    numbers = []

    for path in existing:
        name = os.path.splitext(os.path.basename(path))[0]
        suffix = name.replace("capture_", "")
        if suffix.isdigit():
            numbers.append(int(suffix))

    return max(numbers, default=0) + 1


class CalibrationCapture:
    """Sesion de captura de fotos del tablero."""

    def __init__(self):
        os.makedirs(CALIBRATION_IMAGES_DIR, exist_ok=True)
        self.index = next_index()
        self.saved = 0
        self.found = False

    def process(self, frame):
        """
        Analiza un frame. Devuelve (preview, lineas, sugerencias, valido).
        Las lineas son (texto, nivel) con nivel en ok/warn/error/info.
        """
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)

        # Mismos flags por defecto que calibrate.py, mas una verificacion rapida
        self.found, corners = cv2.findChessboardCorners(
            gray,
            CHECKERBOARD,
            cv2.CALIB_CB_ADAPTIVE_THRESH
            + cv2.CALIB_CB_NORMALIZE_IMAGE
            + cv2.CALIB_CB_FAST_CHECK
        )

        preview = frame.copy()
        tips = []

        if self.found:
            cv2.drawChessboardCorners(preview, CHECKERBOARD, corners, self.found)

            width = corners[:, 0, 0].max() - corners[:, 0, 0].min()
            if width < 0.3 * frame.shape[1]:
                tips.append("Acerca el tablero: se ve chico.")
        else:
            tips.append("Muestra el tablero completo a la camara.")

        total = count_images()
        lines = [
            ("Tablero detectado" if self.found else "Tablero NO detectado",
             "ok" if self.found else "error"),
            (f"Fotos en carpeta: {total} (minimo {MIN_IMAGES})",
             "ok" if total >= MIN_IMAGES else "info"),
        ]

        return preview, lines, tips, self.found

    def capture(self, frame):
        """Guarda el frame (sin dibujos). Devuelve la ruta, o None."""
        if not self.found:
            return None

        path = os.path.join(CALIBRATION_IMAGES_DIR, f"capture_{self.index:02d}.png")
        cv2.imwrite(path, frame)

        self.index += 1
        self.saved += 1
        return path
