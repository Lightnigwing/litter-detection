"""Load the Go1 MuJoCo model with Go2 visuals and scene injection."""

from __future__ import annotations

import xml.etree.ElementTree as ET
from pathlib import Path

import mujoco
import numpy as np
from loguru import logger
from robot_descriptions import go1_mj_description, go2_mj_description

from sim.sim_settings import SimConfig

_MENAGERIE_GO1_PATH = Path(go1_mj_description.PACKAGE_PATH)
_MENAGERIE_GO2_PATH = Path(go2_mj_description.PACKAGE_PATH)

# Mapping from Go1 body names to Go2 body names for visual lookup.
_GO1_TO_GO2_BODY = {"trunk": "base"}

# Go2 material definitions: name → rgba.
_GO2_MATERIALS: dict[str, str] = {
    "metal": "0.9 0.95 0.95 1",
    "black": "0 0 0 1",
    "white": "1 1 1 1",
    "gray": "0.671705 0.692426 0.774270 1",
}

# Go2 mesh file names (OBJ format, in assets/ directory).
_GO2_MESHES = [
    "base_0",
    "base_1",
    "base_2",
    "base_3",
    "base_4",
    "hip_0",
    "hip_1",
    "thigh_0",
    "thigh_1",
    "thigh_mirror_0",
    "thigh_mirror_1",
    "calf_0",
    "calf_1",
    "calf_mirror_0",
    "calf_mirror_1",
    "foot",
]

# Go2 visual geom definitions per body, extracted from the Go2 menagerie MJCF.
# Keys are Go2 body names. Each geom dict has mesh, material, and optional pos/quat.
_GO2_VISUALS: dict[str, list[dict[str, str]]] = {
    "base": [
        {"mesh": "base_0", "material": "black"},
        {"mesh": "base_1", "material": "black"},
        {"mesh": "base_2", "material": "black"},
        {"mesh": "base_3", "material": "white"},
        {"mesh": "base_4", "material": "gray"},
    ],
    "FL_hip": [
        {"mesh": "hip_0", "material": "metal"},
        {"mesh": "hip_1", "material": "gray"},
    ],
    "FL_thigh": [
        {"mesh": "thigh_0", "material": "metal"},
        {"mesh": "thigh_1", "material": "gray"},
    ],
    "FL_calf": [
        {"mesh": "calf_0", "material": "gray"},
        {"mesh": "calf_1", "material": "black"},
        {"mesh": "foot", "material": "black", "pos": "0 0 -0.213"},
    ],
    "FR_hip": [
        {"mesh": "hip_0", "material": "metal", "quat": "4.63268e-05 1 0 0"},
        {"mesh": "hip_1", "material": "gray", "quat": "4.63268e-05 1 0 0"},
    ],
    "FR_thigh": [
        {"mesh": "thigh_mirror_0", "material": "metal"},
        {"mesh": "thigh_mirror_1", "material": "gray"},
    ],
    "FR_calf": [
        {"mesh": "calf_mirror_0", "material": "gray"},
        {"mesh": "calf_mirror_1", "material": "black"},
        {"mesh": "foot", "material": "black", "pos": "0 0 -0.213"},
    ],
    "RL_hip": [
        {"mesh": "hip_0", "material": "metal", "quat": "4.63268e-05 0 1 0"},
        {"mesh": "hip_1", "material": "gray", "quat": "4.63268e-05 0 1 0"},
    ],
    "RL_thigh": [
        {"mesh": "thigh_0", "material": "metal"},
        {"mesh": "thigh_1", "material": "gray"},
    ],
    "RL_calf": [
        {"mesh": "calf_0", "material": "gray"},
        {"mesh": "calf_1", "material": "black"},
        {"mesh": "foot", "material": "black", "pos": "0 0 -0.213"},
    ],
    "RR_hip": [
        {
            "mesh": "hip_0",
            "material": "metal",
            "quat": "2.14617e-09 4.63268e-05 4.63268e-05 -1",
        },
        {
            "mesh": "hip_1",
            "material": "gray",
            "quat": "2.14617e-09 4.63268e-05 4.63268e-05 -1",
        },
    ],
    "RR_thigh": [
        {"mesh": "thigh_mirror_0", "material": "metal"},
        {"mesh": "thigh_mirror_1", "material": "gray"},
    ],
    "RR_calf": [
        {"mesh": "calf_mirror_0", "material": "gray"},
        {"mesh": "calf_mirror_1", "material": "black"},
        {"mesh": "foot", "material": "black", "pos": "0 0 -0.213"},
    ],
}


def load_model(config: SimConfig) -> tuple[mujoco.MjModel, mujoco.MjData, np.ndarray]:
    """Load MuJoCo model and return (model, data, default_joint_angles)."""
    data_dir = Path(config.data_dir)

    xml_string, assets = _build_empty_scene(data_dir)

    model = mujoco.MjModel.from_xml_string(xml_string, assets=assets)
    data = mujoco.MjData(model)

    model.opt.timestep = config.sim_dt

    # Reset to home keyframe (standing pose).
    mujoco.mj_resetDataKeyframe(model, data, 0)

    # Override start position.
    data.qpos[0] = config.start_position[0]
    data.qpos[1] = config.start_position[1]
    data.qpos[2] = config.start_height
    mujoco.mj_forward(model, data)

    default_angles = model.keyframe("home").qpos[7:].astype(np.float32)

    _verify_model(model)

    logger.info(
        "Loaded MuJoCo model (nq={}, nv={}, nu={})",
        model.nq,
        model.nv,
        model.nu,
    )

    return model, data, default_angles


