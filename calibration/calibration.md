# Calibración de cámara

Obtiene los parámetros intrínsecos de la cámara (`K`) y su distorsión (`dist`). La reconstrucción 3D los necesita.

Desde la interfaz hay dos opciones:
- **Usar fotos guardadas:** calibra con las fotos de `images/`.
- **Capturar con la cámara:** abre `capture.py`, sacás las fotos y después calibra.

## `capture.py` paso a paso
Contiene la lógica de la captura; la ventana principal muestra el video.
1. Abre la cámara a `CAPTURE_WIDTH`×`CAPTURE_HEIGHT` (o 640×480 si no entrega imagen).
2. Detecta el tablero en vivo y lo marca. Si se ve chico, sugiere acercarlo.
3. **Capturar** (o **ESPACIO**) guarda el frame sin dibujos como `images/capture_XX.png`, solo si detectó el tablero.
4. **Terminar** (o **ESC**) vuelve al menú y calibra.

## `calibrate.py` paso a paso
1. Toma el tablero de `config.py`: 9×6 esquinas internas y cuadros de 10 mm.
2. Genera las coordenadas 3D conocidas de cada esquina del tablero.
3. Lee todas las fotos de `images/*.png`.
4. Detecta las esquinas en cada foto y las refina a nivel subpíxel.
5. Exige al menos 8 fotos válidas.
6. Calibra con `cv2.calibrateCamera` y muestra el error RMS, `K` y `dist`.
7. Guarda los resultados en `camera_params.npz`.

Con `--no-gui`, que es como lo ejecuta la interfaz, no muestra la vista previa de cada foto.

## Archivos
| Archivo | Uso |
|---|---|
| `tablero_ajedrez.png` | Patrón para imprimir (10×7 cuadros, 9×6 esquinas internas). |
| `images/` | Fotos del tablero impreso (`.png`, 10–15, distintos ángulos). |
| `camera_params.npz` | Resultado de la calibración. Se genera al ejecutar el script. |

> Usá la misma cámara, resolución y zoom que en las fotos de la escena.
