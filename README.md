# TP Final: SfM básico, triangulación de 2 vistas

## 1. Resumen

Aplicación de escritorio en Python que reconstruye en 3D una escena a partir de fotos tomadas con una cámara calibrada (**Structure from Motion** de dos vistas). Calibra la cámara con un tablero de ajedrez, guía la captura de las fotos de la escena con un validador en vivo, genera una nube de puntos 3D con color y estima la pose de una tercera cámara mediante **PnP**. Todo se maneja desde una interfaz gráfica de una sola ventana (`tkinter`).

## 2. Problema y resolución

### Consigna

Implementar un pipeline básico de SfM:

1. Calibrar la cámara para obtener la matriz intrínseca `K` y los coeficientes de distorsión.
2. Tomar 2 fotos de una escena desde posiciones distintas.
3. Detectar y emparejar puntos característicos entre ambas fotos.
4. Estimar la matriz esencial y recuperar la pose relativa entre las cámaras.
5. Triangular los puntos y obtener una nube 3D.
6. **Opcional:** estimar la pose de una 3ª cámara contra la nube con PnP.

### Cómo se resuelve

**Calibración** (`calibration/`)
- Se imprime un tablero de 10×7 cuadros (9×6 esquinas internas, cuadros de 10 mm).
- En cada foto se detectan las esquinas con `findChessboardCorners` y se refinan a nivel subpíxel con `cornerSubPix`.
- Con al menos 8 fotos válidas, `cv2.calibrateCamera` calcula `K`, `dist` y el error RMS, que se guardan en `calibration/camera_params.npz`.

**Reconstrucción** (`sfm/reconstruction.py`)
1. **Carga y corrección:** lee las fotos 1 y 2 y corrige la distorsión con `undistort`.
2. **Keypoints:** SIFT (hasta 5000 puntos) con una máscara que ignora el borde negro del `undistort` y, si se eligió, limita la búsqueda a la zona de interés.
3. **Matching:** BFMatcher con *ratio test* de Lowe (0.75) y matching cruzado: el par A–B se acepta solo si B también elige a A.
4. **Matriz esencial:** `findEssentialMat` con RANSAC y `recoverPose` para obtener `R` y `t` de la cámara 2. Se conservan solo los inliers.
5. **Triangulación:** `triangulatePoints` con las matrices de proyección de ambas cámaras. Se descartan los puntos que quedan detrás de alguna cámara.
6. **Filtro por reproyección:** se proyectan los puntos 3D en ambas imágenes y se descartan los que superan 3 px de error.
7. **Color:** cada punto toma el color de su píxel en la foto 1.
8. **PnP:** se buscan correspondencias entre la foto 3 y los puntos 3D (a través de la foto 1) y `solvePnPRansac` estima la pose de la 3ª cámara.
9. **Salidas:** `point_cloud.ply`, `points_3d.csv`, `cameras.npz` e imágenes de keypoints y coincidencias en `output/`.

**Calidad de las fotos** (`sfm/capture.py`)
Gran parte del resultado depende de las fotos. Por eso la captura de la escena tiene un validador en vivo (ORB) que controla luz, nitidez, textura, solapamiento con la foto 1, desplazamiento, distancia e inclinación, y sugiere cómo mover la cámara. Solo deja capturar cuando todo está en verde.

## 3. Scripts

| Archivo | Para qué sirve |
| --- | --- |
| `main.py` | Punto de entrada. Interfaz gráfica con las tres tarjetas (calibrar, reconstruir, ver nube), el registro y el botón Detener. Ejecuta calibración y reconstrucción como procesos aparte. |
| `config.py` | Parámetros: rutas, tablero, cámara, SIFT, matching, RANSAC, reproyección y PnP. |
| `calibration/capture.py` | Lógica de la captura en vivo del tablero: lo detecta en cada frame y guarda las fotos válidas. |
| `calibration/calibrate.py` | Calibra la cámara con las fotos de `calibration/images/` y guarda `camera_params.npz`. |
| `calibration/tablero_ajedrez.png` | Patrón para imprimir. |
| `sfm/capture.py` | Captura guiada de las 3 fotos de la escena, con validador y sugerencias de posición. |
| `sfm/roi.py` | Guarda, carga y convierte en máscara la zona de interés elegida sobre la foto 1. |
| `sfm/reconstruction.py` | Pipeline SfM completo: SIFT, matching, matriz esencial, triangulación, filtrado, PnP y exportación. |
| `ui/views.py` | Vistas de la ventana: cámara en vivo, selección de zona, nube 3D (matplotlib) e imagen con zoom. |
| `utils/camera.py` | Abre la cámara y lee frames en un hilo aparte, tolerando frames perdidos. |
| `utils/open3d_utils.py` | Dibuja el frustum de una cámara y abre una nube `.ply` en Open3D. |

