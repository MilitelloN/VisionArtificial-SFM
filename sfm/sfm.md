# SfM: reconstrucción 3D

**Structure from Motion**: reconstruye en 3D una escena a partir de fotos tomadas desde distintas posiciones.

Desde la interfaz hay tres opciones:
- **Capturar y reconstruir con imágenes:** abre `capture.py` (3 fotos) y después reconstruye.
- **Capturar y reconstruir en vivo:** abre `live.py`: 2 fotos, reconstrucción y PnP sobre el video.
- **Reconstruir:** usa las fotos `IMAGE1`, `IMAGE2` e `IMAGE3` de `config.py`.

## `capture.py` paso a paso
Contiene la lógica de la captura guiada; la ventana principal muestra el video.
1. Abre la cámara a la **misma resolución de la calibración**.
2. Guía 3 fotos:
   - **Foto 1:** referencia, con los objetos llenando el cuadro.
   - **Foto 2:** correrse unos cm al costado.
   - **Foto 3:** entre la 1 y la 2, para PnP.
3. Muestra a la derecha qué capturar, los pasos y los botones.
4. Muestra un **validador en vivo**, calculado con ORB sobre la foto 1:
   - Detalle y cobertura del cuadro.
   - Coincidencias con la foto 1, más la mejor cantidad lograda en el paso.
   - Desplazamiento (3–15%; 3–10% en la foto 3).
   - Cambio de distancia e inclinación.
5. Da **sugerencias de posición** (`> ...`), por ejemplo "Volvé un poco hacia la izquierda", "Acercate", "No inclines la cámara" o "Mantené la misma altura". Si todo está bien, muestra "LISTA PARA CAPTURAR".
6. **Capturar** (o **ESPACIO**) toma la foto, solo si pasa el validador. **R** rehace la anterior y **ESC** cancela.
7. Guarda las 3 fotos juntas en `images/escena1-3.png`.

## `live.py`: reconstrucción en vivo
Resuelve el opcional del TP, PnP en tiempo real. No hay foto 3: el video hace de cámara 3.
1. **`LivePairCapture`** (reutiliza el validador de `capture.py`):
   - **Foto 1:** se encuadra y se captura con **ESPACIO**.
   - **Foto 2:** la vista muestra la foto 1 fija junto a la cámara en vivo, con una línea entre cada keypoint ORB y su pareja (las 60 mejores). El matching se recalcula en cada cuadro. Con el validador en verde, **ESPACIO** saca la foto.
   - Guarda las fotos 1 y 2 y borra la 3 anterior, que no corresponde al par nuevo.
2. **Reconstrucción** con `reconstruction.py --no-pnp`.
3. **`LiveTracker`:** en cada cuadro corrige la distorsión, detecta SIFT (`LIVE_SIFT_FEATURES`), empareja contra los descriptores de la nube (`output/cloud_features.npz`) con ratio test y calcula la pose con `solvePnPRansac` (EPnP) y `solvePnPRefineLM`. Acepta la pose si tiene al menos `LIVE_MIN_INLIERS` inliers.

## `roi.py`: zona de interés
- La zona se marca con el mouse sobre la foto 1 corregida, desde la ventana principal (**Elegir zona**, o después de una captura).
- Se guarda en `images/roi.json`.
- SIFT busca puntos solo dentro de esa zona, ampliada por `ROI_MARGIN`, en las 3 fotos.
- **Quitar zona** vuelve a usar la imagen completa.

## `reconstruction.py` paso a paso
1. **Carga:** lee `IMAGE1` e `IMAGE2` y la calibración, y corrige la distorsión.
2. **Keypoints:** detecta puntos característicos con SIFT. Ignora el borde negro que deja `undistort` y, si hay zona de interés, solo busca dentro de ella.
3. **Matching:** busca correspondencias con BFMatcher, ratio test de Lowe y matching cruzado (`CROSS_CHECK`). El par A–B se acepta solo si B también elige a A.
4. **Matriz esencial:** estima `E` con RANSAC y recupera la pose relativa (`R`, `t`).
5. **Filtrado:** conserva solo las correspondencias válidas (inliers).
6. **Triangulación:** calcula los puntos 3D y descarta los que quedan detrás de las cámaras.
7. **Reproyección:** mide el error y descarta los puntos con más de `REPROJECTION_THRESHOLD` píxeles.
8. **Color:** asigna a cada punto el color del píxel en la imagen 1.
9. **Guardado:** escribe `output/point_cloud.ply` y `output/cloud_features.npz` (el descriptor SIFT de cada punto 3D, que usa el modo en vivo).
10. **PnP (opcional del TP):** estima la pose de una 3ª cámara (`IMAGE3`) contra la nube. Con `--no-pnp` se omite (modo en vivo).
11. **Exportación:** escribe `output/points_3d.csv`.
12. **Cámaras:** guarda las poses en `output/cameras.npz`.
13. **Visualización:** muestra en Open3D la nube, las 3 cámaras y su trayectoria. Con `--no-gui` se omite y la interfaz dibuja la nube en su propia ventana.

## Salidas en `output/`
En las imágenes `matches*.jpg` se dibujan como máximo `MAX_DRAWN_MATCHES` coincidencias, las de menor distancia. Es solo visual: el cálculo usa todas.

`keypoints1/2.jpg`, `matches.jpg` (válidas en verde y descartadas en rojo), `matches_inliers.jpg`, `matches_outliers.jpg`, `point_cloud.ply`, `points_3d.csv`, `cameras.npz` y `cloud_features.npz`.

Los parámetros se configuran en `config.py`.
