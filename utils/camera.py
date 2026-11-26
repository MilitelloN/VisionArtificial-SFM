"""
Camara en vivo para las capturas (calibracion y escena).

CameraStream abre la camara y lee frames en un hilo aparte, para que la
interfaz no se trabe mientras espera imagen.
"""

import sys
import threading
import time

import cv2


def open_camera(index, width, height):
    """
    Abre la camara en MJPG a la resolucion pedida.
    Devuelve None si no abre, no entrega imagen o usa otra resolucion.
    """
    cap = cv2.VideoCapture(index)

    if not cap.isOpened():
        return None

    # MJPG reduce el ancho de banda USB (necesario en WSL2 con usbipd)
    cap.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)

    # Algunas camaras abren pero no entregan imagen
    ok, frame = cap.read()

    if not ok or (frame.shape[1], frame.shape[0]) != (width, height):
        cap.release()
        return None

    return cap


class CameraStream:
    """Lee frames continuamente en segundo plano."""

    def __init__(self, index, sizes, retries=10):
        """
        index: indice de la camara.
        sizes: resoluciones (ancho, alto) a probar, en orden de preferencia.
        retries: lecturas fallidas seguidas toleradas (frecuentes en WSL2).
        """
        self.index = index
        self.sizes = sizes
        self.retries = retries

        self.size = None
        self.error = None
        self.ready = False

        self._frame = None
        self._lock = threading.Lock()
        self._running = True

        threading.Thread(target=self._run, daemon=True).start()

    def _open(self, sizes, attempts=5):
        """
        Abre la camara probando las resoluciones dadas. Si una captura
        anterior todavia no la solto, abrirla falla en el acto: se reintenta
        unos segundos antes de rendirse. Devuelve el cap o None.
        """
        for _attempt in range(attempts):
            for width, height in sizes:
                cap = open_camera(self.index, width, height)
                if cap is not None:
                    self.size = (width, height)
                    return cap

            if not self._running:
                return None
            time.sleep(1)

        return None

    def _run(self, max_reopens=5):
        cap = self._open(self.sizes)

        if cap is None:
            sizes = ", ".join(f"{w}x{h}" for w, h in self.sizes)
            self.error = f"La camara (indice {self.index}) no entrega imagen a {sizes}."
            return

        self.ready = True
        failures = 0
        reopens = 0

        while self._running:
            ok, frame = cap.read()

            if ok:
                failures = reopens = 0
                with self._lock:
                    self._frame = frame
                continue

            failures += 1
            if failures < self.retries:
                continue

            # En WSL2 (usbipd) el stream USB se corta seguido: se reabre la
            # camara a la misma resolucion en vez de abandonar.
            cap.release()
            reopens += 1
            failures = 0
            print(f"[camara] sin imagen, reabriendo ({reopens}/{max_reopens})",
                  file=sys.stderr)

            cap = self._open([self.size]) if reopens <= max_reopens else None
            if cap is None:
                if self._running:
                    self.error = "La camara dejo de responder."
                return

        cap.release()

    def read(self):
        """Ultimo frame disponible (copia), o None."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
