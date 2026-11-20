"""
Calibracion de camara con un tablero de ajedrez (9x6 esquinas internas).

Lee las fotos de calibration/images/*.png, detecta las esquinas del
tablero y guarda K, dist, image_size y rms en calibration/camera_params.npz.

Ejecutar desde la raiz del proyecto:
    python -m calibration.calibrate
"""

import cv2
import numpy as np
import glob
import os
import sys

from config import CHECKERBOARD, SQUARE_SIZE


def run(show=True):
    IMAGE_SIZE = None

    # Criterio de refinamiento subpixel
    criteria = (
        cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER,
        30,
        0.001
    )

    # Coordenadas 3D conocidas del tablero
    objp = np.zeros(
        (CHECKERBOARD[0] * CHECKERBOARD[1], 3),
        np.float32
    )

    objp[:, :2] = np.mgrid[
        0:CHECKERBOARD[0],
        0:CHECKERBOARD[1]
    ].T.reshape(-1, 2)

    objp *= SQUARE_SIZE

    objpoints = []
    imgpoints = []

    images = glob.glob("calibration/images/*.png")

    for fname in images:

        img = cv2.imread(fname)

        if img is None:
            continue

        gray = cv2.cvtColor(
            img,
            cv2.COLOR_BGR2GRAY
        )

        IMAGE_SIZE = gray.shape[::-1]

        found, corners = cv2.findChessboardCorners(
            gray,
            CHECKERBOARD,
            None
        )

        if found:

            corners2 = cv2.cornerSubPix(
                gray,
                corners,
                (11, 11),
                (-1, -1),
                criteria
            )

            objpoints.append(objp)
            imgpoints.append(corners2)

            print("Tablero detectado:", fname)

            # Vista previa (se omite con --no-gui)
            if show:
                display = cv2.drawChessboardCorners(
                    img.copy(),
                    CHECKERBOARD,
                    corners2,
                    found
                )

                cv2.imshow("Calibration", display)
                cv2.waitKey(300)

        else:
            print("No se detectó:", fname)

    if show:
        cv2.destroyAllWindows()

    if len(objpoints) < 8:
        raise RuntimeError(
            "Se necesitan al menos 8 imágenes válidas del tablero"
        )

    # Calibración
    rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(
        objpoints,
        imgpoints,
        IMAGE_SIZE,
        None,
        None
    )

    print("\n===== RESULTADOS =====")
    print("Error RMS:", rms)
    print("\nMatriz intrínseca:")
    print(K)
    print("\nDistorsión:")
    print(dist)

    os.makedirs("calibration", exist_ok=True)

    np.savez(
        "calibration/camera_params.npz",
        K=K,
        dist=dist,
        image_size=IMAGE_SIZE,
        rms=rms
    )

    print("\nCalibración guardada correctamente.")


if __name__ == "__main__":
    run(show="--no-gui" not in sys.argv)
