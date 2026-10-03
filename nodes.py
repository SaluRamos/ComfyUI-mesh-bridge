import copy

import numpy as np
import torch
import trimesh as trimesh_lib
from PIL import Image
from comfy_api.latest import Types
from comfy_extras.nodes_mesh_io import Get3DComponents


def _array(tensor):
    return tensor.detach().cpu().numpy().copy()


def _tensor(array, dtype=torch.float32):
    return torch.from_numpy(np.array(array, copy=True)).to(dtype).unsqueeze(0)


def _image(tensor, index):
    if tensor is None:
        return None
    array = _array(tensor[index]).clip(0, 1)
    return Image.fromarray(np.rint(array * 255).astype(np.uint8))


def _texture(image):
    if image is None:
        return None
    return _tensor(np.asarray(image.convert("RGB"), dtype=np.float32) / 255)


class Model3DToMesh:
    CATEGORY = "3d/conversion"
    FUNCTION = "convert"
    RETURN_TYPES = ("MESH",)
    RETURN_NAMES = ("mesh",)
    DESCRIPTION = "Convert model_3d from Load 3D to native MESH using ComfyUI's reader. Supports GLB, GLTF, OBJ and STL; textures/material factors come from the first material."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"model_3d": ("FILE_3D_GLB,FILE_3D_GLTF,FILE_3D_OBJ,FILE_3D_STL,FILE_3D",)}}

    def convert(self, model_3d):
        return (Get3DComponents.execute(model_3d)[0],)


class MeshToTrimesh:
    CATEGORY = "3d/conversion"
    FUNCTION = "convert"
    RETURN_TYPES = ("TRIMESH",)
    RETURN_NAMES = ("trimesh",)
    DESCRIPTION = "Convert native ComfyUI MESH to TRIMESH, including UVs and PBR textures. Coordinates are unchanged."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"mesh": ("MESH",)}, "optional": {
            "batch_index": ("INT", {"default": 0, "min": 0, "max": 2147483647}),
        }}

    def convert(self, mesh, batch_index=0):
        if not isinstance(mesh, Types.MESH):
            raise TypeError("mesh_to_trimesh expects the native ComfyUI MESH object.")
        if not 0 <= batch_index < mesh.vertices.shape[0]:
            raise ValueError(f"batch_index must be between 0 and {mesh.vertices.shape[0] - 1}.")
        n = int(mesh.vertex_counts[batch_index]) if mesh.vertex_counts is not None else mesh.vertices.shape[1]
        f = int(mesh.face_counts[batch_index]) if mesh.face_counts is not None else mesh.faces.shape[1]
        result = trimesh_lib.Trimesh(
            vertices=_array(mesh.vertices[batch_index, :n]),
            faces=_array(mesh.faces[batch_index, :f]),
            vertex_normals=_array(mesh.normals[batch_index, :n]) if mesh.normals is not None else None,
            process=False,
        )
        overrides = mesh.material or {}
        if mesh.uvs is not None:
            uv = _array(mesh.uvs[batch_index, :n])
            uv[:, 1] = 1 - uv[:, 1]
            mr = _image(mesh.metallic_roughness, batch_index)
            material = trimesh_lib.visual.material.PBRMaterial(
                baseColorTexture=_image(mesh.texture, batch_index),
                metallicRoughnessTexture=mr,
                normalTexture=_image(mesh.normal_map, batch_index),
                emissiveTexture=_image(mesh.emissive, batch_index),
                occlusionTexture=mr if mesh.occlusion_in_mr else None,
                baseColorFactor=overrides.get("base_color_factor", [1., 1., 1., 1.]),
                metallicFactor=overrides.get("metallic_factor", 1. if mr is not None else 0.),
                roughnessFactor=overrides.get("roughness_factor", 1.),
                emissiveFactor=overrides.get("emissive_factor", [1., 1., 1.] if mesh.emissive is not None else [0., 0., 0.]),
                doubleSided=overrides.get("double_sided", False),
            )
            result.visual = trimesh_lib.visual.TextureVisuals(uv=uv, material=material)
        elif any(image is not None for image in (mesh.texture, mesh.metallic_roughness, mesh.normal_map, mesh.emissive)):
            raise ValueError("Textured MESH has no UVs. Connect a UV unwrap node first.")
        elif overrides:
            result.visual = trimesh_lib.visual.TextureVisuals(material=trimesh_lib.visual.material.PBRMaterial(
                baseColorFactor=overrides.get("base_color_factor", [1., 1., 1., 1.]),
                metallicFactor=overrides.get("metallic_factor", 0.),
                roughnessFactor=overrides.get("roughness_factor", 1.),
                emissiveFactor=overrides.get("emissive_factor", [0., 0., 0.]),
                doubleSided=overrides.get("double_sided", False),
            ))
        if mesh.vertex_colors is not None:
            colors = _array(mesh.vertex_colors[batch_index, :n])
            if result.visual.kind == "texture":
                result.vertex_attributes["mesh_bridge_colors"] = colors
            else:
                result.visual = trimesh_lib.visual.ColorVisuals(
                    mesh=result, vertex_colors=np.rint(colors.clip(0, 1) * 255).astype(np.uint8))
        if mesh.tangents is not None:
            result.vertex_attributes["mesh_bridge_tangents"] = _array(mesh.tangents[batch_index, :n])
        result.metadata["mesh_bridge"] = {
            "unlit": mesh.unlit,
            "material": copy.deepcopy(overrides),
        }
        return (result,)


