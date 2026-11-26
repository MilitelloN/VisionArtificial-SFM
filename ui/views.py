"""
Vistas que se muestran dentro de la ventana principal (main.py):

- CameraView: video en vivo con validador, sugerencias y guia (capturas).
- RoiView: seleccion de la zona de interes con el mouse sobre la foto 1.
- CloudView: nube de puntos 3D y camaras (matplotlib, rotable con el mouse)
  y la imagen de coincidencias entre las fotos 1 y 2, con zoom (ZoomableImage).
"""

import os
import tkinter as tk
from tkinter import ttk

import cv2
import numpy as np

# Paleta compartida con main.py
BG = "#f4f5f7"
CARD = "#ffffff"
TEXT = "#1f2328"
MUTED = "#656d76"
ACCENT = "#2563eb"

LEVEL_COLORS = {
    "ok": "#15803d",
    "warn": "#b45309",
    "error": "#b91c1c",
    "info": MUTED,
    "title": TEXT,
    "muted": "#9ca3af",
}

# Colores de las camaras (los mismos de la ventana de Open3D)
CAMERA_COLORS = [(0.0, 0.7, 1.0), (1.0, 0.3, 0.1), (0.2, 0.8, 0.2)]


def to_photo(bgr):
    """Convierte una imagen BGR de OpenCV en un PhotoImage de tkinter."""
    rgb = cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB)
    header = f"P6 {rgb.shape[1]} {rgb.shape[0]} 255\n".encode()
    return tk.PhotoImage(data=header + rgb.tobytes(), format="PPM")


def side_panel(parent, width=320):
    panel = tk.Frame(parent, bg=CARD, width=width, highlightthickness=1,
                     highlightbackground="#d0d7de")
    panel.pack(side="right", fill="y", padx=(12, 0))
    panel.pack_propagate(False)
    return panel


def label(parent, text="", size=9, bold=False, color=TEXT, **kw):
    font = ("Segoe UI", size, "bold" if bold else "normal")
    return tk.Label(parent, text=text, bg=CARD, fg=color, font=font,
                    justify="left", anchor="w", **kw)


# ======================================================================
# Captura con camara
# ======================================================================