Cada carpeta tiene un `.md` con el detalle de sus módulos.

## 4. Preparación del entorno e instalación

Requiere **Python 3.10+**. Las dependencias están en `requirements.txt` (`opencv-python` 4.x, `numpy`, `open3d`, `matplotlib`).

### Linux

```bash
sudo apt install python3-venv python3-tk    # tkinter no viene con pip
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Windows

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

El instalador oficial de python.org ya incluye `tkinter` (opción *tcl/tk and IDLE*). Si PowerShell bloquea el script de activación: `Set-ExecutionPolicy -Scope CurrentUser RemoteSigned`.

## 5. Modo de uso

Desde la raíz del proyecto, con el entorno activado:

```bash
python main.py
```

Se abre una ventana con tres tarjetas. La captura, la zona de interés y la nube se muestran dentro de la misma ventana, y la **X** cierra toda la app. Cada tarjeta indica su estado (fotos disponibles, calibración, nube). La salida de cada proceso aparece en el **Registro**, que se puede expandir, limpiar o cortar con **■ Detener**.

### 5.1. Calibrar cámara

**Objetivo:** obtener `K` y la distorsión de la cámara. Sin calibración no se puede reconstruir, y un `K` malo deforma toda la nube.

**Botones:**
- **Capturar y calibrar:** abre la cámara en vivo. Cuando se detecta el tablero se dibujan sus esquinas y se habilita **Capturar** (o **ESPACIO**), que guarda la foto sin dibujos en `calibration/images/capture_XX.png`. **Terminar** (o **ESC**) cierra la cámara y calibra.
- **Calibrar:** calibra con las fotos `.png` que ya estén en `calibration/images/`.
- **Borrar fotos:** borra las fotos del tablero, con confirmación.

**Cómo lograr el mejor resultado:**
- Tablero impreso, plano (pegado a un cartón) y completo en la imagen.
- Entre **10 y 15 fotos** (mínimo 8), variando ángulo e inclinación y llevando el tablero a los bordes y esquinas del cuadro. Así se estima bien la distorsión, que es mayor en los bordes.
- Que el tablero ocupe la mitad del ancho de la imagen o más.
- Sin fotos movidas ni reflejos.
- **Misma cámara, resolución y zoom** que se usarán en la escena. Si cambia algo, hay que recalibrar.
- Un error RMS por debajo de ~0.5 px indica una buena calibración.

### 5.2. Reconstruir escena

**Objetivo:** generar la nube de puntos 3D de la escena y las poses de las 3 cámaras.

**Botones:**
- **Capturar y reconstruir:** captura guiada de 3 fotos a la misma resolución de la calibración.
  - **Foto 1 (referencia):** los objetos con detalle llenan el cuadro.
  - **Foto 2:** correrse unos cm al costado, a la misma distancia y altura.
  - **Foto 3 (PnP):** ubicarse entre la 1 y la 2, apuntando a lo mismo.

  El panel lateral muestra el validador (luz, nitidez, detalle, coincidencias con la foto 1 y la mejor cantidad lograda, desplazamiento, distancia e inclinación) y sugerencias como *"Volvé un poco hacia la izquierda"*, *"Acercate"* o *"No inclines la cámara"*. **Capturar** (o **ESPACIO**) solo funciona con "LISTA PARA CAPTURAR". **R** rehace la foto anterior y **ESC** cancela. Al terminar ofrece marcar la zona de interés y luego reconstruye.
- **Reconstruir:** usa las fotos ya guardadas en `images/escena1-3.png`. Antes verifica que existan, que tengan la misma resolución entre sí y que coincida con la de la calibración.
- **Elegir zona / Quitar zona:** se marca con el mouse un rectángulo sobre la foto 1. SIFT solo busca puntos ahí (con un margen del 10%) y el fondo deja de aportar coincidencias falsas.
- **Borrar fotos:** borra las fotos de la escena, con confirmación.

Al terminar se abre la vista de la nube junto con la imagen de coincidencias.

**Cómo lograr el mejor resultado:**
- Objetos con mucha textura: libros, cajas, revistas, superficies con detalle impreso. Evitar paredes lisas, vidrios y superficies brillantes.
- Con una cámara de baja resolución, acercarse (30–60 cm) para que los detalles se vean grandes.
- **Trasladar, no girar:** correrse al costado sin rotar ni inclinar la cámara. Un desplazamiento del 3–15% del ancho da buena base para triangular sin perder solapamiento. Si es muy chico, la profundidad sale con mucho ruido; si es muy grande, hay pocas coincidencias.
- Buena luz, sin sombras que cambien entre fotos, y la cámara quieta al capturar.
- Seguir las sugerencias hasta que todo esté en verde y apuntar a más de 150 coincidencias.
- Marcar la zona de interés cuando el fondo es liso o lejano.
- En el registro, revisar los inliers de la matriz esencial y el error de reproyección: muchos inliers y error medio de 1 px o menos indican una buena reconstrucción.

### 5.3. Ver nube guardada

**Objetivo:** inspeccionar el último resultado sin volver a reconstruir.

Muestra `output/point_cloud.ply` con las 3 cámaras (frustums, centros y trayectoria) en un gráfico 3D que se rota con el mouse, y la barra inferior permite mover y guardar la imagen. La vista se recorta a la zona densa de puntos sin modificar los datos.

Debajo se ve la imagen de coincidencias entre las fotos 1 y 2. En el panel lateral se elige entre **válidas** (inliers), **descartadas** (outliers) o **todas**. Se dibujan solo las 20 mejores (`MAX_DRAWN_MATCHES`) para que se lean. La imagen admite zoom hasta 800% (rueda del mouse o botones **−**/**+**), se arrastra para recorrerla y con doble clic o **Ajustar** vuelve a encajar.

Sirve para validar el resultado: las líneas válidas deberían unir los mismos puntos de la escena y ser aproximadamente paralelas.

## 6. Versiones

**Primera versión.** Un conjunto de scripts sueltos que se ejecutaban por consola:
- `calibration/calibrate.py` para calibrar y `main.py` con todo el pipeline SfM en unas 790 líneas a nivel módulo.
- `dibuja_cam.py` para los frustums y `levantar_nube.py` para ver la nube.
- Las fotos se sacaban aparte y se copiaban a mano a las carpetas. Los resultados se veían en ventanas separadas de OpenCV y Open3D.

**Versión actual.**
- **Refactor:** el código se organizó en paquetes (`calibration/`, `sfm/`, `ui/`, `utils/`) con funciones `run()`, sin cambiar los algoritmos. Las constantes se centralizaron en `config.py`.
- **Interfaz gráfica** de una sola ventana con tarjetas, registro, botón Detener y validación de requisitos previos (calibración, fotos, resoluciones).
- **Captura en vivo** del tablero y **captura guiada** de la escena con validador y sugerencias de posición.
- **Zona de interés**, **matching cruzado** y máscara del borde de `undistort` para reducir coincidencias falsas.
- **Visor propio** de la nube 3D y las cámaras con matplotlib, junto a la imagen de coincidencias con zoom.

## 7. Problemas resueltos

| Problema | Solución |
| --- | --- |
| OpenCV 5.x falla en `findEssentialMat` con datos reales. | Se fijó `opencv-python>=4.10,<5`. |
| El borde negro de `undistort` generaba coincidencias falsas (una línea que cruzaba la imagen). | Máscara para SIFT que excluye ese borde. |
| El fondo aportaba coincidencias sin sentido. | Zona de interés elegida sobre la foto 1. |
| Coincidencias ambiguas entre las fotos 1 y 2. | Matching cruzado (`CROSS_CHECK`). En PnP no se aplica porque reducía demasiado las correspondencias y RANSAC ya filtra outliers. |
| Fotos de escena malas (poco solapamiento, cámara girada, desenfoque). | Validador en vivo con sugerencias; solo captura cuando todo está bien. |
| Fotos y calibración con distinta resolución. | La escena se captura a la resolución de la calibración y se valida antes de reconstruir. |
| Muchas ventanas sueltas y la de Open3D bloqueaba la app. | Ventana única; los procesos corren con `--no-gui` y la interfaz muestra la nube con matplotlib. |
| Las imágenes de coincidencias eran ilegibles. | Solo se dibujan las 20 mejores (solo visual) y la imagen admite zoom. |

## 8. Tecnologías

| Tecnología | Uso en la app |
| --- | --- |
| **Python 3** | Lenguaje de toda la aplicación. |
| **OpenCV** (`opencv-python` 4.x) | Visión artificial: captura de la cámara, detección del tablero (`findChessboardCorners`, `cornerSubPix`), calibración (`calibrateCamera`), corrección de distorsión (`undistort`), keypoints SIFT y ORB, matching con BFMatcher, matriz esencial y pose (`findEssentialMat`, `recoverPose`), triangulación (`triangulatePoints`), PnP (`solvePnPRansac`) y dibujo de keypoints y coincidencias. |
| **NumPy** | Álgebra lineal y manejo de arreglos: matrices de proyección, puntos 3D, máscaras, errores de reproyección y archivos `.npz`. |
| **Open3D** | Guardado y lectura de la nube (`.ply`), frustums de las cámaras y visor 3D por consola. |
| **Matplotlib** | Visor 3D de la nube y las cámaras dentro de la ventana (backend `TkAgg`). |
| **tkinter / ttk** | Interfaz gráfica de una sola ventana: tarjetas, registro, vistas de cámara, zona de interés e imagen con zoom. |
| **Biblioteca estándar** | `subprocess` (calibración y reconstrucción como procesos aparte), `threading` y `queue` (lectura de la cámara y de la salida de los procesos sin trabar la interfaz), `json` (zona de interés), `glob`, `os` y `sys` (archivos, rutas y argumentos como `--no-gui`). |
| **Formatos de archivo** | `.png` (fotos), `.npz` (calibración y cámaras), `.json` (zona de interés), `.ply` (nube de puntos), `.csv` (coordenadas 3D) y `.jpg` (keypoints y coincidencias). |

## 9. Glosario

Definiciones basadas en el material de la materia (carpeta `teoria/`), salvo donde se indica.

| Concepto | Definición |
| --- | --- |
| **BFMatcher** (*Brute-Force Matcher*) | Emparejador de OpenCV por fuerza bruta: compara cada descriptor de una imagen con todos los de la otra y elige el de menor distancia (L2 para SIFT, Hamming para ORB). Es lento pero exacto; `knnMatch` devuelve los *k* mejores, que es lo que necesita el ratio test. |
| **Coeficientes de distorsión** | Parámetros del modelo que describe cuánto se aparta la lente de una proyección ideal que conserva las rectas (colineación). Incluyen la distorsión **radial** (`k1`, `k2`, `k3`), presente en todas las cámaras comunes, y la **tangencial** (`p1`, `p2`), poco frecuente. Valen cero si no hay distorsión. Con ellos, `undistort` corrige la imagen. |
| **`dist`** | Nombre de la variable que guarda los coeficientes de distorsión (`k1, k2, p1, p2, k3`) en `camera_params.npz`. |
| **Distancia de Hamming** | Distancia entre dos descriptores binarios: la cantidad de bits en que difieren. Se calcula como `popCount(V1 xor V2)`, por eso es muy rápida. Se usa exclusivamente con descriptores binarios como BRIEF y ORB (máximo 256 para ORB). En esta app la usa el validador en vivo (ORB con `BFMatcher(NORM_HAMMING)`); para los descriptores de SIFT, que son *float*, se usa la distancia euclidiana (L2). |
| **Error de reproyección** | Distancia en píxeles entre un keypoint detectado y la proyección del punto 3D que le corresponde. Mide la calidad de la triangulación y de la pose; la triangulación y el *bundle adjustment* buscan minimizarlo. |
| **Error RMS** | Raíz del error cuadrático medio entre las esquinas detectadas del tablero y las que predice el modelo calibrado, en píxeles. Cuanto más bajo, mejor la calibración. *(No figura en `teoria/`.)* |
| **Frustum** | Pirámide que representa a una cámara en una vista 3D: el vértice es el centro óptico y la base es el plano de imagen. Muestra dónde está la cámara y hacia dónde mira. *(En `teoria/` se describe como "pirámide de base rectangular, con el foco en el vértice principal".)* |
| **Inliers / outliers** | Inliers: coincidencias consistentes con el modelo estimado (por ejemplo, con la matriz esencial). Outliers: coincidencias falsas o redundantes, que se descartan. |
| **Keypoints** | Puntos característicos de la escena, usualmente esquinas, que se pueden volver a detectar en otras imágenes de la misma escena. No son píxeles sino puntos geométricos (sus coordenadas pueden no ser enteras) y pueden tener orientación, tamaño y puntaje. |
| **Matching cruzado** (*cross check*) | Chequeo que acepta un par A–B solo si A elige a B y B también elige a A. Evita que varios descriptores se asignen al mismo y reduce outliers. |
| **Matriz esencial `E`** | Matriz 3×3 que encapsula la rotación y la traslación entre dos cámaras calibradas. Cumple la restricción epipolar: para un par de puntos correspondientes, `x1ᵀ E x2 = 0`. Al descomponerla se obtiene la pose relativa. |
| **Matriz intrínseca `K`** | Matriz 3×3 con los parámetros internos de la cámara: distancia focal en píxeles (`fx`, `fy`) y punto principal (`cx`, `cy`). Convierte coordenadas focales en píxeles. Varía entre unidades del mismo modelo y se obtiene con la calibración. |
| **Nube de puntos 3D con color** | Conjunto de puntos con su posición 3D, obtenida por triangulación de keypoints emparejados, y el color del píxel del que provienen. Se guarda en formatos estándar como `.ply`. Esta app genera una nube **dispersa**: solo los puntos que se pudieron emparejar. **Otras opciones:** la nube **densa** (millones de puntos, horas de cálculo, orientada a visualización), guardar también un **descriptor** por punto para relocalizar la cámara, generar una **malla o modelo 3D** de superficies (etapa posterior a SfM) o calcular un **mapa de disparidad o profundidad** por píxel con un par estéreo rectificado. |
| **ORB** (*Oriented FAST and Rotated BRIEF*) | Detector y descriptor rápido. Usa FAST en pirámides para detectar keypoints y un descriptor BRIEF binario de 256 bits, girado según la orientación del keypoint. Es más rápido que SIFT, por eso esta app lo usa en el validador en vivo. |
| **PnP** (*Perspective-n-Point*) | Obtiene la pose de una cámara a partir de correspondencias entre puntos 3D conocidos y sus proyecciones 2D en una sola imagen. Necesita la calibración de la cámara. Con 4 correspondencias suele haber solución única; con más se usan métodos robustos como `solvePnPRansac`. |
| **Pose** | Posición y orientación de un cuerpo rígido (o de una cámara) en un sistema de coordenadas. Se expresa con una rotación `R` y una traslación `t`, o como una matriz 4×4 en coordenadas homogéneas. |
| **Pose relativa** | Pose de la cámara 2 respecto de la cámara 1, que se toma como origen del mundo. Necesita al menos 5 correspondencias y tiene 4 soluciones posibles: la correcta es la que deja los puntos delante de ambas cámaras. |
| **`R` y `t`** | Componentes de la pose relativa que devuelve `recoverPose` a partir de `E`. `R` es la matriz de rotación 3×3 de la cámara 2 respecto de la 1. `t` es el vector de traslación, de **módulo unitario**: solo indica la dirección, porque con imágenes no se puede conocer la escala real. Por eso la nube queda en unidades arbitrarias. |
| **RANSAC** (*Random Sample Consensus*) | Método robusto de estimación: prueba modelos con subconjuntos aleatorios mínimos de datos y se queda con el que más datos explica (inliers), ignorando los outliers. Se usa en la matriz esencial y en PnP. *(En `teoria/` aparece solo como método robusto de `solvePnPRansac`.)* |
| **Ratio test de Lowe** | Filtro de coincidencias: se compara la distancia del mejor candidato con la del segundo. Si son parecidas, el emparejamiento es ambiguo y se descarta. Se acepta solo si el primero es claramente mejor (en esta app, menor al 75% del segundo). |
| **SfM** (*Structure from Motion*) | "Estructura a partir del movimiento": técnicas que obtienen la estructura 3D de una escena (la nube de puntos y la pose de cada cámara) a partir de *features* de varias imágenes tomadas desde distintas posiciones. El término viene de la biología: entender una estructura observándola mientras uno se desplaza a su alrededor. |
| **SIFT** (*Scale Invariant Feature Transform*) | Detector y descriptor de keypoints (Lowe, 2004). Busca *features* en pirámides de imágenes, lo que lo hace invariante a la escala, y orienta cada keypoint para ser invariante a la rotación. Su descriptor es un vector de 128 valores *float*. |