class TrimeshToMesh:
    CATEGORY = "3d/conversion"
    FUNCTION = "convert"
    RETURN_TYPES = ("MESH",)
    RETURN_NAMES = ("mesh",)
    DESCRIPTION = "Convert TRIMESH to native MESH. Keep flip_v enabled for standard trimesh; disable it after TRELLIS.2 Rasterize PBR, which already uses image-space V. Output tensors are on CPU."

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"trimesh": ("TRIMESH",)}, "optional": {
            "flip_v": ("BOOLEAN", {"default": True,
                "tooltip": "True: standard trimesh UVs. False: TRELLIS.2 Rasterize PBR output UVs."}),
        }}

    def convert(self, trimesh, flip_v=True):
        if not isinstance(trimesh, trimesh_lib.Trimesh):
            raise TypeError("trimesh_to_mesh expects a trimesh.Trimesh, not a Scene or a list.")
        visual = trimesh.visual
        kwargs = {}
        bridge = trimesh.metadata.get("mesh_bridge", {})
        kwargs["unlit"] = bool(bridge.get("unlit", False))
        if visual.kind == "texture":
            if visual.face_materials is not None and len(np.unique(visual.face_materials)) > 1:
                raise ValueError("MESH supports one material. Split the mesh by material before converting.")
            material = visual.material
            if isinstance(material, trimesh_lib.visual.material.MultiMaterial):
                material_index = int(visual.face_materials[0]) if visual.face_materials is not None else 0
                material = material.get(material_index)
            if isinstance(material, trimesh_lib.visual.material.SimpleMaterial):
                material = material.to_pbr()
            if visual.uv is not None:
                uv = np.array(visual.uv, dtype=np.float32, copy=True)
                if flip_v:
                    uv[:, 1] = 1 - uv[:, 1]
                kwargs["uvs"] = _tensor(uv)
            kwargs.update(
                texture=_texture(material.baseColorTexture),
                metallic_roughness=_texture(material.metallicRoughnessTexture),
                normal_map=_texture(material.normalTexture),
                emissive=_texture(material.emissiveTexture),
            )
            overrides = {"metallic_factor": material.metallicFactor if material.metallicFactor is not None else 1.,
                         "roughness_factor": material.roughnessFactor if material.roughnessFactor is not None else 1.,
                         "double_sided": bool(material.doubleSided)}
            if material.baseColorFactor is not None:
                overrides["base_color_factor"] = (material.baseColorFactor.astype(np.float32) / 255).tolist()
            if material.emissiveFactor is not None:
                overrides["emissive_factor"] = material.emissiveFactor.tolist()
            for key in ("normal_scale", "occlusion_strength", "emissive_strength"):
                if key in bridge.get("material", {}):
                    overrides[key] = bridge["material"][key]
            kwargs["material"] = overrides
            if material.occlusionTexture is not None:
                ao = material.occlusionTexture.convert("RGB")
                mr = material.metallicRoughnessTexture
                if mr is None:
                    packed = np.full((ao.height, ao.width, 3), 255, dtype=np.uint8)
                else:
                    packed = np.array(mr.convert("RGB"), copy=True)
                    ao = ao.resize((packed.shape[1], packed.shape[0]))
                packed[:, :, 0] = np.asarray(ao)[:, :, 0]
                kwargs["metallic_roughness"] = _tensor(packed.astype(np.float32) / 255)
                kwargs["occlusion_in_mr"] = True
        elif visual.kind in ("vertex", "face"):
            if visual.kind == "face":
                raise ValueError("Per-face colors need separate vertices. Convert to per-vertex colors before converting.")
            kwargs["vertex_colors"] = _tensor(np.asarray(visual.vertex_colors, dtype=np.float32) / 255)
        for attribute, field in (("mesh_bridge_colors", "vertex_colors"), ("mesh_bridge_tangents", "tangents")):
            array = trimesh.vertex_attributes.get(attribute)
            if array is not None and len(array) == len(trimesh.vertices):
                kwargs[field] = _tensor(array)
        mesh = Types.MESH(
            vertices=_tensor(trimesh.vertices),
            faces=_tensor(trimesh.faces, torch.int64),
            normals=_tensor(trimesh.vertex_normals),
            **kwargs,
        )
        return (mesh,)

