# Classifier builds

This directory is empty in the source repository and filled at build time.

`oats-scan` bundles a compiled classifier, and a wheel carries exactly one
build: the one for the platform it was built for. CI drops the right binaries
in here before building each wheel, which is why `pip install oats-scan`
downloads only your platform rather than every platform.

Working from a source checkout? Point `OATS_SCAN_BIN_DIR` at a directory
holding `pheo-action-gateway` and `oatsctl`, or install the published package.
