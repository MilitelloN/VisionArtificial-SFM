# Utilidades

## `open3d_utils.py`
- **`create_camera_frustum(...)`:** arma el cono (frustum) de una cámara. Usa `K`, el tamaño de imagen y la pose, y proyecta las 4 esquinas de la imagen a una profundidad `scale`. La reconstrucción lo usa para dibujar las cámaras.
- **`view_point_cloud()`:** abre `output/point_cloud.ply`, imprime cantidad de puntos y límites, y la muestra. Se usa al ejecutar el módulo por consola; la interfaz tiene su propio visor.

## `camera.py`
- **`open_camera(...)`:** abre la cámara en MJPG, que es necesario en WSL2, y verifica que entregue imagen a la resolución pedida.
- **`CameraStream`:** lee frames en un hilo aparte, tolera fallas puntuales y prueba varias resoluciones. Así la interfaz no se traba.
