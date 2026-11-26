"""
Punto de entrada del TP: SfM basico, triangulacion de 2 vistas.

Interfaz grafica (tkinter) de una sola ventana. Las capturas con camara,
la seleccion de la zona de interes y la nube 3D se muestran dentro de
ella (ui/views.py). La calibracion y la reconstruccion corren como
procesos aparte y su salida se ve en el panel de registro.

Uso (desde la raiz del proyecto):
    python main.py
"""

import glob
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

import cv2
import numpy as np

from calibration.capture import CAMERA_SIZES, CalibrationCapture
from calibration.capture import GUIDE as CALIBRATION_GUIDE
from calibration.capture import KEYS as CALIBRATION_KEYS
from calibration.capture import TITLE as CALIBRATION_TITLE
from config import (
    CALIBRATION_FILE,
    CALIBRATION_IMAGES_DIR,
    CAMERA_INDEX,
    IMAGE1,
    IMAGE2,
    IMAGE3,
    OUTPUT_DIR,
    ROI_FILE,
)
from sfm.capture import GUIDE as SCENE_GUIDE
from sfm.capture import KEYS as SCENE_KEYS
from sfm.capture import SceneCapture
from sfm.roi import clear_roi, load_roi, reference_image, save_roi
from ui.views import ACCENT, BG, CARD, MUTED, TEXT, CameraView, CloudView, RoiView
from utils.camera import CameraStream

ROOT = os.path.dirname(os.path.abspath(__file__))

MIN_CALIBRATION_IMAGES = 8
SCENE_IMAGES = (IMAGE1, IMAGE2, IMAGE3)
CLOUD_FILE = os.path.join(OUTPUT_DIR, "point_cloud.ply")
CAMERAS_FILE = os.path.join(OUTPUT_DIR, "cameras.npz")

# Tamaño inicial de la ventana (se limita al tamaño de la pantalla)
WINDOW_SIZE = (1360, 960)

LOG_LINES_COLLAPSED = 5
LOG_LINES_EXPANDED = 20

OK = "#15803d"
WARN = "#b45309"
LOG_BG = "#1e1e1e"
LOG_FG = "#d4d4d4"

IMAGE_EXTENSIONS = (".png", ".jpg", ".jpeg")


def path(relative):
    return os.path.join(ROOT, relative)


def images_in(folder):
    """Imagenes (png/jpg) dentro de una carpeta del proyecto."""
    return sorted(
        f for f in glob.glob(os.path.join(path(folder), "*"))
        if f.lower().endswith(IMAGE_EXTENSIONS)
    )


def calibration_images():
    return glob.glob(os.path.join(path(CALIBRATION_IMAGES_DIR), "*.png"))


def calibration_size():
    """Resolucion (ancho, alto) de la calibracion, o None si no existe."""
    if not os.path.exists(path(CALIBRATION_FILE)):
        return None
    return tuple(int(v) for v in np.load(path(CALIBRATION_FILE))["image_size"])


def scene_problems():
    """Lista de problemas de las fotos de la escena (vacia si estan OK)."""
    problems = []
    sizes = []

    for image in SCENE_IMAGES:
        img = cv2.imread(path(image)) if os.path.exists(path(image)) else None
        if img is None:
            problems.append(f"Falta {image}")
        else:
            sizes.append((img.shape[1], img.shape[0]))

    if problems:
        return problems

    if len(set(sizes)) > 1:
        problems.append("Las 3 fotos no tienen la misma resolucion.")

    calib = calibration_size()
    if calib and sizes[0] != calib:
        problems.append(f"Las fotos son {sizes[0][0]}x{sizes[0][1]} y la "
                        f"calibracion {calib[0]}x{calib[1]}.")

    return problems