def _load_go2_visual_assets() -> dict[str, bytes]:
    """Load Go2 OBJ mesh files from the robot_descriptions Go2 menagerie package."""
    assets: dict[str, bytes] = {}
    assets_dir = _MENAGERIE_GO2_PATH / "assets"
    for name in _GO2_MESHES:
        obj_file = assets_dir / f"{name}.obj"
        if obj_file.is_file():
            assets[obj_file.name] = obj_file.read_bytes()
    return assets


def _swap_go1_visuals_for_go2(xml_string: str) -> str:
    """Replace Go1 visual meshes and geoms with Go2 equivalents in the robot XML.

    Preserves all Go1 physics (collision geoms, inertials, joints, actuators,
    sensors, keyframes) — only swaps the visual appearance.
    """
    root = ET.fromstring(xml_string)

    # --- Replace asset definitions ---
    asset = root.find("asset")
    if asset is None:
        return xml_string

    # Remove Go1 mesh definitions (STL files).
    for mesh_elem in list(asset.findall("mesh")):
        asset.remove(mesh_elem)

    # Remove Go1 "dark" material.
    for mat_elem in list(asset.findall("material")):
        if mat_elem.get("name") == "dark":
            asset.remove(mat_elem)

    # Add Go2 materials.
    for mat_name, rgba in _GO2_MATERIALS.items():
        ET.SubElement(asset, "material", name=mat_name, rgba=rgba)

    # Add Go2 mesh definitions (OBJ files).
    for mesh_name in _GO2_MESHES:
        ET.SubElement(asset, "mesh", name=mesh_name, file=f"{mesh_name}.obj")

    # --- Replace visual geoms in each body ---
    _replace_visual_geoms_recursive(root)

    return ET.tostring(root, encoding="unicode")


def _replace_visual_geoms_recursive(elem: ET.Element) -> None:
    """Walk the XML tree and replace visual geoms in bodies that have Go2 mappings."""
    for child in list(elem):
        if child.tag == "body":
            body_name = child.get("name", "")
            # Map Go1 body name to Go2 body name (trunk → base).
            go2_name = _GO1_TO_GO2_BODY.get(body_name, body_name)

            if go2_name in _GO2_VISUALS:
                # Remove existing Go1 visual geoms.
                for geom in list(child.findall("geom")):
                    if geom.get("class") == "visual":
                        child.remove(geom)

                # Add Go2 visual geoms.
                for geom_def in _GO2_VISUALS[go2_name]:
                    attribs: dict[str, str] = {
                        "type": "mesh",
                        "contype": "0",
                        "conaffinity": "0",
                        "group": "2",
                        "mesh": geom_def["mesh"],
                        "material": geom_def["material"],
                    }
                    if "pos" in geom_def:
                        attribs["pos"] = geom_def["pos"]
                    if "quat" in geom_def:
                        attribs["quat"] = geom_def["quat"]
                    child.insert(0, ET.Element("geom", attribs))

            # Recurse into child bodies.
            _replace_visual_geoms_recursive(child)
        else:
            _replace_visual_geoms_recursive(child)


def _include_robot_into_scene(scene_xml: str) -> str:
    """Insert ``<include file="unitree_go1.xml"/>`` into a scene XML.

    This is the same approach used by the reference implementation.
    MuJoCo's ``<include>`` mechanism correctly processes the robot's
    ``<default>`` / ``inheritrange`` / ``<option>`` blocks, which breaks
    when the robot XML is used as the outer document.
    """
    root = ET.fromstring(scene_xml)
    root.insert(0, ET.Element("include", file="unitree_go1.xml"))

    # Ensure visual/map element exists with znear and zfar.
    visual = root.find("visual")
    if visual is None:
        visual = ET.SubElement(root, "visual")
    map_elem = visual.find("map")
    if map_elem is None:
        map_elem = ET.SubElement(visual, "map")
    map_elem.set("znear", "0.01")
    map_elem.set("zfar", "10000")

    return ET.tostring(root, encoding="unicode")


def _build_robot_xml(data_dir: Path) -> bytes:
    """Read the Go1 robot XML, swap visuals for Go2, and return as bytes."""
    robot_xml = (data_dir / "unitree_go1.xml").read_text()
    swapped = _swap_go1_visuals_for_go2(robot_xml)
    return swapped.encode()


def _build_empty_scene(data_dir: Path) -> tuple[str, dict[str, bytes]]:
    """Include the Go1 robot (with Go2 visuals) into the empty scene XML."""
    scene_xml = (data_dir / "scene_empty.xml").read_text()
    combined = _include_robot_into_scene(scene_xml)

    assets = _load_go2_visual_assets()
    assets["unitree_go1.xml"] = _build_robot_xml(data_dir)
    return combined, assets


def _verify_model(model: mujoco.MjModel) -> None:
    """Verify required sensors and cameras exist."""
    required_sensors = ["gyro", "local_linvel"]
    for name in required_sensors:
        sid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_SENSOR, name)
        if sid == -1:
            msg = f"Required sensor '{name}' not found in model"
            raise RuntimeError(msg)

    required_cameras = [
        "head_camera",
        "lidar_front_camera",
        "lidar_left_camera",
        "lidar_right_camera",
    ]
    for name in required_cameras:
        cid = mujoco.mj_name2id(model, mujoco.mjtObj.mjOBJ_CAMERA, name)
        if cid == -1:
            msg = f"Required camera '{name}' not found in model"
            raise RuntimeError(msg)
