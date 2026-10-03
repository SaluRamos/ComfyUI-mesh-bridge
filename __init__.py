from .nodes import MeshToTrimesh, Model3DToMesh, TrimeshToMesh

NODE_CLASS_MAPPINGS = {
    "mesh_to_trimesh": MeshToTrimesh,
    "trimesh_to_mesh": TrimeshToMesh,
    "model_3d_to_mesh": Model3DToMesh,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "mesh_to_trimesh": "mesh_to_trimesh",
    "trimesh_to_mesh": "trimesh_to_mesh",
    "model_3d_to_mesh": "model_3d_to_mesh",
}
