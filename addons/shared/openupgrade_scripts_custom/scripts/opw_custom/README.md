# opw_custom migration (18.0 -> 19.0)

Post-migration hook: `scripts/opw_custom/19.0.8.2/post-migration.py` handles
missing-manifest cleanup during the OpenUpgrade pass.

Pre-migration rename for `product_connect` is handled in
`scripts/base/19.0.1.0/pre-migration.py`.
