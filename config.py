IMAGE1 = "images/escena1.png"
IMAGE2 = "images/escena2.png"
IMAGE3 = "images/escena3.png"

# Zona de interes: rectangulo elegido sobre la foto 1 (ver sfm/roi.py)
ROI_FILE = "images/roi.json"
ROI_MARGIN = 0.10   # margen extra, fraccion del ancho/alto, para fotos 2 y 3

CALIBRATION_FILE = "calibration/camera_params.npz"
CALIBRATION_IMAGES_DIR = "calibration/images"

# Tablero de calibracion
CHECKERBOARD = (9, 6)   # esquinas INTERNAS
SQUARE_SIZE = 10.0      # tamaño real del cuadrado en mm

# Camara en vivo (captura de fotos de calibracion)
CAMERA_INDEX = 0
CAPTURE_WIDTH = 640    # 1280x720 no entrega imagen por usbipd en WSL2
CAPTURE_HEIGHT = 480

OUTPUT_DIR = "output"

# SIFT
SIFT_FEATURES = 5000

# Matching
RATIO_TEST = 0.75

# Matching cruzado (imagenes 1-2): un par (A, B) se acepta solo si B tambien elige a A
CROSS_CHECK = True

# Visualizacion: maximo de lineas dibujadas en matches*.jpg (las mejores).
# Solo afecta las imagenes, no el calculo. None = dibujar todas.
MAX_DRAWN_MATCHES = 20

# Essential matrix
RANSAC_THRESHOLD = 1.0
RANSAC_CONFIDENCE = 0.999

REPROJECTION_THRESHOLD = 3.0

# PnP: estimación de la tercera cámara
PNP_REPROJECTION_THRESHOLD = 3.0
PNP_CONFIDENCE = 0.999
PNP_ITERATIONS = 2000