# Color regression fixture

`srgb-reference.icc` is a fixed sRGB profile generated with LittleCMS through
Pillow by this project. It contains no copied printer/vendor profile.

SHA-256: `f3aff2ca301bf0b8371e53eb5fde8a0c49e6324a8b81a6f6a52ec065994c464d`

The project regression check pins this asset and tests independent D50 Lab
anchors for black, white and saturated primaries. The values include the
documented 8-bit Lab quantization tolerance. Keep the asset fixed when updating
Pillow/LittleCMS; review changes to color results explicitly. Pillow is pinned
to the tested version in both requirements files.
