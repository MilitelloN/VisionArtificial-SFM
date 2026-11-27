"""
Captura guiada en vivo de las 3 fotos de la escena para la reconstruccion.

Logica de la sesion de captura, sin interfaz propia: la ventana principal
(main.py) muestra el video, llama a process() en cada frame y a capture()
cuando el usuario saca una foto.

El validador (ORB) controla luz, nitidez, detalle, solapamiento con la
foto 1, desplazamiento, distancia e inclinacion, y sugiere como mover la
camara para mejorar las coincidencias.
"""

import os

import cv2
import numpy as np

from config import IMAGE1, IMAGE2, IMAGE3

# Umbrales del validador (sobre la imagen reducida a VALIDATION_WIDTH)
VALIDATION_WIDTH = 640
MIN_KEYPOINTS = 300       # textura minima de la escena
MIN_COVERAGE = 0.5        # fraccion del cuadro con detalle (grilla 4x4)
MIN_BRIGHTNESS = 50       # brillo medio minimo (0-255)
MIN_SHARPNESS = 120       # varianza del Laplaciano minima (nitidez)
MIN_MATCHES = 60          # solapamiento minimo con la foto 1
GOOD_MATCHES = 150        # a partir de aca el solapamiento es muy bueno
MIN_SHIFT = 0.03          # desplazamiento minimo (fraccion del ancho)
MAX_SHIFT = 0.15          # desplazamiento maximo para la foto 2
MAX_SHIFT_PNP = 0.10      # foto 3: cerca de la foto 1 (PnP usa sus puntos)
MAX_SCALE_CHANGE = 0.15   # cambio de distancia tolerado (15%)
MAX_ROLL = 8              # inclinacion tolerada (grados)

STEPS = [
    ("Foto 1/3 - Referencia",
     "Acercate: que los objetos con detalle llenen el cuadro."),
    ("Foto 2/3 - Segunda vista",
     "Correte unos cm al costado, misma distancia y altura."),
    ("Foto 3/3 - Tercera vista (PnP)",
     "Ubicate entre la foto 1 y la 2, apuntando a lo mismo."),
]

GUIDE = [
    "- Objetos con detalle impreso",
    "  (libros, cajas, revistas).",
    "- Camara de baja resolucion:",
    "  acercate (30-60 cm) para que",
    "  los detalles se vean grandes.",
    "- Correrse al costado, sin girar",
    "  ni inclinar la camara.",
    "- Seguir las sugerencias hasta",
    "  que todo este en verde.",
]

KEYS = "ESPACIO: capturar   R: rehacer anterior   ESC: cancelar"


