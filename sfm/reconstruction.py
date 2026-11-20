"""
Reconstruccion 3D por Structure from Motion (SfM) de dos vistas.

Pipeline: carga + undistort -> SIFT -> matching -> matriz esencial ->
pose relativa -> triangulacion -> filtro por reproyeccion -> color ->
guardado de la nube -> PnP de una tercera camara -> visualizacion Open3D.

Ejecutar desde la raiz del proyecto:
    python -m sfm.reconstruction
"""

import cv2
import numpy as np
import open3d as o3d
import os
import sys

from config import *
from utils.open3d_utils import create_camera_frustum
from sfm.roi import load_roi, roi_mask


def reverse_matches(matcher, des_a, des_b):
    """
    Para el matching cruzado: indice del mejor vecino en A de cada
    descriptor de B. Si CROSS_CHECK esta desactivado devuelve None.
    """
    if not CROSS_CHECK:
        return None

    return {m.queryIdx: m.trainIdx for m in matcher.match(des_b, des_a)}


def is_mutual(m, reverse):
    """True si el par m tambien es el mejor en sentido inverso."""
    return reverse is None or reverse.get(m.trainIdx) == m.queryIdx


def best_for_drawing(matches):
    """Las MAX_DRAWN_MATCHES coincidencias de menor distancia, para dibujar."""
    if MAX_DRAWN_MATCHES is None:
        return matches

    return sorted(matches, key=lambda m: m.distance)[:MAX_DRAWN_MATCHES]


