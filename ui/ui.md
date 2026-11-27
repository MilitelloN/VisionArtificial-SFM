# Interfaz

La app usa **una sola ventana** (`main.py`). El menú de tarjetas se reemplaza por la vista que corresponda, y la **X** cierra toda la app (cámara, procesos y vistas).

## `views.py`
- **`CameraView`:** video en vivo de la cámara, leído en segundo plano por `utils/camera.py`. A la derecha muestra:
  - El estado del validador y las sugerencias para corregir la posición.
  - Los pasos y qué capturar.
  - Los botones **Capturar**, **Rehacer anterior** y **Terminar/Cancelar**.
  - Atajos: **ESPACIO**, **R** y **ESC**.
  - La usan la captura de calibración, la de escena y la del par en vivo (con la foto 1 fija junto a la cámara).
- **`RoiView`:** foto 1 corregida, para marcar la zona de interés arrastrando el mouse.
- **`CloudView`:** nube de puntos 3D y las cámaras (frustums, centros y trayectoria) en un gráfico de matplotlib. Muestra 3 cámaras, o 2 si se reconstruyó en vivo. Debajo muestra la imagen de coincidencias entre las fotos 1 y 2, y en el panel lateral se elige entre válidas, descartadas o todas (válidas en verde y descartadas en rojo).
  - Se rota con el mouse, solo en horizontal, y la barra inferior permite mover y guardar la imagen.
  - La vista se recorta a la zona densa de puntos, sin modificar los datos.
- **`ZoomableImage`:** imagen con zoom de hasta 800%. La rueda del mouse acerca hacia el cursor, arrastrar mueve la imagen y el doble clic la ajusta. También tiene botones **−**, **+** y **Ajustar**. Al ampliar se ven los píxeles reales, sin suavizar.
- **`LiveView`:** PnP en vivo. Un hilo aparte ubica la cámara en cada cuadro (`sfm/live.py`) sin trabar la interfaz.
  - **Video:** la nube proyectada con la pose calculada (puntos de color) y los inliers (círculos verdes).
  - **Columna central:** gráfico 3D con la nube, las cámaras 1 y 2 y la cámara en vivo con su recorrido. Se gira solo en horizontal.
  - **Panel:** correspondencias 2D-3D, inliers, error de reproyección, posición y cuadros por segundo. **ESC** termina.

La calibración y la reconstrucción corren como procesos aparte, con `--no-gui` para que no abran ventanas, y su salida aparece en el *Registro*.