class Validator:
    """
    Evalua en vivo si el frame actual sirve para la reconstruccion y
    sugiere como mover la camara para mejorar las coincidencias.
    """

    def __init__(self):
        self.orb = cv2.ORB_create(nfeatures=1500)
        self.matcher = cv2.BFMatcher(cv2.NORM_HAMMING)
        self.reference = None  # (keypoints, descriptores) de la foto 1
        self.best = 0          # mejor cantidad de coincidencias del paso
        self.factor = 1.0      # escala de la imagen reducida respecto del frame
        # Ultimas correspondencias con la foto 1, en pixeles del frame:
        # (puntos en la foto 1, puntos en el frame actual), o None
        self.last_matches = None

    def features(self, frame):
        scale = VALIDATION_WIDTH / frame.shape[1]
        small = cv2.resize(frame, None, fx=scale, fy=scale) if scale < 1 else frame
        self.factor = scale if scale < 1 else 1.0
        gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
        kp, des = self.orb.detectAndCompute(gray, None)
        return gray, kp, des

    def set_reference(self, frame):
        _, kp, des = self.features(frame)
        self.reference = (kp, des)

    def reset_best(self):
        self.best = 0

    @staticmethod
    def coverage(kp, shape, cells=4, min_points=5):
        """Fraccion de celdas de una grilla con suficientes keypoints."""
        height, width = shape[:2]
        grid = np.zeros((cells, cells), dtype=int)

        for k in kp:
            col = min(int(k.pt[0] / width * cells), cells - 1)
            row = min(int(k.pt[1] / height * cells), cells - 1)
            grid[row, col] += 1

        return np.mean(grid >= min_points)

    def check(self, frame, step):
        """Devuelve (valido, lineas de estado, sugerencias)."""
        gray, kp, des = self.features(frame)
        lines, tips = [], []
        self.last_matches = None

        # --- Calidad de la imagen ---------------------------------------
        brightness = gray.mean()
        sharpness = cv2.Laplacian(gray, cv2.CV_64F).var()
        coverage = self.coverage(kp, gray.shape)

        texture_ok = len(kp) >= MIN_KEYPOINTS and coverage >= MIN_COVERAGE
        lines.append((f"Detalle: {len(kp)} puntos, cubren {coverage:.0%} del cuadro",
                      "ok" if texture_ok else "error"))

        # Sugerencias sobre la imagen (menos prioritarias que las de posicion)
        light_tip = brightness < MIN_BRIGHTNESS

        if sharpness < MIN_SHARPNESS:
            tips.append("Imagen borrosa: quedate quieto o acercate menos.")
        if coverage < MIN_COVERAGE:
            tips.append("Acercate: los objetos con detalle ocupan poco del cuadro.")
        elif len(kp) < MIN_KEYPOINTS:
            tips.append("Poco detalle: suma objetos con texto o dibujos.")

        image_ok = texture_ok and sharpness >= MIN_SHARPNESS
        image_tips = len(tips)

        if self.reference is None:
            return image_ok, lines, self._with_light(tips, light_tip)

        # --- Comparacion con la foto 1 ----------------------------------
        ref_kp, ref_des = self.reference
        good = []

        if des is not None and ref_des is not None and len(des) >= 2:
            for pair in self.matcher.knnMatch(ref_des, des, k=2):
                if len(pair) == 2 and pair[0].distance < 0.75 * pair[1].distance:
                    good.append(pair[0])

        overlap_ok = len(good) >= MIN_MATCHES
        quality = ("muy buena" if len(good) >= GOOD_MATCHES
                   else "aceptable" if overlap_ok else "baja")
        self.best = max(self.best, len(good))

        lines.append((f"Coincidencias con foto 1: {len(good)} ({quality}) "
                      f"- mejor: {self.best}",
                      "ok" if overlap_ok else "error"))

        if not overlap_ok:
            tips.insert(0, "Apunta a la misma zona que en la foto 1 (miniatura).")
            return False, lines, self._with_light(tips, light_tip)

        p_ref = np.float32([ref_kp[m.queryIdx].pt for m in good])
        p_cur = np.float32([kp[m.trainIdx].pt for m in good])
        # Las de menor distancia primero (son las que se dibujan)
        order = np.argsort([m.distance for m in good])
        self.last_matches = (p_ref[order] / self.factor, p_cur[order] / self.factor)

        motion = p_cur - p_ref
        shift = np.median(np.linalg.norm(motion, axis=1)) / VALIDATION_WIDTH
        dx, dy = np.median(motion, axis=0)

        # Escala e inclinacion entre la foto 1 y el frame actual
        affine, _ = cv2.estimateAffinePartial2D(p_ref, p_cur)
        scale, roll = 1.0, 0.0
        if affine is not None:
            scale = float(np.hypot(affine[0, 0], affine[1, 0]))
            roll = float(np.degrees(np.arctan2(affine[1, 0], affine[0, 0])))

        max_shift = MAX_SHIFT_PNP if step == 2 else MAX_SHIFT
        # Los puntos se mueven al reves que la camara
        back = "izquierda" if dx < 0 else "derecha"

        if shift < MIN_SHIFT:
            shift_ok = False
            lines.append((f"Desplazamiento: {shift:.0%} (muy poco)", "error"))
            tips.append("Correte un poco mas al costado (sin girar).")
        elif shift > max_shift:
            shift_ok = False
            lines.append((f"Desplazamiento: {shift:.0%} (demasiado)", "warn"))
            tips.append(f"Volve un poco hacia la {back}.")
        else:
            shift_ok = True
            lines.append((f"Desplazamiento: {shift:.0%} (OK)", "ok"))

        if abs(dy) > abs(dx) and shift >= MIN_SHIFT:
            tips.append("Mantene la misma altura: movete hacia los costados.")

        pose_ok = True
        if abs(scale - 1) > MAX_SCALE_CHANGE:
            pose_ok = False
            tips.append("Alejate un poco: mantene la distancia de la foto 1."
                        if scale > 1 else
                        "Acercate un poco: mantene la distancia de la foto 1.")
        if abs(roll) > MAX_ROLL:
            pose_ok = False
            tips.append("No inclines la camara: mantenela derecha.")

        # Primero las sugerencias de posicion, despues las de imagen
        position_tips = tips[image_tips:]
        tips = position_tips + tips[:image_tips]

        return image_ok and shift_ok and pose_ok, lines, self._with_light(tips, light_tip)

    @staticmethod
    def _with_light(tips, light_tip):
        return tips + ["Poca luz: ilumina mas la escena."] if light_tip else tips


def draw_thumbnail(frame, image):
    """Muestra la foto 1 en miniatura en la esquina inferior derecha."""
    width = frame.shape[1] // 5
    height = int(image.shape[0] * width / image.shape[1])
    thumb = cv2.resize(image, (width, height))

    y, x = frame.shape[0] - height - 10, frame.shape[1] - width - 10
    frame[y:y + height, x:x + width] = thumb
    cv2.rectangle(frame, (x, y), (x + width, y + height), (255, 255, 255), 1)
    cv2.putText(frame, "Foto 1", (x + 4, y + 16),
                cv2.FONT_HERSHEY_SIMPLEX, 0.45, (255, 255, 255), 1, cv2.LINE_AA)


class SceneCapture:
    """Sesion de captura guiada de las 3 fotos de la escena."""

    def __init__(self):
        self.validator = Validator()
        self.photos = []
        self.valid = False

    @property
    def step(self):
        return len(self.photos)

    @property
    def complete(self):
        return len(self.photos) == len(STEPS)

    def step_labels(self):
        """Pasos con su estado: (texto, nivel)."""
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
        """
        Analiza un frame. Devuelve (preview, lineas, sugerencias, valido).
        Las lineas son (texto, nivel) con nivel en ok/warn/error/info.
        """
        self.valid, lines, tips = self.validator.check(frame, self.step)

        preview = frame.copy()
        if self.photos:
            draw_thumbnail(preview, self.photos[0])

        if not tips:
            tips = [STEPS[self.step][1]] if not self.valid else []

        return preview, lines, tips, self.valid

    def capture(self, frame):
        """Guarda el frame en memoria si es valido. Devuelve True si se tomo."""
        if not self.valid or self.complete:
            return False

        self.photos.append(frame.copy())
        self.validator.reset_best()

        if len(self.photos) == 1:
            self.validator.set_reference(frame)

        return True

    def undo(self):
        """Descarta la ultima foto."""
        if not self.photos:
            return

        self.photos.pop()
        self.validator.reset_best()

        if not self.photos:
            self.validator.reference = None

    def save(self):
        """Guarda las 3 fotos juntas, para no dejar un set incompleto."""
        paths = (IMAGE1, IMAGE2, IMAGE3)

        for path, photo in zip(paths, self.photos):
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            cv2.imwrite(path, photo)

        return paths