def run(show=True):
    # ==========================================================
    # 1. CARGAR IMAGENES Y CALIBRACION
    # ==========================================================

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    img1 = cv2.imread(IMAGE1)
    img2 = cv2.imread(IMAGE2)

    if img1 is None or img2 is None:
        raise RuntimeError("No se pudieron cargar las imagenes")

    if img1.shape != img2.shape:
        raise RuntimeError("Las imagenes deben tener igual resolucion")

    calib = np.load(CALIBRATION_FILE)

    K = calib["K"]
    dist = calib["dist"]

    print("Matriz K:")
    print(K)

    # Corregir distorsion
    img1 = cv2.undistort(img1, K, dist)
    img2 = cv2.undistort(img2, K, dist)

    gray1 = cv2.cvtColor(img1, cv2.COLOR_BGR2GRAY)
    gray2 = cv2.cvtColor(img2, cv2.COLOR_BGR2GRAY)

    print("Resolución imagen 1:", img1.shape)
    print("Resolución imagen 2:", img2.shape)

    print("Resolución calibración:", calib["image_size"])
    print("Error RMS:", calib["rms"])


    # ==========================================================
    # 2. DETECCION DE KEYPOINTS CON SIFT
    # ==========================================================

    sift = cv2.SIFT_create(
        nfeatures=10000,
        contrastThreshold=0.02,
        edgeThreshold=15
    )

    # Zona valida: se excluye el borde negro que deja undistort, cuyos
    # bordes artificiales generan coincidencias falsas
    valid_region = cv2.undistort(np.full(gray1.shape, 255, np.uint8), K, dist)
    valid_region = cv2.erode(
        np.where(valid_region > 250, 255, 0).astype(np.uint8),
        np.ones((15, 15), np.uint8)
    )

    # Zona de interes: si existe, SIFT busca solo dentro de ella
    mask = roi_mask(gray1.shape)

    if mask is not None:
        print("\nZona de interes activa:", load_roi())
        mask = cv2.bitwise_and(mask, valid_region)
    else:
        mask = valid_region

    kp1, des1 = sift.detectAndCompute(gray1, mask)
    kp2, des2 = sift.detectAndCompute(gray2, mask)

    print("\nKEYPOINTS")
    print("Imagen 1:", len(kp1))
    print("Imagen 2:", len(kp2))

    if des1 is None or des2 is None:
        raise RuntimeError("No se detectaron descriptores")

    # Visualizar keypoints
    keypoints_img1 = cv2.drawKeypoints(
        img1,
        kp1,
        None,
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
    )

    keypoints_img2 = cv2.drawKeypoints(
        img2,
        kp2,
        None,
        flags=cv2.DRAW_MATCHES_FLAGS_DRAW_RICH_KEYPOINTS
    )

    cv2.imwrite(
        f"{OUTPUT_DIR}/keypoints1.jpg",
        keypoints_img1
    )

    cv2.imwrite(
        f"{OUTPUT_DIR}/keypoints2.jpg",
        keypoints_img2
    )


    # ==========================================================
    # 3. MATCHING
    # ==========================================================

    matcher = cv2.BFMatcher(
        cv2.NORM_L2
    )

    matches = matcher.knnMatch(
        des1,
        des2,
        k=2
    )

    reverse12 = reverse_matches(matcher, des1, des2)

    good_matches = []

    for pair in matches:

        if len(pair) < 2:
            continue

        m, n = pair

        if m.distance < RATIO_TEST * n.distance and is_mutual(m, reverse12):
            good_matches.append(m)

    print("\nMATCHING")
    print("Matching cruzado:", "activo" if CROSS_CHECK else "inactivo")
    print("Correspondencias:", len(good_matches))

    if len(good_matches) < 8:
        raise RuntimeError(
            "No hay suficientes correspondencias para estimar E"
        )

    matches_img = cv2.drawMatches(
        img1,
        kp1,
        img2,
        kp2,
        best_for_drawing(good_matches),
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
    )

    cv2.imwrite(
        f"{OUTPUT_DIR}/matches.jpg",
        matches_img
    )


    # Obtener coordenadas de los keypoints
    pts1 = np.float32([
        kp1[m.queryIdx].pt for m in good_matches
    ])

    pts2 = np.float32([
        kp2[m.trainIdx].pt for m in good_matches
    ])


    # ==========================================================
    # 4. MATRIZ ESENCIAL
    # ==========================================================

    E, mask = cv2.findEssentialMat(
        pts1,
        pts2,
        K,
        method=cv2.RANSAC,
        prob=RANSAC_CONFIDENCE,
        threshold=RANSAC_THRESHOLD
    )

    if E is None:
        raise RuntimeError("No se pudo calcular la matriz esencial")

    print("\nMATRIZ ESENCIAL:")
    print(E)

    # Recuperar pose relativa
    inliers, R, t, pose_mask = cv2.recoverPose(
        E,
        pts1,
        pts2,
        K,
        mask=mask
    )

    print("\nPOSE DE CAMARA")
    print("Rotacion:")
    print(R)

    print("Traslacion:")
    print(t)

    print("Inliers:", inliers)

    # ==========================================================
    # VISUALIZAR CORRESPONDENCIAS VALIDAS Y DESCARTADAS
    # ==========================================================

    inlier_mask = pose_mask.ravel() > 0

    inlier_matches = [
        m for m, valid in zip(good_matches, inlier_mask)
        if valid
    ]

    outlier_matches = [
        m for m, valid in zip(good_matches, inlier_mask)
        if not valid
    ]

    print("Inliers:", len(inlier_matches))
    print("Outliers:", len(outlier_matches))

    # Dibujar solamente correspondencias válidas
    img_inliers = cv2.drawMatches(
        img1,
        kp1,
        img2,
        kp2,
        best_for_drawing(inlier_matches),
        None,
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
    )

    cv2.imwrite(
        f"{OUTPUT_DIR}/matches_inliers.jpg",
        img_inliers
    )

    # Dibujar correspondencias descartadas
    img_outliers = cv2.drawMatches(
        img1,
        kp1,
        img2,
        kp2,
        best_for_drawing(outlier_matches),
        None,
        matchColor=(0, 0, 255),
        flags=cv2.DrawMatchesFlags_NOT_DRAW_SINGLE_POINTS
    )

    cv2.imwrite(
        f"{OUTPUT_DIR}/matches_outliers.jpg",
        img_outliers
    )


    # ==========================================================
    # 5. FILTRAR CORRESPONDENCIAS VALIDAS
    # ==========================================================

    valid = pose_mask.ravel() > 0

    pts1_valid = pts1[valid]
    pts2_valid = pts2[valid]

    print("Puntos validos:", len(pts1_valid))


    # ==========================================================
    # 6. TRIANGULACION
    # ==========================================================

    # Convertir coordenadas de pixeles a coordenadas normalizadas
    pts1_norm = cv2.undistortPoints(
        pts1_valid.reshape(-1, 1, 2),
        K,
        None
    )

    pts2_norm = cv2.undistortPoints(
        pts2_valid.reshape(-1, 1, 2),
        K,
        None
    )

    pts1_norm = pts1_norm.reshape(-1, 2).T
    pts2_norm = pts2_norm.reshape(-1, 2).T

    # Primera camara: origen del sistema de coordenadas
    P1 = np.hstack((
        np.eye(3),
        np.zeros((3, 1))
    ))

    # Segunda camara: transformacion relativa
    P2 = np.hstack((
        R,
        t
    ))

    # Triangulacion
    points_4d = cv2.triangulatePoints(
        P1,
        P2,
        pts1_norm,
        pts2_norm
    )

    # Coordenadas homogeneas -> cartesianas
    points_3d = (
        points_4d[:3] / points_4d[3]
    ).T

    # Profundidad respecto a ambas camaras
    depth1 = points_3d[:, 2]

    points_cam2 = (
        R @ points_3d.T + t
    ).T

    depth2 = points_cam2[:, 2]

    # Descartar puntos en el infinito, detras de las camaras
    valid_3d = (
        np.isfinite(points_3d).all(axis=1) &
        (np.abs(points_4d[3]) > 1e-8) &
        (depth1 > 0) &
        (depth2 > 0)
    )

    points_3d = points_3d[valid_3d]

    print("\nTRIANGULACION")
    print("Puntos 3D:", len(points_3d))

    # Índices de los puntos que sobrevivieron a la triangulación
    idx_tri = np.where(valid_3d)[0]


    ###

    # ==========================================================
    # VALIDACION: ERROR DE REPROYECCION
    # ==========================================================

    # Puntos 3D correspondientes a ambas imágenes
    p3d = points_3d.astype(np.float64)

    # Proyección sobre cámara 1
    projected1, _ = cv2.projectPoints(
        p3d,
        np.zeros(3),
        np.zeros(3),
        K,
        None
    )

    projected1 = projected1.reshape(-1, 2)

    # Proyección sobre cámara 2
    rvec2, _ = cv2.Rodrigues(R)

    projected2, _ = cv2.projectPoints(
        p3d,
        rvec2,
        t,
        K,
        None
    )

    projected2 = projected2.reshape(-1, 2)

    # Comparar con los keypoints originales
    error1 = np.linalg.norm(
        projected1 - pts1_valid[valid_3d],
        axis=1
    )

    error2 = np.linalg.norm(
        projected2 - pts2_valid[valid_3d],
        axis=1
    )

    print("\n===== ERROR DE REPROYECCION =====")

    print("Error medio camara 1:", error1.mean())
    print("Error medio camara 2:", error2.mean())

    print("Error maximo camara 1:", error1.max())
    print("Error maximo camara 2:", error2.max())


    # ==========================================================
    # FILTRADO POR ERROR DE REPROYECCION
    # ==========================================================

    # Un punto debe tener bajo error en las DOS imágenes
    good_reprojection = (
        (error1 < REPROJECTION_THRESHOLD) &
        (error2 < REPROJECTION_THRESHOLD)
    )

    print("\n===== FILTRO DE REPROYECCION =====")

    print("Puntos antes:", len(points_3d))
    print("Puntos aceptados:", np.sum(good_reprojection))
    print("Puntos descartados:", np.sum(~good_reprojection))

    # Conservar los puntos de buena calidad
    points_3d = points_3d[good_reprojection]

    # Índices finales (respecto a pts1_valid)
    idx_final = idx_tri[good_reprojection]

    # Índice del keypoint de img1 correspondiente a cada punto 3D
    kp1_idx_all = np.array([m.queryIdx for m in good_matches])
    kp1_final = kp1_idx_all[valid][idx_final]


    ##
    # ==========================================================
    # EVALUACION DESPUES DEL FILTRADO
    # ==========================================================

    error1_filtered = error1[good_reprojection]
    error2_filtered = error2[good_reprojection]

    print("\n===== ERRORES DESPUES DEL FILTRADO =====")

    print("Camara 1:")
    print("  Media:", error1_filtered.mean())
    print("  Maximo:", error1_filtered.max())

    print("Camara 2:")
    print("  Media:", error2_filtered.mean())
    print("  Maximo:", error2_filtered.max())

    print("\nError combinado medio:",
          np.mean((error1_filtered + error2_filtered) / 2))

    # Conservar también sus keypoints originales
    pts1_for_colors = pts1_valid[valid_3d][good_reprojection]

    print("Puntos finales:", len(points_3d))

    if len(points_3d) == 0:
        raise RuntimeError("No quedaron puntos luego del filtrado")


    # ==========================================================
    # 7. ASIGNAR COLOR A LOS PUNTOS FILTRADOS
    # ==========================================================

    colors = []

    for p in pts1_for_colors:

        x = int(round(p[0]))
        y = int(round(p[1]))

        x = np.clip(x, 0, img1.shape[1] - 1)
        y = np.clip(y, 0, img1.shape[0] - 1)

        color = img1[y, x][::-1] / 255.0

        colors.append(color)

    colors = np.asarray(colors, dtype=np.float64)

    assert len(colors) == len(points_3d), (
        f"Cantidad de colores: {len(colors)}, "
        f"cantidad de puntos: {len(points_3d)}"
    )

    ###
    print("\n===== ESTADISTICAS 3D =====")

    print("Cantidad de puntos:", len(points_3d))

    print("X min/max:",
          points_3d[:, 0].min(),
          points_3d[:, 0].max())

    print("Y min/max:",
          points_3d[:, 1].min(),
          points_3d[:, 1].max())

    print("Z min/max:",
          points_3d[:, 2].min(),
          points_3d[:, 2].max())

    print("Centro de la nube:",
          points_3d.mean(axis=0))


    # ==========================================================
    # 8. GUARDAR NUBE DE PUNTOS
    # ==========================================================

    if len(points_3d) < 5:
        raise RuntimeError(
            "Muy pocos puntos 3D validos. Revisar imagenes y matching"
        )

    cloud = o3d.geometry.PointCloud()

    cloud.points = o3d.utility.Vector3dVector(
        points_3d
    )

    cloud.colors = o3d.utility.Vector3dVector(
        colors
    )

    o3d.io.write_point_cloud(
        f"{OUTPUT_DIR}/point_cloud.ply",
        cloud
    )

    print("\nNube guardada en output/point_cloud.ply")

    ###

    # ==========================================================
    # 9. CAMARA 3: PnP CONTRA EL MAPA 3D
    # ==========================================================

    img3 = cv2.imread(IMAGE3)

    if img3 is None:
        raise RuntimeError("No se pudo cargar IMAGE3")

    if img3.shape != img1.shape:
        raise RuntimeError("La imagen 3 debe tener la misma resolucion")

    img3 = cv2.undistort(img3, K, dist)
    gray3 = cv2.cvtColor(img3, cv2.COLOR_BGR2GRAY)

    kp3, des3 = sift.detectAndCompute(gray3, mask)

    if des3 is None:
        raise RuntimeError("No se detectaron descriptores en imagen 3")

    print("\nKEYPOINTS imagen 3:", len(kp3))

    # Matching imagen 1 (query) <-> imagen 3 (train)
    # Sin matching cruzado: solvePnPRansac ya descarta los outliers
    matches13 = matcher.knnMatch(des1, des3, k=2)

    # Diccionario: keypoint de img1 -> punto 3D
    map_3d = {
        int(k): p for k, p in zip(kp1_final, points_3d)
    }

    obj_pts = []   # puntos 3D
    img_pts = []   # pixeles en imagen 3

    for pair in matches13:
        if len(pair) < 2:
            continue

        m, n = pair

        if m.distance < RATIO_TEST * n.distance and m.queryIdx in map_3d:
            obj_pts.append(map_3d[m.queryIdx])
            img_pts.append(kp3[m.trainIdx].pt)

    obj_pts = np.asarray(obj_pts, dtype=np.float64)
    img_pts = np.asarray(img_pts, dtype=np.float64)

    print("Correspondencias 2D-3D para cámara 3:", len(obj_pts))

    if len(obj_pts) < 6:
        raise RuntimeError(
            "Muy pocas correspondencias 2D-3D para estimar la cámara 3"
        )

    # PnP con RANSAC
    ok, rvec3, tvec3, inliers3 = cv2.solvePnPRansac(
        obj_pts,
        img_pts,
        K,
        None,                              # imagen ya corregida
        iterationsCount=PNP_ITERATIONS,
        reprojectionError=PNP_REPROJECTION_THRESHOLD,
        confidence=PNP_CONFIDENCE,
        flags=cv2.SOLVEPNP_EPNP
    )

    if not ok or inliers3 is None or len(inliers3) < 6:
        raise RuntimeError("PnP no encontro una pose valida para la cámara 3")

    inliers3 = inliers3.ravel()

    print("Inliers PnP:", len(inliers3), "de", len(obj_pts))

    # Refinamiento no lineal solo con inliers
    rvec3, tvec3 = cv2.solvePnPRefineLM(
        obj_pts[inliers3],
        img_pts[inliers3],
        K,
        None,
        rvec3,
        tvec3
    )

    # Pose: mundo -> cámara 3
    R3_w2c, _ = cv2.Rodrigues(rvec3)

    # Pose: cámara 3 -> mundo (convención usada en el resto del código)
    R3_c2w = R3_w2c.T
    C3 = (-R3_c2w @ tvec3).ravel()

    print("\nPOSE CAMARA 3")
    print("Rotacion (cam3 -> mundo):")
    print(R3_c2w)
    print("Centro camara 3:", C3)

    # Error de reproyeccion de la cámara 3
    proj3, _ = cv2.projectPoints(
        obj_pts[inliers3], rvec3, tvec3, K, None
    )
    err3 = np.linalg.norm(
        proj3.reshape(-1, 2) - img_pts[inliers3], axis=1
    )
    print("Error reproyeccion cámara 3 - medio:", err3.mean())
    print("Error reproyeccion cámara 3 - maximo:", err3.max())

    # ==========================================================
    # EXPORTAR COORDENADAS 3D
    # ==========================================================

    np.savetxt(
        f"{OUTPUT_DIR}/points_3d.csv",
        points_3d,
        delimiter=",",
        header="X,Y,Z",
        comments=""
    )

    print("Coordenadas exportadas a points_3d.csv")


    # ==========================================================
    # VISUALIZACION DE NUBE Y CAMARAS
    # ==========================================================

    # Primera camara
    cam1 = o3d.geometry.TriangleMesh.create_coordinate_frame(
        size=0.4,
        origin=[0, 0, 0]
    )

    # Segunda camara
    R_cam2 = R.T
    C_cam2 = -R.T @ t

    # Poses de las camaras (camara -> mundo) para la interfaz
    np.savez(
        f"{OUTPUT_DIR}/cameras.npz",
        K=K,
        image_size=(img1.shape[1], img1.shape[0]),
        R2=R_cam2,
        C2=C_cam2.ravel(),
        R3=R3_c2w,
        C3=C3
    )

    ##

    # Ventana de Open3D (se omite con --no-gui; la interfaz dibuja la nube)
    if show:
        # ==========================================================
        # FRUSTUMS DE LAS DOS CAMARAS
        # ==========================================================

        # image_size = (1280, 720)
        image_size = (img1.shape[1], img1.shape[0])


        # Primera camara: identidad y origen
        frustum1 = create_camera_frustum(
            K,
            image_size,
            np.eye(3),
            np.zeros(3),
            scale=0.7,
            color=(0.0, 0.7, 1.0)
        )

        # Segunda camara: pose recuperada
        frustum2 = create_camera_frustum(
            K,
            image_size,
            R_cam2,
            C_cam2.ravel(),
            scale=0.7,
            color=(1.0, 0.3, 0.1)
        )

        ##

        T_cam2 = np.eye(4)
        T_cam2[:3, :3] = R_cam2
        T_cam2[:3, 3] = C_cam2.ravel()

        cam2 = o3d.geometry.TriangleMesh.create_coordinate_frame(
            size=0.4
        )

        cam2.transform(T_cam2)

        # ==========================================================
        # CAMARA 3: FRUSTUM, EJES Y MARCADOR
        # ==========================================================

        # Frustum de la cámara 3 (verde)
        frustum3 = create_camera_frustum(
            K,
            image_size,
            R3_c2w,
            C3,
            scale=0.7,
            color=(0.2, 1.0, 0.2)
        )

        # Sistema de coordenadas de la cámara 3
        T_cam3 = np.eye(4)
        T_cam3[:3, :3] = R3_c2w
        T_cam3[:3, 3] = C3

        cam3 = o3d.geometry.TriangleMesh.create_coordinate_frame(size=0.4)
        cam3.transform(T_cam3)

        # Esfera marcadora en el centro óptico de la cámara 3
        marker3 = o3d.geometry.TriangleMesh.create_sphere(radius=0.05)
        marker3.paint_uniform_color([0.2, 1.0, 0.2])
        marker3.translate(C3)

        # Esferas marcadoras de cámaras 1 y 2 (opcional, para distinguirlas)
        marker1 = o3d.geometry.TriangleMesh.create_sphere(radius=0.05)
        marker1.paint_uniform_color([0.0, 0.7, 1.0])

        marker2 = o3d.geometry.TriangleMesh.create_sphere(radius=0.05)
        marker2.paint_uniform_color([1.0, 0.3, 0.1])
        marker2.translate(C_cam2.ravel())

        # Trayectoria entre los tres centros de cámara
        centers = np.array([
            [0.0, 0.0, 0.0],
            C_cam2.ravel(),
            C3
        ])

        cam_path = o3d.geometry.LineSet(
            points=o3d.utility.Vector3dVector(centers),
            lines=o3d.utility.Vector2iVector([[0, 1], [1, 2]])
        )
        cam_path.colors = o3d.utility.Vector3dVector(
            np.array([[1, 1, 0], [1, 1, 0]], dtype=np.float64)
        )


        # Crear ventana
        vis = o3d.visualization.Visualizer()

        vis.create_window(
            window_name="SfM - Two View Reconstruction",
            width=1280,
            height=800
        )

        # Agregar geometria
        vis.add_geometry(cloud)

        # Sistemas de coordenadas
        vis.add_geometry(cam1)
        vis.add_geometry(cam2)

        # Frustums
        vis.add_geometry(frustum1)
        vis.add_geometry(frustum2)

        vis.add_geometry(cam3)
        vis.add_geometry(frustum3)
        vis.add_geometry(marker1)
        vis.add_geometry(marker2)
        vis.add_geometry(marker3)
        vis.add_geometry(cam_path)


        # Inicializar ventana y renderizador
        vis.poll_events()
        vis.update_renderer()

        # Configurar visualizacion DESPUES de inicializar
        render_option = vis.get_render_option()
        render_option.point_size = 7.0

        view_control = vis.get_view_control()

        view_control.set_lookat(
            points_3d.mean(axis=0)
        )

        view_control.set_zoom(0.7)

        # Mostrar
        vis.run()
        vis.destroy_window()

    print("\n===== CAMARAS =====")
    print("Centro camara 1:", [0, 0, 0])
    print("Centro camara 2:", C_cam2.ravel())

    print("Centro camara 3:", C3)


if __name__ == "__main__":
    run(show="--no-gui" not in sys.argv)
