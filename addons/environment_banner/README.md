# Environment Banner

This addon shows a banner in the backend when the instance is not recognized as
production.

## Configuration

Set these configuration parameters to control behavior:

- `environment_banner.enabled` (default True)
- `environment_banner.production_hostnames` (comma or whitespace-separated hostnames;
  `*` wildcards allowed)

If no production hostnames are configured, the banner only shows for hosts that
look like dev/testing/localhost or include `.local`/`-local` labels.