class App(tk.Tk):

    def __init__(self):
        super().__init__()

        # Los modulos usan rutas relativas a la raiz del proyecto
        os.chdir(ROOT)

        self.title("SfM - Triangulacion de 2 vistas")
        self.minsize(760, 560)
        self._set_initial_size()
        self.configure(bg=BG)

        self.process = None
        self.stopped = False
        self.output = queue.Queue()
        self.action_buttons = []
        self.card_status = {}
        self.log_expanded = False
        self.view = None
        self.stream = None

        self._setup_style()
        self._build_header()
        self._build_status()
        self._build_content()
        self._build_log()

        self.refresh_status()
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    # ------------------------------------------------------------------
    # Construccion de la interfaz
    # ------------------------------------------------------------------

    def _set_initial_size(self):
        """Ventana grande y centrada, sin pasarse de la pantalla."""
        screen_w, screen_h = self.winfo_screenwidth(), self.winfo_screenheight()
        width = min(WINDOW_SIZE[0], screen_w - 40)
        height = min(WINDOW_SIZE[1], screen_h - 80)
        x, y = (screen_w - width) // 2, max(0, (screen_h - height) // 2 - 20)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")

        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=CARD, relief="solid", borderwidth=1)
        style.configure("CardInner.TFrame", background=CARD)
        style.configure("Title.TLabel", background=BG, foreground=TEXT,
                        font=("Segoe UI", 18, "bold"))
        style.configure("Subtitle.TLabel", background=BG, foreground=MUTED,
                        font=("Segoe UI", 10))
        style.configure("CardTitle.TLabel", background=CARD, foreground=TEXT,
                        font=("Segoe UI", 11, "bold"))
        style.configure("CardText.TLabel", background=CARD, foreground=MUTED,
                        font=("Segoe UI", 9))
        style.configure("CardStatus.TLabel", background=CARD,
                        font=("Segoe UI", 9, "bold"))
        style.configure("Section.TLabel", background=BG, foreground=TEXT,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Status.TLabel", background="#e5e7eb", foreground=TEXT,
                        font=("Segoe UI", 9), padding=(12, 4))
        style.configure("Accent.TButton", background=ACCENT, foreground="white",
                        font=("Segoe UI", 10, "bold"), padding=(10, 6), borderwidth=0)
        style.map("Accent.TButton",
                  background=[("disabled", "#9ca3af"), ("active", "#1d4ed8")])
        style.configure("TButton", font=("Segoe UI", 10), padding=(10, 6))
        style.configure("Small.TButton", font=("Segoe UI", 9), padding=(8, 2))
        style.configure("Danger.TButton", font=("Segoe UI", 9), padding=(8, 3),
                        foreground="#b91c1c")

    def _build_header(self):
        header = ttk.Frame(self, padding=(20, 18, 20, 8))
        header.pack(fill="x")

        ttk.Label(header, text="Structure from Motion",
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(header,
                  text="Reconstruccion 3D de una escena a partir de 2 vistas "
                       "con una camara calibrada.",
                  style="Subtitle.TLabel").pack(anchor="w")

    def _build_content(self):
        """Zona central: el menu de tarjetas o la vista activa."""
        self.content = ttk.Frame(self, padding=(20, 8))
        self.content.pack(fill="both", expand=True)

        self.home = ttk.Frame(self.content)
        self.home.pack(fill="x")

        cards = [
            ("calibration", "1. Calibrar camara",
             "Obtiene K y la distorsion con fotos de un tablero de ajedrez.",
             [("Capturar y calibrar", self.on_capture_calibrate, "Accent.TButton"),
              ("Calibrar", self.on_calibrate, "TButton"),
              ("Borrar fotos", self.on_delete_calibration_images, "Danger.TButton")]),
            ("scene", "2. Reconstruir escena",
             "SIFT, matriz esencial, triangulacion y PnP de una 3ra camara.",
             [("Capturar y reconstruir", self.on_capture_reconstruct, "Accent.TButton"),
              ("Reconstruir", self.on_reconstruct, "TButton"),
              [("Elegir zona", self.on_select_roi, "TButton"),
               ("Quitar zona", self.on_clear_roi, "TButton")],
              ("Borrar fotos", self.on_delete_scene_images, "Danger.TButton")]),
            ("cloud", "3. Ver nube guardada",
             "Muestra la nube de puntos 3D y las camaras.",
             [("Ver nube", self.on_view_cloud, "Accent.TButton")]),
        ]

        for column, (key, title, text, buttons) in enumerate(cards):
            self.home.columnconfigure(column, weight=1, uniform="cards")

            card = ttk.Frame(self.home, style="Card.TFrame", padding=14)
            card.grid(row=0, column=column, sticky="nsew",
                      padx=(0 if column == 0 else 6, 0 if column == 2 else 6))

            ttk.Label(card, text=title, style="CardTitle.TLabel").pack(anchor="w")
            ttk.Label(card, text=text, style="CardText.TLabel",
                      wraplength=210, justify="left").pack(anchor="w", pady=(4, 6), fill="x")

            status = ttk.Label(card, style="CardStatus.TLabel",
                               wraplength=210, justify="left")
            status.pack(anchor="w", pady=(0, 10), fill="x")
            self.card_status[key] = status

            # Los botones se apilan desde abajo para alinearlos entre tarjetas.
            # Una lista de botones se muestra como una fila.
            for entry in reversed(buttons):
                row = ttk.Frame(card, style="CardInner.TFrame")
                row.pack(side="bottom", fill="x", pady=(4, 0))

                for i, (label, command, style) in enumerate(
                        entry if isinstance(entry, list) else [entry]):
                    button = ttk.Button(row, text=label, style=style, command=command)
                    button.pack(side="left", fill="x", expand=True,
                                padx=(0 if i == 0 else 4, 0))
                    self.action_buttons.append(button)

    def _build_log(self):
        frame = ttk.Frame(self, padding=(20, 8, 20, 12))
        frame.pack(fill="x")

        top = ttk.Frame(frame)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="Registro", style="Section.TLabel").pack(side="left")

        self.toggle_button = ttk.Button(top, text="Expandir ▾", style="Small.TButton",
                                        command=self.toggle_log)
        self.toggle_button.pack(side="right")
        self.stop_button = ttk.Button(top, text="■ Detener", style="Danger.TButton",
                                      command=self.stop_process, state="disabled")
        self.stop_button.pack(side="right", padx=(0, 6))
        ttk.Button(top, text="Limpiar", style="Small.TButton",
                   command=self.clear_log).pack(side="right", padx=(0, 6))

        body = ttk.Frame(frame)
        body.pack(fill="both", expand=True)

        self.log = tk.Text(body, bg=LOG_BG, fg=LOG_FG, insertbackground=LOG_FG,
                           font=("Consolas", 9), relief="flat", wrap="word",
                           height=LOG_LINES_COLLAPSED, padx=10, pady=8,
                           state="disabled")
        scroll = ttk.Scrollbar(body, command=self.log.yview)
        self.log.configure(yscrollcommand=scroll.set)

        scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        self.log.tag_configure("info", foreground="#4fc1ff")
        self.log.tag_configure("error", foreground="#f48771")

    def _build_status(self):
        self.status = tk.StringVar(value="Listo")
        ttk.Label(self, textvariable=self.status,
                  style="Status.TLabel", anchor="w").pack(fill="x", side="bottom")

    # ------------------------------------------------------------------
    # Navegacion entre el menu y las vistas
    # ------------------------------------------------------------------

    def show_view(self, view):
        """Reemplaza el menu por una vista (camara, zona o nube)."""
        self.close_view()
        self.home.pack_forget()
        self.view = view
        view.pack(fill="both", expand=True)

        # Los botones del menu oculto conservan el foco: sin esto, la tecla
        # espacio los "presiona" y abre otra captura encima de la actual.
        view.focus_set()

    def close_view(self):
        if self.view is not None:
            # Una vista de camara que se destruye debe soltar la camara
            stream = getattr(self.view, "stream", None)
            if stream is not None:
                stream.stop()

            self.view.destroy()
            self.view = None

    def show_home(self):
        self.close_view()
        self.home.pack(fill="x")
        self.refresh_status()

    # ------------------------------------------------------------------
    # Estado de cada tarjeta
    # ------------------------------------------------------------------

    def refresh_status(self):
        total = len(calibration_images())
        calib = calibration_size()

        if calib:
            text = f"Calibrada ({calib[0]}x{calib[1]}) · {total} fotos"
            self._set_card_status("calibration", text, OK)
        else:
            self._set_card_status("calibration",
                                  f"Sin calibrar · {total} fotos en carpeta", WARN)

        # Solo informa si hay fotos; la falta se avisa al reconstruir
        zone = " · zona de interes activa" if os.path.exists(path(ROI_FILE)) else ""

        if not scene_problems():
            self._set_card_status("scene", "3 fotos listas en images/" + zone, OK)
        else:
            self._set_card_status("scene", zone.strip(" ·"), MUTED)

        if os.path.exists(path(CLOUD_FILE)):
            self._set_card_status("cloud", "Nube guardada", OK)
        else:
            self._set_card_status("cloud", "Sin nube guardada", WARN)

    def _set_card_status(self, key, text, color):
        self.card_status[key].configure(text=text, foreground=color)

    # ------------------------------------------------------------------
    # Registro
    # ------------------------------------------------------------------

    def write_log(self, text, tag=None):
        self.log.configure(state="normal")
        self.log.insert("end", text, tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def clear_log(self):
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def toggle_log(self, expand=None):
        self.log_expanded = not self.log_expanded if expand is None else expand

        if self.log_expanded:
            self.log.configure(height=LOG_LINES_EXPANDED)
            self.toggle_button.configure(text="Contraer ▴")
        else:
            self.log.configure(height=LOG_LINES_COLLAPSED)
            self.toggle_button.configure(text="Expandir ▾")

        self.log.see("end")

    # ------------------------------------------------------------------
    # Procesos en segundo plano (calibracion y reconstruccion)
    # ------------------------------------------------------------------

    def run_module(self, module, label, args=(), on_done=None):
        """Ejecuta un modulo en segundo plano y muestra su salida."""
        if self.process is not None:
            return

        self.stopped = False
        self.set_busy(True, f"Ejecutando: {label}...")
        self.write_log(f"\n> {label}  (python -m {module} {' '.join(args)})\n", "info")

        self.process = subprocess.Popen(
            [sys.executable, "-u", "-m", module, *args],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )

        threading.Thread(target=self._read_output, daemon=True).start()
        self.after(50, self._poll_output, label, on_done)

    def _read_output(self):
        for line in self.process.stdout:
            self.output.put(line)
        self.output.put(None)

    def _poll_output(self, label, on_done):
        finished = False

        while not self.output.empty():
            line = self.output.get()
            if line is None:
                finished = True
            else:
                self.write_log(line)

        if not finished:
            self.after(50, self._poll_output, label, on_done)
            return

        code = self.process.wait()
        self.process = None
        self.set_busy(False)
        self.refresh_status()

        if self.stopped:
            self.status.set(f"{label}: detenido")
            self.write_log(f"[DETENIDO] {label}\n", "info")
            return

        if code == 0:
            self.status.set(f"{label}: finalizado")
            self.write_log(f"[OK] {label}\n", "info")
        else:
            self.status.set(f"{label}: error (codigo {code})")
            self.write_log(f"[ERROR] {label} termino con codigo {code}\n", "error")
            self.toggle_log(expand=True)

        if on_done:
            on_done(code)

    def stop_process(self):
        """Detiene el proceso en curso."""
        if self.process is None:
            return

        self.stopped = True
        self.process.terminate()

        # Si no termina por las buenas, se fuerza a los 2 segundos
        self.after(2000, lambda p=self.process: p.poll() is None and p.kill())

    def set_busy(self, busy, message=None):
        state = "disabled" if busy else "normal"
        for button in self.action_buttons:
            button.configure(state=state)
        self.stop_button.configure(state="normal" if busy else "disabled")
        if message:
            self.status.set(message)

    # ------------------------------------------------------------------
    # Captura con camara (dentro de la ventana)
    # ------------------------------------------------------------------

    def start_capture(self, sizes, session, title, guide, keys, on_finish, **options):
        self.stream = CameraStream(CAMERA_INDEX, sizes)
        self.status.set(f"{title}: camara activa")

        def finish(result):
            self.stream = None
            if result == "error":
                messagebox.showerror(
                    "Camara no disponible",
                    "No se pudo obtener imagen de la camara.\n"
                    "Revisa que este conectada o cambia CAMERA_INDEX en config.py.",
                )
            self.show_home()
            on_finish(result)

        self.show_view(CameraView(self.content, self, self.stream, session, title,
                                  guide, keys, finish, **options))

    # ------------------------------------------------------------------
    # Calibracion
    # ------------------------------------------------------------------

    def on_capture_calibrate(self):
        session = CalibrationCapture()

        def finished(result):
            self.write_log(f"Fotos nuevas del tablero: {session.saved}\n", "info")
            if result == "done":
                self.on_calibrate()

        self.start_capture(CAMERA_SIZES, session, CALIBRATION_TITLE,
                           CALIBRATION_GUIDE, CALIBRATION_KEYS, finished,
                           finish_label="Terminar")

    def on_calibrate(self):
        total = len(calibration_images())

        if total < MIN_CALIBRATION_IMAGES:
            messagebox.showwarning(
                "Faltan fotos",
                f"Hay {total} fotos .png en {CALIBRATION_IMAGES_DIR}/.\n"
                f"Se necesitan al menos {MIN_CALIBRATION_IMAGES}.\n\n"
                "Agrega fotos a la carpeta o usa 'Capturar y calibrar'.",
            )
            return

        self.run_module("calibration.calibrate", "Calibracion", args=["--no-gui"])

    # ------------------------------------------------------------------
    # Reconstruccion
    # ------------------------------------------------------------------

    def require_calibration(self):
        if calibration_size() is None:
            messagebox.showwarning("Sin calibracion",
                                   "No existe la calibracion de la camara.\n"
                                   "Calibra la camara primero.")
            return False
        return True

    def on_capture_reconstruct(self):
        if not self.require_calibration():
            return

        if not scene_problems() and not messagebox.askyesno(
                "Reemplazar fotos",
                "Ya hay 3 fotos de la escena en images/.\n"
                "¿Reemplazarlas con una nueva captura?"):
            return

        session = SceneCapture()

        def finished(result):
            if result != "done" or not session.complete:
                self.write_log("Captura de escena cancelada.\n", "info")
                return

            for saved in session.save():
                self.write_log(f"Foto guardada: {saved}\n")

            # La zona anterior no corresponde a las fotos nuevas
            clear_roi()

            if messagebox.askyesno("Zona de interes",
                                   "¿Queres marcar una zona de interes sobre la foto 1?\n"
                                   "Solo se reconstruye esa zona y se ignora el fondo."):
                self.open_roi(then=self.on_reconstruct)
            else:
                self.on_reconstruct()

        # La escena se captura a la resolucion de la calibracion
        self.start_capture([calibration_size()], session, "Captura de escena",
                           SCENE_GUIDE, SCENE_KEYS, finished,
                           finish_label="Cancelar", allow_undo=True)

    def on_reconstruct(self):
        if not self.require_calibration():
            return

        problems = scene_problems()

        if problems:
            messagebox.showwarning(
                "Fotos de la escena",
                "\n".join(problems) +
                "\n\nUsa 'Capturar y reconstruir' o revisa IMAGE1-3 en config.py.",
            )
            return

        self.run_module("sfm.reconstruction", "Reconstruccion 3D", args=["--no-gui"],
                        on_done=lambda code: code == 0 and self.on_view_cloud())

    # ------------------------------------------------------------------
    # Zona de interes
    # ------------------------------------------------------------------

    def open_roi(self, then=None):
        image = reference_image()

        if image is None:
            messagebox.showwarning("Zona de interes",
                                   f"Falta {IMAGE1}. Captura la escena primero.")
            return

        def done(result):
            if result == "clear":
                clear_roi()
                self.write_log("Zona de interes: imagen completa.\n", "info")
            elif result:
                save_roi(*result)
                self.write_log(f"Zona de interes guardada: {result}\n", "info")

            self.show_home()

            if then and result is not None:
                then()

        self.show_view(RoiView(self.content, image, load_roi(), done))

    def on_select_roi(self):
        self.open_roi()

    def on_clear_roi(self):
        if not os.path.exists(path(ROI_FILE)):
            messagebox.showinfo("Zona de interes",
                                "No hay zona definida: se usa la imagen completa.")
            return

        clear_roi()
        self.refresh_status()
        self.write_log("Zona de interes eliminada: se usa la imagen completa.\n", "info")

    # ------------------------------------------------------------------
    # Borrado de fotos
    # ------------------------------------------------------------------

    def delete_images(self, folder, description):
        files = images_in(folder)

        if not files:
            messagebox.showinfo("Borrar fotos", f"No hay fotos en {folder}/.")
            return

        if not messagebox.askyesno(
                "Borrar fotos",
                f"Se van a borrar {len(files)} fotos {description} de {folder}/.\n"
                "Esta accion no se puede deshacer. ¿Continuar?",
                icon="warning"):
            return

        for f in files:
            os.remove(f)

        self.write_log(f"Se borraron {len(files)} fotos de {folder}/\n", "info")
        self.status.set(f"Fotos de {folder}/ borradas")
        self.refresh_status()

    def on_delete_calibration_images(self):
        self.delete_images(CALIBRATION_IMAGES_DIR, "del tablero")

    def on_delete_scene_images(self):
        self.delete_images(os.path.dirname(IMAGE1), "de la escena")

        if not images_in(os.path.dirname(IMAGE1)):
            clear_roi()
            self.refresh_status()

    # ------------------------------------------------------------------
    # Nube de puntos
    # ------------------------------------------------------------------

    def on_view_cloud(self):
        if not os.path.exists(path(CLOUD_FILE)):
            messagebox.showwarning("Sin nube",
                                   "No hay una nube de puntos guardada.\n"
                                   "Reconstruye la escena primero.")
            return

        self.status.set("Nube de puntos 3D")
        self.show_view(CloudView(self.content, path(CLOUD_FILE), path(CAMERAS_FILE),
                                 on_back=self.show_home))

    # ------------------------------------------------------------------
    # Cierre
    # ------------------------------------------------------------------

    def on_close(self):
        """La X cierra toda la app: camara, procesos y vistas."""
        if self.process is not None:
            if not messagebox.askyesno("Salir",
                                       "Hay un proceso en ejecucion. ¿Cerrar igual?"):
                return
            self.process.kill()

        if self.stream is not None:
            self.stream.stop()

        self.close_view()
        self.quit()
        self.destroy()


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
