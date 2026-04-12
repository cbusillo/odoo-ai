# Image Enhancements

Provides opt-in image metadata for models that store `image_1920` images.

## Usage

- Add `image.metadata.mixin` to a model that needs image metadata.
- The mixin is currently applied to `product.image`.

## Fields

- `image_1920_file_size` (stored)
- `image_1920_width` (stored)
- `image_1920_height` (stored)
- `image_1920_file_size_kb` (computed)
- `image_1920_resolution` (computed)

## Behavior

- Metadata is computed from the image attachment bytes (DB or filestore).
- Invalid images are logged and leave metadata empty instead of raising errors.

## Migration

- 19.0.1.1 removes legacy metadata columns from unrelated tables.
