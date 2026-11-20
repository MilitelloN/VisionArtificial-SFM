"""
Camara en vivo para las capturas (calibracion y escena).

CameraStream abre la camara y lee frames en un hilo aparte, para que la
interfaz no se trabe mientras espera imagen.
"""

import threading

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

    def __init__(self, index, sizes, retries=30):
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

    def _run(self):
        cap = None

        for width, height in self.sizes:
            cap = open_camera(self.index, width, height)
            if cap is not None:
                self.size = (width, height)
                break

        if cap is None:
            sizes = ", ".join(f"{w}x{h}" for w, h in self.sizes)
            self.error = f"La camara (indice {self.index}) no entrega imagen a {sizes}."
            return

        self.ready = True
        failures = 0

        while self._running:
            ok, frame = cap.read()

            if ok:
                failures = 0
                with self._lock:
                    self._frame = frame
            else:
                failures += 1
                if failures >= self.retries:
                    self.error = "La camara dejo de responder."
                    break

        cap.release()

    def read(self):
        """Ultimo frame disponible (copia), o None."""
        with self._lock:
            return None if self._frame is None else self._frame.copy()

    def stop(self):
        self._running = False
