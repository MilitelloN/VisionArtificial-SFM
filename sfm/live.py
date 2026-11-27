"""
Reconstruccion en vivo: captura del par de fotos y PnP sobre el video.

1. LivePairCapture: se saca la foto 1. Despues la vista muestra la foto 1
   fija junto a la camara en vivo, con el matching de keypoints
   resolviendose en cada cuadro, hasta que se saca la foto 2 a mano.
2. Con ese par se reconstruye la nube (sfm.reconstruction --no-pnp).
3. LiveTracker: en cada cuadro del video empareja SIFT contra los
   descriptores de la nube y calcula la pose de la camara con
   solvePnPRansac. El video hace de "camara 3".
"""

import os

import cv2
import numpy as np

from config import (
    CALIBRATION_FILE,
    IMAGE1,
    IMAGE2,
    IMAGE3,
    LIVE_MIN_INLIERS,
    LIVE_PNP_ITERATIONS,
    LIVE_SIFT_FEATURES,
    OUTPUT_DIR,
    PNP_REPROJECTION_THRESHOLD,
    RATIO_TEST,
)
from sfm.capture import SceneCapture

FEATURES_FILE = os.path.join(OUTPUT_DIR, "cloud_features.npz")
CAMERAS_FILE = os.path.join(OUTPUT_DIR, "cameras.npz")

STEPS = [
    ("Foto 1/2 - Referencia",
     "Acercate: que los objetos con detalle llenen el cuadro."),
    ("Foto 2/2 - Segunda vista",
     "Correte unos cm al costado, misma distancia y altura."),
]

GUIDE = [
    "- Foto 1: encuadra y pulsa ESPACIO.",
    "- Despues correte al costado, sin",
    "  girar ni inclinar la camara.",
    "- Foto 1 fija a la izquierda y la",
    "  camara a la derecha: cada linea",
    "  une un keypoint con su pareja.",
    "- Con todo en verde, ESPACIO saca",
    "  la foto 2 y abre el PnP en vivo.",
]

KEYS = "ESPACIO: capturar   R: rehacer anterior   ESC: cancelar"

MAX_DRAWN = 60                    # lineas de correspondencia dibujadas (las mejores)
PAIR_WIDTH = 960                  # ancho de la vista doble (foto 1 | camara en vivo)

# Colores BGR que se alternan entre lineas, para distinguir cada pareja
MATCH_COLORS = [(80, 220, 80), (255, 180, 0), (0, 200, 255), (255, 90, 200),
                (0, 140, 255), (200, 255, 0), (255, 255, 255), (60, 60, 255)]