class CameraView(tk.Frame):
    """
    Muestra el video de un CameraStream procesado por una sesion de
    captura (CalibrationCapture o SceneCapture).

    on_finish(result) se llama con "done" (terminar), "cancel" o "error".
    """

    def __init__(self, parent, app, stream, session, title, guide, keys,
                 on_finish, finish_label="Terminar", allow_undo=False):
        super().__init__(parent, bg=BG)

        self.app = app
        self.stream = stream
        self.session = session
        self.on_finish = on_finish
        self.frame = None
        self.photo = None
        self.closed = False

        # Video
        self.video = tk.Label(self, bg="#111111", fg="#dddddd",
                              text="Abriendo camara...", font=("Segoe UI", 11),
                              width=80, height=30)
        self.video.pack(side="left", anchor="n")

        # Panel lateral
        panel = side_panel(self)
        inner = tk.Frame(panel, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        label(inner, title, size=12, bold=True).pack(fill="x")

        self.status_labels = [label(inner, wraplength=290) for _ in range(4)]
        for item in self.status_labels:
            item.pack(fill="x", pady=(4, 0))

        self.tip_labels = [label(inner, wraplength=290, color=LEVEL_COLORS["warn"])
                           for _ in range(2)]
        for item in self.tip_labels:
            item.pack(fill="x", pady=(4, 0))

        self.step_labels = []
        if hasattr(session, "step_labels"):
            label(inner, "PASOS", bold=True, color=ACCENT).pack(fill="x", pady=(12, 0))
            self.step_labels = [label(inner) for _ in session.step_labels()]
            for item in self.step_labels:
                item.pack(fill="x")

        label(inner, "QUE CAPTURAR", bold=True, color=ACCENT).pack(fill="x", pady=(12, 2))
        label(inner, "\n".join(guide), color=MUTED).pack(fill="x")

        # Botones
        buttons = tk.Frame(inner, bg=CARD)
        buttons.pack(side="bottom", fill="x")

        label(inner, keys, size=8, color=MUTED, wraplength=290).pack(
            side="bottom", fill="x", pady=(0, 8))

        self.capture_button = ttk.Button(buttons, text="Capturar",
                                         style="Accent.TButton", command=self.capture,
                                         takefocus=False)
        self.capture_button.pack(fill="x")

        if allow_undo:
            ttk.Button(buttons, text="Rehacer anterior", takefocus=False,
                       command=self.undo).pack(fill="x", pady=(4, 0))

        ttk.Button(buttons, text=finish_label, takefocus=False,
                   command=lambda: self.finish("done" if finish_label == "Terminar"
                                               else "cancel")).pack(fill="x", pady=(4, 0))

        self.finish_label = finish_label

        # Atajos de teclado
        self.bindings = {
            "<space>": lambda _e: self.capture(),
            "<Escape>": lambda _e: self.finish("done" if finish_label == "Terminar"
                                               else "cancel"),
        }
        if allow_undo:
            self.bindings["r"] = lambda _e: self.undo()

        for key, handler in self.bindings.items():
            app.bind(key, handler)

        self.after(30, self.tick)

    def tick(self):
        if self.closed:
            return

        if self.stream.error:
            self.app.write_log(self.stream.error + "\n", "error")
            self.finish("error")
            return

        frame = self.stream.read()

        if frame is not None:
            self.frame = frame
            preview, lines, tips, valid = self.session.process(frame)

            self.photo = to_photo(preview)
            self.video.configure(image=self.photo, text="", width=0, height=0)

            for item, line in zip(self.status_labels, lines + [("", "info")] * 4):
                item.configure(text=line[0], fg=LEVEL_COLORS[line[1]])

            for item, tip in zip(self.tip_labels, tips[:2] + [""] * 2):
                item.configure(text=f"> {tip}" if tip else "")

            for item, (text, level) in zip(self.step_labels,
                                           getattr(self.session, "step_labels", list)()):
                item.configure(text=text, fg=LEVEL_COLORS[level])

            self.capture_button.configure(
                text="Capturar  (lista)" if valid else "Capturar",
                state="normal" if valid else "disabled")

        self.after(30, self.tick)

    def capture(self):
        if self.frame is None:
            return

        result = self.session.capture(self.frame)

        if not result:
            self.app.write_log("Foto descartada: no cumple el validador.\n")
            return

        self.app.write_log(f"Foto guardada: {result}\n" if isinstance(result, str)
                           else f"Foto {self.session.step} capturada.\n")

        if getattr(self.session, "complete", False):
            self.finish("done")

    def undo(self):
        if hasattr(self.session, "undo"):
            self.session.undo()
            self.app.write_log("Ultima foto descartada.\n")

    def finish(self, result):
        if self.closed:
            return

        self.closed = True
        self.stream.stop()

        for key in self.bindings:
            self.app.unbind(key)

        self.on_finish(result)


# ======================================================================
# Zona de interes
# ======================================================================

class RoiView(tk.Frame):
    """
    Permite marcar con el mouse un rectangulo sobre la foto 1.
    on_done(result) se llama con (x, y, w, h), "clear" o None (cancelar).
    """

    def __init__(self, parent, image, current, on_done):
        super().__init__(parent, bg=BG)

        self.on_done = on_done
        self.start = None
        self.rect = None
        self.selection = current

        self.photo = to_photo(image)
        self.canvas = tk.Canvas(self, width=image.shape[1], height=image.shape[0],
                                highlightthickness=0, cursor="crosshair")
        self.canvas.pack(side="left", anchor="n")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")

        if current:
            x, y, w, h = current
            self.rect = self.canvas.create_rectangle(x, y, x + w, y + h,
                                                     outline="#22c55e", width=2)

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)

        panel = side_panel(self)
        inner = tk.Frame(panel, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        label(inner, "Zona de interes", size=12, bold=True).pack(fill="x")
        label(inner, "Arrastra un rectangulo sobre los objetos a reconstruir. "
                     "Solo se buscan coincidencias dentro de esa zona (con un "
                     "margen extra) en las 3 fotos; el fondo se ignora.",
              color=MUTED, wraplength=290).pack(fill="x", pady=(6, 0))

        self.info = label(inner, wraplength=290, color=LEVEL_COLORS["ok"])
        self.info.pack(fill="x", pady=(10, 0))
        self.update_info()

        buttons = tk.Frame(inner, bg=CARD)
        buttons.pack(side="bottom", fill="x")
        ttk.Button(buttons, text="Confirmar zona", style="Accent.TButton",
                   command=self.confirm).pack(fill="x")
        ttk.Button(buttons, text="Usar imagen completa",
                   command=lambda: self.on_done("clear")).pack(fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Cancelar",
                   command=lambda: self.on_done(None)).pack(fill="x", pady=(4, 0))

    def on_press(self, event):
        self.start = (event.x, event.y)
        if self.rect:
            self.canvas.delete(self.rect)
        self.rect = self.canvas.create_rectangle(event.x, event.y, event.x, event.y,
                                                 outline="#22c55e", width=2)

    def on_drag(self, event):
        x0, y0 = self.start
        x1 = min(max(event.x, 0), int(self.canvas["width"]))
        y1 = min(max(event.y, 0), int(self.canvas["height"]))
        self.canvas.coords(self.rect, x0, y0, x1, y1)

        self.selection = (min(x0, x1), min(y0, y1), abs(x1 - x0), abs(y1 - y0))
        self.update_info()

    def update_info(self):
        if self.selection and self.selection[2] > 0 and self.selection[3] > 0:
            x, y, w, h = self.selection
            self.info.configure(text=f"Zona: {w}x{h} px en ({x}, {y})")
        else:
            self.info.configure(text="Sin zona: se usa la imagen completa.")

    def confirm(self):
        if self.selection and self.selection[2] > 10 and self.selection[3] > 10:
            self.on_done(self.selection)
        else:
            self.on_done("clear")


# ======================================================================
# Imagen con zoom
# ======================================================================

class ZoomableImage(tk.Canvas):
    """
    Muestra una imagen con zoom y desplazamiento:
    - Rueda del mouse: acerca/aleja hacia donde apunta el cursor.
    - Arrastrar: mueve la imagen ampliada.
    - Doble clic: vuelve a ajustar la imagen completa.
    """

    MAX_ZOOM = 8.0
    STEP = 1.25

    def __init__(self, parent, width, height, on_zoom=None, max_height=340):
        super().__init__(parent, width=width, height=height, bg="#111111",
                         highlightthickness=0, cursor="fleur")

        self.view_w, self.view_h = width, height
        self.ratio = height / width
        self.max_height = max_height
        self.on_zoom = on_zoom
        self.image = None
        self.photo = None
        self.zoom = 1.0
        self.x0 = self.y0 = 0.0      # esquina visible, en pixeles de la imagen
        self.drag = None

        self.bind("<ButtonPress-1>", self._start_drag)
        self.bind("<B1-Motion>", self._drag)
        self.bind("<Double-Button-1>", lambda _e: self.fit())
        self.bind("<MouseWheel>", self._wheel)                      # Windows / macOS
        self.bind("<Button-4>", lambda e: self.zoom_at(self.STEP, e.x, e.y))   # Linux
        self.bind("<Button-5>", lambda e: self.zoom_at(1 / self.STEP, e.x, e.y))
        self.bind("<Configure>", self._resize)

    def _resize(self, event):
        """Se adapta al ancho disponible, con la proporcion inicial y un alto maximo."""
        ratio = self.ratio
        self.view_w = event.width
        height = min(int(event.width * ratio), self.max_height)

        if height != int(self["height"]):
            self.configure(height=height)

        self.view_h = height
        self.render()

    def set_image(self, image):
        self.image = image
        self.fit()

    def fit(self):
        self.zoom, self.x0, self.y0 = 1.0, 0.0, 0.0
        self.render()

    def zoom_in(self):
        self.zoom_at(self.STEP, self.view_w / 2, self.view_h / 2)

    def zoom_out(self):
        self.zoom_at(1 / self.STEP, self.view_w / 2, self.view_h / 2)

    def _base_scale(self):
        """Escala que ajusta la imagen completa al canvas (zoom 100%)."""
        return min(self.view_w / self.image.shape[1], self.view_h / self.image.shape[0])

    def _scale(self):
        return self._base_scale() * self.zoom

    def zoom_at(self, factor, cx, cy):
        """Cambia el zoom manteniendo fijo el punto bajo (cx, cy)."""
        if self.image is None:
            return

        scale = self._scale()
        px, py = self.x0 + cx / scale, self.y0 + cy / scale

        self.zoom = min(max(self.zoom * factor, 1.0), self.MAX_ZOOM)

        scale = self._scale()
        self.x0, self.y0 = px - cx / scale, py - cy / scale
        self.render()

    def _wheel(self, event):
        self.zoom_at(self.STEP if event.delta > 0 else 1 / self.STEP, event.x, event.y)

    def _start_drag(self, event):
        self.drag = (event.x, event.y)

    def _drag(self, event):
        if self.image is None or self.drag is None:
            return

        scale = self._scale()
        self.x0 -= (event.x - self.drag[0]) / scale
        self.y0 -= (event.y - self.drag[1]) / scale
        self.drag = (event.x, event.y)
        self.render()

    def render(self):
        self.delete("all")

        if self.image is None:
            return

        height, width = self.image.shape[:2]
        scale = self._scale()

        # Region visible de la imagen, limitada a sus bordes
        visible_w = min(width, self.view_w / scale)
        visible_h = min(height, self.view_h / scale)
        self.x0 = min(max(self.x0, 0.0), width - visible_w)
        self.y0 = min(max(self.y0, 0.0), height - visible_h)

        x0, y0 = int(self.x0), int(self.y0)
        crop = self.image[y0:y0 + int(np.ceil(visible_h)),
                          x0:x0 + int(np.ceil(visible_w))]

        size = (max(1, round(crop.shape[1] * scale)), max(1, round(crop.shape[0] * scale)))
        # Al ampliar se ven los pixeles reales; al reducir se suaviza
        interpolation = cv2.INTER_NEAREST if scale > 1.5 else cv2.INTER_AREA
        self.photo = to_photo(cv2.resize(crop, size, interpolation=interpolation))

        self.create_image(self.view_w / 2, self.view_h / 2, image=self.photo)

        if self.on_zoom:
            self.on_zoom(self.zoom)


# ======================================================================
# Nube de puntos
# ======================================================================

def frustum_segments(K, image_size, R, C, scale):
    """Segmentos 3D del frustum de una camara (misma geometria que Open3D)."""
    width, height = image_size
    fx, fy, cx, cy = K[0, 0], K[1, 1], K[0, 2], K[1, 2]

    corners = np.array([
        [(u - cx) / fx * scale, (v - cy) / fy * scale, scale]
        for u, v in [(0, 0), (width, 0), (width, height), (0, height)]
    ])
    corners = (R @ corners.T).T + C.reshape(1, 3)

    segments = [(C, corner) for corner in corners]
    segments += [(corners[i], corners[(i + 1) % 4]) for i in range(4)]
    return segments


def to_plot(points):
    """OpenCV (X derecha, Y abajo, Z adelante) -> grafico (X, Z, -Y)."""
    points = np.atleast_2d(points)
    return points[:, 0], points[:, 2], -points[:, 1]


# Imagenes de coincidencias que genera la reconstruccion (en OUTPUT_DIR)
MATCH_IMAGES = [
    ("Validas (inliers)", "matches_inliers.jpg"),
    ("Descartadas (outliers)", "matches_outliers.jpg"),
    ("Todas (verde: validas, rojo: descartadas)", "matches.jpg"),
]

MATCHES_WIDTH = 680  # ancho con que se muestra la imagen de coincidencias
CLOUD_ELEVATION = 20  # angulo vertical fijo de la nube 3D (solo rota horizontal)


class CloudView(tk.Frame):
    """
    Nube de puntos y camaras en un grafico 3D de matplotlib, y debajo la
    imagen de coincidencias entre las fotos 1 y 2.
    """

    def __init__(self, parent, cloud_file, cameras_file, on_back):
        super().__init__(parent, bg=BG)

        self.output_dir = os.path.dirname(cloud_file)

        import open3d as o3d
        from matplotlib.backends.backend_tkagg import (
            FigureCanvasTkAgg,
            NavigationToolbar2Tk,
        )
        from matplotlib.figure import Figure

        cloud = o3d.io.read_point_cloud(cloud_file)
        points = np.asarray(cloud.points)
        colors = np.asarray(cloud.colors) if cloud.has_colors() else None

        figure = Figure(figsize=(7.2, 3.5), dpi=100, facecolor=CARD)
        ax = figure.add_subplot(projection="3d")

        # Rotacion clasica (elevacion + acimut). Desde matplotlib 3.10 el
        # modo por defecto es "arcball", que ademas inclina la vista (roll)
        import matplotlib
        if "axes3d.mouserotationstyle" in matplotlib.rcParams:
            matplotlib.rcParams["axes3d.mouserotationstyle"] = "azel"
        ax.set_facecolor(CARD)

        # Se recorta la vista a la zona densa (los puntos aislados muy
        # lejanos achicarian todo el grafico); los datos no se modifican
        low, high = np.percentile(points, [2, 98], axis=0)
        margin = (high - low) * 0.1
        shown = np.all((points >= low - margin) & (points <= high + margin), axis=1)

        xs, ys, zs = to_plot(points[shown])
        ax.scatter(xs, ys, zs, s=6, depthshade=False,
                   c=colors[shown] if colors is not None else ACCENT)

        centers = [np.zeros(3)]
        text = f"{len(points)} puntos"

        if os.path.exists(cameras_file):
            cams = np.load(cameras_file)
            K, size = cams["K"], cams["image_size"]
            poses = [(np.eye(3), np.zeros(3)), (cams["R2"], cams["C2"]),
                     (cams["R3"], cams["C3"])]
            scale = 0.25 * np.linalg.norm(cams["C2"])

            for i, ((R, C), color) in enumerate(zip(poses, CAMERA_COLORS), start=1):
                for a, b in frustum_segments(K, size, R, C, scale):
                    ax.plot(*to_plot(np.array([a, b])), color=color, linewidth=1.5)
                ax.scatter(*to_plot(C), color=color, s=30, label=f"Camara {i}")

            centers = [C for _, C in poses]
            ax.plot(*to_plot(np.array(centers)), color="#6b7280",
                    linestyle="--", linewidth=1)
            ax.legend(loc="upper left", fontsize=8)
            text += " - 3 camaras"

        # Escala igual en los 3 ejes
        everything = np.vstack([points[shown], np.array(centers)])
        px, py, pz = to_plot(everything)
        ax.set_box_aspect((np.ptp(px), np.ptp(py), np.ptp(pz)))
        ax.set_xlabel("X")
        ax.set_ylabel("Z (profundidad)")
        ax.set_zlabel("Y")
        ax.view_init(elev=CLOUD_ELEVATION, azim=-60)
        figure.tight_layout()

        # Panel lateral
        panel = side_panel(self, width=240)
        inner = tk.Frame(panel, bg=CARD)
        inner.pack(fill="both", expand=True, padx=14, pady=12)

        label(inner, "Nube de puntos 3D", size=12, bold=True).pack(fill="x")
        label(inner, text, color=MUTED).pack(fill="x", pady=(4, 0))
        label(inner, "Arrastra con el mouse para rotar. Rueda o boton derecho "
                     "para acercar. La barra inferior permite mover y guardar "
                     "la imagen.", color=MUTED, wraplength=210).pack(fill="x", pady=(10, 0))

        label(inner, "COINCIDENCIAS (FOTOS 1 Y 2)", bold=True,
              color=ACCENT).pack(fill="x", pady=(16, 2))

        self.match_choice = tk.StringVar(value=MATCH_IMAGES[0][1])
        for text, filename in MATCH_IMAGES:
            tk.Radiobutton(inner, text=text, value=filename, variable=self.match_choice,
                           command=self.show_matches, bg=CARD, fg=TEXT, anchor="w",
                           activebackground=CARD, highlightthickness=0,
                           font=("Segoe UI", 9)).pack(fill="x")

        label(inner, "Se dibujan las mejores (MAX_DRAWN_MATCHES en config.py).",
              size=8, color=MUTED, wraplength=210).pack(fill="x", pady=(4, 0))

        # Controles de zoom de la imagen de coincidencias
        zoom_row = tk.Frame(inner, bg=CARD)
        zoom_row.pack(fill="x", pady=(8, 0))
        ttk.Button(zoom_row, text="−", width=3, style="Small.TButton",
                   command=lambda: self.matches_view.zoom_out()).pack(side="left")
        ttk.Button(zoom_row, text="+", width=3, style="Small.TButton",
                   command=lambda: self.matches_view.zoom_in()).pack(side="left", padx=4)
        ttk.Button(zoom_row, text="Ajustar", style="Small.TButton",
                   command=lambda: self.matches_view.fit()).pack(side="left")
        self.zoom_text = label(zoom_row, "100%", color=MUTED)
        self.zoom_text.pack(side="right")

        label(inner, "Rueda: zoom hacia el cursor. Arrastrar: mover. "
                     "Doble clic: ajustar.", size=8, color=MUTED,
              wraplength=210).pack(fill="x", pady=(4, 0))

        ttk.Button(inner, text="Volver al menu", style="Accent.TButton",
                   command=on_back).pack(side="bottom", fill="x")

        # Columna izquierda: grafico 3D arriba, coincidencias abajo
        column = tk.Frame(self, bg=BG)
        column.pack(side="left", fill="both", expand=True)

        # Las imagenes de coincidencias son 2 fotos lado a lado (proporcion 8:3)
        self.matches_view = ZoomableImage(
            column, MATCHES_WIDTH, MATCHES_WIDTH * 3 // 8,
            on_zoom=lambda z: self.zoom_text.configure(text=f"{z:.0%}"))
        self.matches_view.pack(side="bottom", fill="x", pady=(8, 0))
        self.show_matches()

        holder = tk.Frame(column, bg=CARD)
        holder.pack(side="top", fill="both", expand=True)

        self.canvas = FigureCanvasTkAgg(figure, master=holder)
        toolbar = NavigationToolbar2Tk(self.canvas, holder, pack_toolbar=False)
        toolbar.update()
        toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(fill="both", expand=True)
        self.canvas.draw()

        # Rotacion solo horizontal: el arrastre cambia el acimut, pero la
        # elevacion se vuelve a fijar despues de cada movimiento del mouse
        def keep_elevation(_event):
            if ax.elev != CLOUD_ELEVATION or ax.roll != 0:
                ax.view_init(elev=CLOUD_ELEVATION, azim=ax.azim, roll=0)
                self.canvas.draw_idle()

        self.canvas.mpl_connect("motion_notify_event", keep_elevation)

    def show_matches(self):
        """Muestra la imagen de coincidencias elegida (con zoom)."""
        image_path = os.path.join(self.output_dir, self.match_choice.get())
        image = cv2.imread(image_path) if os.path.exists(image_path) else None

        self.matches_view.set_image(image)

        if image is None:
            self.matches_view.create_text(MATCHES_WIDTH / 2, 40, fill="#dddddd",
                                          text=f"No existe {image_path}")
