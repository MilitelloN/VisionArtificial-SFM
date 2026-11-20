"""
Utilidades de Open3D.

- create_camera_frustum: dibuja el cono (frustum) de una camara.
- view_point_cloud: abre y muestra una nube de puntos guardada (.ply).

Ver la nube guardada, desde la raiz del proyecto:
    python -m utils.open3d_utils
"""

import numpy as np
import open3d as o3d


def create_camera_frustum(K, image_size, R_wc, C, scale=0.7,
                          color=(1.0, 0.2, 0.1)):
    """
    Crea un frustum de cámara en coordenadas del mundo.

    K: matriz intrínseca
    image_size: (width, height)
    R_wc: rotacion de camara a mundo
    C: centro de camara en coordenadas del mundo
    scale: profundidad visual del frustum
    color: RGB
    """

    width, height = image_size

    fx = K[0, 0]
    fy = K[1, 1]
    cx = K[0, 2]
    cy = K[1, 2]

    # Esquinas del plano de imagen en coordenadas
    # de la camara. OpenCV utiliza Z hacia adelante.
    corners = [
        (0, 0),
        (width, 0),
        (width, height),
        (0, height)
    ]

    corners_camera = []

    for u, v in corners:
        x = (u - cx) / fx * scale
        y = (v - cy) / fy * scale

        corners_camera.append([x, y, scale])

    corners_camera = np.array(corners_camera)

    # Transformar las esquinas al sistema global
    corners_world = (
        R_wc @ corners_camera.T
    ).T + C.reshape(1, 3)

    # Vertice inicial: centro de camara
    vertices = np.vstack([
        C.reshape(1, 3),
        corners_world
    ])

    # Lineas: centro a esquinas + contorno del plano
    lines = [
        [0, 1],
        [0, 2],
        [0, 3],
        [0, 4],
        [1, 2],
        [2, 3],
        [3, 4],
        [4, 1]
    ]

    frustum = o3d.geometry.LineSet()

    frustum.points = o3d.utility.Vector3dVector(vertices)
    frustum.lines = o3d.utility.Vector2iVector(lines)

    colors = np.tile(
        np.array(color),
        (len(lines), 1)
    )

    frustum.colors = o3d.utility.Vector3dVector(colors)

    return frustum


def view_point_cloud():
    cloud = o3d.io.read_point_cloud(
        "output/point_cloud.ply"
    )

    print(cloud)
    print(cloud.get_min_bound())
    print(cloud.get_max_bound())

    o3d.visualization.draw_geometries([cloud])


if __name__ == "__main__":
    view_point_cloud()