class LivePairCapture(SceneCapture):
    """Captura de las fotos 1 y 2, con el matching en vivo entre ambas."""

    @property
    def complete(self):
        return len(self.photos) == len(STEPS)

    def step_labels(self):
        labels = []
        for i, (title, _) in enumerate(STEPS):
            if i < self.step:
                labels.append((f"[OK] {title}", "ok"))
            elif i == self.step:
                labels.append((f">> {title}", "title"))
            else:
                labels.append((f"   {title}", "muted"))
        return labels

    def process(self, frame):
        self.valid, lines, tips = self.validator.check(frame, self.step)

        preview = frame.copy()

        if self.photos:
            preview = self._draw_pair(frame)

        if not tips and not self.valid:
            tips = [STEPS[self.step][1]]

        return preview, lines, tips, self.valid

    def _draw_pair(self, frame):
        """
        Matching en vivo: la foto 1 fija a la izquierda, la camara a la
        derecha y una linea entre cada keypoint y su pareja, recalculada
        en cada cuadro.
        """
        photo = self.photos[0]
        width = photo.shape[1]
        pair = np.hstack([photo, frame])

        if self.validator.last_matches is not None:
            p_ref, p_cur = self.validator.last_matches
            for i, (a, b) in enumerate(list(zip(p_ref, p_cur))[:MAX_DRAWN]):
                color = MATCH_COLORS[i % len(MATCH_COLORS)]
                a = (int(a[0]), int(a[1]))
                b = (int(b[0]) + width, int(b[1]))
                cv2.line(pair, a, b, color, 1, cv2.LINE_AA)
                cv2.circle(pair, a, 3, color, 1, cv2.LINE_AA)
                cv2.circle(pair, b, 3, color, 1, cv2.LINE_AA)

        cv2.line(pair, (width, 0), (width, pair.shape[0]), (255, 255, 255), 2)
        for text, x in (("Foto 1 (fija)", 10), ("Camara en vivo", width + 10)):
            cv2.putText(pair, text, (x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (0, 0, 0), 4, cv2.LINE_AA)
            cv2.putText(pair, text, (x, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8,
                        (255, 255, 255), 2, cv2.LINE_AA)

        scale = PAIR_WIDTH / pair.shape[1]
        return cv2.resize(pair, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)

    def save(self):
        """Guarda las fotos 1 y 2. La 3 anterior se borra: no es de este par."""
        for path, photo in zip((IMAGE1, IMAGE2), self.photos):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            cv2.imwrite(path, photo)

        if os.path.exists(IMAGE3):
            os.remove(IMAGE3)

        return IMAGE1, IMAGE2


class LiveTracker:
    """Pose de la camara en cada cuadro, con PnP contra la nube 3D."""

    def __init__(self, features_file=FEATURES_FILE, cameras_file=CAMERAS_FILE):
        calib = np.load(CALIBRATION_FILE)
        self.K = calib["K"]
        width, height = (int(v) for v in calib["image_size"])
        self.size = (width, height)

        features = np.load(features_file)
        self.points = features["points"].astype(np.float64)
        self.colors = features["colors"]
        self.descriptors = features["descriptors"].astype(np.float32)

        cams = np.load(cameras_file)
        self.R2 = cams["R2"]
        self.C2 = cams["C2"]

        # Mismo undistort que la reconstruccion, precalculado para ir rapido
        self.maps = cv2.initUndistortRectifyMap(
            self.K, calib["dist"], None, self.K, (width, height), cv2.CV_16SC2)

        self.sift = cv2.SIFT_create(nfeatures=LIVE_SIFT_FEATURES,
                                    contrastThreshold=0.02, edgeThreshold=15)
        self.matcher = cv2.BFMatcher(cv2.NORM_L2)
        self.rvec = None
        self.tvec = None

    def locate(self, frame):
        """
        Devuelve un dict con el frame corregido y, si se pudo ubicar la
        camara, su pose, centro, inliers y error de reproyeccion.
        """
        image = cv2.remap(frame, *self.maps, cv2.INTER_LINEAR)
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        result = {"image": image, "ok": False, "matches": 0, "inliers": 0}

        kp, des = self.sift.detectAndCompute(gray, None)
        if des is None or len(kp) < 2:
            return result

        # Correspondencias 2D-3D: descriptor de cada punto de la nube contra
        # los keypoints del cuadro, con ratio test
        obj_pts, img_pts = [], []
        for pair in self.matcher.knnMatch(self.descriptors, des, k=2):
            if len(pair) == 2 and pair[0].distance < RATIO_TEST * pair[1].distance:
                obj_pts.append(self.points[pair[0].queryIdx])
                img_pts.append(kp[pair[0].trainIdx].pt)

        result["matches"] = len(obj_pts)
        if len(obj_pts) < 6:
            return result

        obj_pts = np.asarray(obj_pts, dtype=np.float64)
        img_pts = np.asarray(img_pts, dtype=np.float64)

        ok, rvec, tvec, inliers = cv2.solvePnPRansac(
            obj_pts, img_pts, self.K, None,
            iterationsCount=LIVE_PNP_ITERATIONS,
            reprojectionError=PNP_REPROJECTION_THRESHOLD,
            confidence=0.99,
            flags=cv2.SOLVEPNP_EPNP,
        )

        if not ok or inliers is None or len(inliers) < LIVE_MIN_INLIERS:
            return result

        inliers = inliers.ravel()
        rvec, tvec = cv2.solvePnPRefineLM(obj_pts[inliers], img_pts[inliers],
                                          self.K, None, rvec, tvec)

        projected, _ = cv2.projectPoints(obj_pts[inliers], rvec, tvec, self.K, None)
        error = np.linalg.norm(projected.reshape(-1, 2) - img_pts[inliers], axis=1)

        # Toda la nube proyectada sobre el cuadro, para dibujarla
        cloud_2d, _ = cv2.projectPoints(self.points, rvec, tvec, self.K, None)

        R, _ = cv2.Rodrigues(rvec)
        result.update(
            ok=True,
            inliers=len(inliers),
            error=float(error.mean()),
            center=(-R.T @ tvec).ravel(),       # centro de la camara en el mundo
            rotation=R.T,                         # camara -> mundo
            inlier_points=img_pts[inliers],
            cloud_2d=cloud_2d.reshape(-1, 2),
        )
        return result
