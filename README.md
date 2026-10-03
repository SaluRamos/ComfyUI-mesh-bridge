# ComfyUI Mesh Bridge

<img width="1101" height="914" alt="image" src="https://github.com/user-attachments/assets/b561e784-b0a9-4761-8aab-3f51eecd8da3" />
<img width="954" height="329" alt="image" src="https://github.com/user-attachments/assets/3d02d1db-2e9f-412e-8140-1bd91a7ba970" />
<img width="1322" height="608" alt="image" src="https://github.com/user-attachments/assets/613df88a-65bb-4876-9101-090dd42c66fc" />

Três nós na categoria `3d/conversion`:

- `mesh_to_trimesh`: MESH nativo do ComfyUI → trimesh.Trimesh (`TRIMESH`).
- `trimesh_to_mesh`: trimesh.Trimesh (`TRIMESH`) → MESH nativo do ComfyUI.
- `model_3d_to_mesh`: `model_3d` (`FILE_3D`) → MESH nativo do ComfyUI.

Conecte `Load 3D (Advanced) → model_3d_to_mesh → Unwrap Mesh UVs`.
O novo nó usa o leitor nativo `Get 3D Components`, aceita GLB, GLTF, OBJ e STL,
aplica as transformações da cena e transporta UVs, cores, normais e mapas PBR.
Em arquivos com vários materiais, o leitor nativo mantém os mapas/fatores
do primeiro material. FBX e USDZ devem ser convertidos para GLB antes.

Exemplo: `Unwrap Mesh UVs → mesh_to_trimesh → TRELLIS.2 Encode Mesh`.
Conecte também o TRIMESH com UV ao `Rasterize PBR` para aplicar a textura gerada.

No `trimesh_to_mesh` conectado à saída de `TRELLIS.2 Rasterize PBR`, configure
`flip_v = false`: esse nó do TRELLIS já entrega UVs com V em coordenadas de imagem.
Para objetos trimesh convencionais, mantenha `flip_v = true` (padrão).
Usar true na saída do Rasterize PBR desloca as partes da textura pelo atlas.

Reinicie o ComfyUI após colocar esta pasta em `custom_nodes`.
As dependências já estão presentes na instalação usada para testar.

Os nós preservam vértices, faces e UVs, ajustando a inversão de V entre os dois
formatos. Não rotacionam, centralizam, normalizam nem fazem remesh.
Transportam normais, cores por vértice, mapas de base color, metallic/roughness,
normal, emissive, AO (empacotado em ORM) e fatores PBR.
Texturas e cores do formato trimesh usam precisão de 8 bits.

`batch_index` seleciona um item do lote MESH (padrão: 0); a saída MESH tem
um item e tensores em CPU. Não há arquivos intermediários nem chamadas de rede.

Limites: MESH suporta um material e um conjunto de UVs. Scenes, múltiplos
materiais por face e cores por face são rejeitados com orientação no erro.
Imagens voltam como RGB, conforme os nós nativos de exportação do ComfyUI;
alpha de textura não é transportado. Tangentes, cores simultâneas à textura,
unlit e fatores extras são mantidos em atributos/metadados do objeto trimesh
para a conversão de retorno; outros nós podem descartar esses dados.
Os conversores não geram texturas nem coordenadas UV.
