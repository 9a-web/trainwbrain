# Heart 3D model for the Cardio section header

Place a **GLB file** (glTF Binary) of a human heart in this directory
to be loaded by [`Heart3D.js`](../../src/components/Heart3D.js).
The filename must be `realistic-heart.glb`.

## Recommended model

**Realistic Human Heart** by neshallads — CC BY 4.0

- Sketchfab: https://sketchfab.com/3d-models/realistic-human-heart-3f8072336ce94d18b3d0d055a1ece089
- Licence: Creative Commons Attribution (CC BY 4.0) — commercial use allowed with attribution

### How to download

1. Create a free account on [Sketchfab](https://sketchfab.com/signup)
2. Open the model page: https://sketchfab.com/3d-models/realistic-human-heart-3f8072336ce94d18b3d0d055a1ece089
3. Click the **"Download" button** (72k+ free downloads)
4. Download the **GLB** format file
5. Rename it to `realistic-heart.glb` and place it here

### What happens without the file

`Heart3D.js` generates a **procedural 3D heart** at runtime using
THREE.ExtrudeGeometry with a bezier contour. It looks decent but doesn't
have the detail of the Sketchfab model.

## Attribution

If you use the Sketchfab model, keep this credit visible in the app
(already shown in the cardio header credit link).

See [ATTRIBUTION.md](../ATTRIBUTION.md) for the full licence notice.