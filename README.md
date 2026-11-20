# TP Final: SfM básico, triangulación de 2 vistas

Reconstruye en 3D una escena a partir de 2 fotos tomadas con una cámara calibrada. Además estima la pose de una 3ª cámara mediante PnP.

## Instalación

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```
Requiere `tkinter`. En Linux: `sudo apt install python3-tk`.

## Uso

```bash
python main.py
```

Se abre una interfaz de **una sola ventana**. La captura con cámara, la zona de interés y la nube 3D se muestran dentro de ella, y la **X** cierra toda la app. La salida de cada proceso aparece en el *Registro*, que se puede expandir.

| Tarjeta            | Botones                                                                                  |
| ------------------ | ---------------------------------------------------------------------------------------- |
| Calibrar cámara    | **Capturar y calibrar** · **Calibrar** (fotos de `calibration/images/`) · **Borrar fotos** |
| Reconstruir escena | **Capturar y reconstruir** (con validador) · **Reconstruir** (fotos de `images/`) · **Borrar fotos** |
| Ver nube guardada  | Nube 3D y cámaras, rotable con el mouse                                                  |

## Preparación

1. Imprimí `calibration/tablero_ajedrez.png` y sacale 10–15 fotos `.png` → `calibration/images/`, o capturalas desde la app con la cámara.
2. Sacá 3 fotos de la escena con mucho solapamiento → `images/escena1-3.png` (o capturalas desde la app).

Usá la misma cámara, resolución y zoom en todas las fotos.

## Estructura

```
main.py            interfaz gráfica (tkinter)
ui/                vistas de la ventana (cámara, zona, nube 3D)
config.py          parámetros (rutas, SIFT, RANSAC, PnP)
calibration/       calibración de la cámara
sfm/               reconstrucción 3D
utils/             utilidades de Open3D
images/            fotos de la escena
output/            resultados
```
