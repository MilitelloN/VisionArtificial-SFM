# Refactor

Reorganización del proyecto **sin cambios de comportamiento**: los algoritmos, parámetros, prints y salidas son idénticos.

## Estructura

| Antes | Después |
|---|---|
| `main.py` (pipeline SfM, 790 líneas) | `sfm/reconstruction.py` |
| — | `main.py` (menú nuevo) |
| `dibuja_cam.py` | `utils/open3d_utils.py` → `create_camera_frustum` |
| `levantar_nube.py` | `utils/open3d_utils.py` → `view_point_cloud` |
| `calibration/calibrate.py` | `calibration/calibrate.py` (misma ubicación) |
| `tableroAjedrez.png` | `calibration/tablero_ajedrez.png` |
| `config.py` | `config.py` (sin cambios) |
| — | `README.md`, `requirements.txt`, `refactor.md` |
| — | `calibration/calibration.md`, `sfm/sfm.md`, `utils/utils.md` |

```
ANTES                              DESPUÉS
tpfinal/                           tpfinal/
├── main.py                        ├── main.py              (menú)
├── config.py                      ├── config.py
├── dibuja_cam.py                  ├── README.md / requirements.txt / refactor.md
├── levantar_nube.py               ├── calibration/
├── tableroAjedrez.png             │   ├── calibrate.py
├── test.txt                       │   ├── tablero_ajedrez.png
├── calibration/                   │   ├── calibration.md
│   ├── calibrate.py               │   └── images/          (vacía)
│   ├── camera_params.npz          ├── sfm/
│   └── images/ (compañero)        │   ├── reconstruction.py
├── images/ (compañero)            │   └── sfm.md
├── output/                        ├── utils/
├── output0/                       │   ├── open3d_utils.py
├── output_lej12/                  │   └── utils.md
├── output_med12/                  ├── images/              (vacía)
└── output_med23/                  ├── output/              (vacía)
                                   └── ToRemove/
```

## Cambios en el código (solo forma)
- **Scripts a funciones:** cada script pasó de ejecutarse a nivel módulo a una función `run()` / `view_point_cloud()` con `if __name__ == "__main__"`. El cuerpo es el mismo, solo indentado.
- **Imports:** `from dibuja_cam import create_camera_frustum` pasó a `from utils.open3d_utils import create_camera_frustum`.
- **Docstrings:** se agregó un docstring de cabecera en cada módulo.
- **Salida vieja de `calibrate.py`:** se quitó el string con la salida de la corrida del compañero. Era código muerto y se guardó en `ToRemove/calibrate_old_output.txt`.
- **Paquetes:** se agregaron `__init__.py` en `calibration/`, `sfm/` y `utils/`.

## Ejecución

| Antes | Después |
|---|---|
| `python calibration/calibrate.py` | `python main.py` → 1 (o `python -m calibration.calibrate`) |
| `python main.py` | `python main.py` → 2 (o `python -m sfm.reconstruction`) |
| `python levantar_nube.py` | `python main.py` → 3 (o `python -m utils.open3d_utils`) |

El menú ejecuta cada módulo desde la raiz, así que las rutas relativas de `config.py` siguen siendo válidas. Antes de las opciones 2 y 3 verifica que existan la calibración y la nube.

## Movido a `ToRemove/`
Fotos y calibración del compañero (`old_images/`, `old_calibration_images/`, `old_camera_params*.npz`), salidas viejas (`output_old/`, `output0/`, `output_*`), `test.txt`, `chatgpt-summary.md`, `claude-context.md`, `__pycache__/` y archivos `*:Zone.Identifier`.

## Cambios posteriores (nuevas funcionalidades)
- **Interfaz gráfica:** `main.py` pasó del menú de consola a una interfaz con `tkinter`. Muestra la salida de cada proceso en un panel de registro y valida los requisitos previos.
- **Calibración en dos modos:** fotos guardadas en la carpeta, o captura en vivo con el nuevo `calibration/capture.py`.
- **Constantes en `config.py`:** `CHECKERBOARD` y `SQUARE_SIZE` se movieron ahí desde `calibrate.py`, con los mismos valores. También se sumaron `CALIBRATION_IMAGES_DIR`, `CAMERA_INDEX` y `CAPTURE_WIDTH/HEIGHT`.
- **Botones por tarjeta:** calibración y reconstrucción tienen cada una un botón de captura en vivo y otro para usar las fotos de la carpeta. Durante la captura, una barra lateral fija indica qué fotografiar. Las capturas toleran frames perdidos. El registro es compacto y se puede expandir.
- **Captura guiada de la escena:** nuevo `sfm/capture.py`, con validador en vivo de textura, solapamiento y desplazamiento.
- **Cámara compartida:** nuevo `utils/camera.py`, con el código de cámara que usan ambas capturas.
- **Fotos de la escena:** `IMAGE1-3` en `config.py` ahora apuntan a `images/escena1-3.png`.
- **Borrar fotos:** cada tarjeta (calibración y escena) tiene un botón que borra las fotos de su carpeta, con confirmación previa.
- **OpenCV fijado en 4.x:** `requirements.txt` evita la versión 5.1, que falla en `findEssentialMat`.
- **Zona de interés:** nuevo `sfm/roi.py`. `reconstruction.py` pasa a SIFT una máscara con la zona elegida; si no hay zona, la máscara es `None` y el comportamiento es el original.
- **Botón Detener:** corta el proceso en curso, por ejemplo la ventana de Open3D.
- **Matching cruzado (`CROSS_CHECK` en `config.py`):** se aplica al par 1–2 y descarta coincidencias ambiguas. Con `False` vuelve al comportamiento original. No se aplica a PnP, porque `solvePnPRansac` ya filtra los outliers y sumarlo reducía demasiado las correspondencias.
- **`MAX_DRAWN_MATCHES` (`config.py`):** limita las líneas dibujadas en `matches*.jpg` a las mejores coincidencias. Solo afecta la visualización.
- **Sugerencias de posición en la captura:** el validador indica cómo mover la cámara (dirección, distancia, inclinación, altura) y muestra la mejor cantidad de coincidencias del paso. Los límites de desplazamiento pasaron a 3–15%, y a 10% en la foto 3.
- **`MAX_DRAWN_MATCHES` = 20.**
- **Ventana única:** la captura con cámara, la zona de interés y la nube 3D (matplotlib) se muestran dentro de la ventana principal. Las vistas están en el nuevo `ui/views.py`. La **X** cierra toda la app. `calibrate.py` y `reconstruction.py` aceptan `--no-gui`, para no abrir ventanas propias. `reconstruction.py` guarda además `output/cameras.npz`.
- **Sin borde de `undistort`:** SIFT ignora el borde negro que deja la corrección de distorsión, que generaba coincidencias falsas (la línea que cruzaba la imagen).
- **Capturas como sesiones:** `calibration/capture.py` y `sfm/capture.py` ya no abren ventanas de OpenCV. Exponen la lógica (`process`, `capture`) y la interfaz las muestra.
- **Coincidencias junto a la nube:** al terminar la reconstrucción, la vista de la nube 3D muestra también `matches_inliers.jpg`, `matches_outliers.jpg` o `matches.jpg`, a elección.
- **Zoom en las coincidencias:** la imagen de matches de la vista de la nube admite zoom (rueda, botones +/−) y arrastre para recorrerla.
