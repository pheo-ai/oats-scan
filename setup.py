"""Build a platform-tagged wheel.

oats-scan ships a compiled classifier, so a wheel built here is only valid
for the platform it was built for. Without this, setuptools would tag it
`py3-none-any` and a Linux user would install macOS binaries and get a tool
that cannot start. One wheel per platform, each honestly labelled.
"""
import os
from pathlib import Path

from setuptools import Distribution, setup

try:
    from wheel.bdist_wheel import bdist_wheel
except ImportError:  # setuptools>=70 vendors it here
    from setuptools.command.bdist_wheel import bdist_wheel


class BinaryDistribution(Distribution):
    def has_ext_modules(self):
        return True


class PlatformWheel(bdist_wheel):
    def finalize_options(self):
        # Must be set before super().finalize_options(): that call computes
        # plat_name_supplied from whether plat_name is already non-None, so
        # setting it later leaves the flag False and the override is
        # silently discarded in favour of autodetection.
        if os.environ.get("OATS_SCAN_WHEEL_PLAT_NAME"):
            self.plat_name = os.environ["OATS_SCAN_WHEEL_PLAT_NAME"]
        super().finalize_options()
        self.root_is_pure = False

    def get_tag(self):
        if self.plat_name_supplied:
            # bdist_wheel's own get_tag() asserts the tag is one of
            # packaging.tags.sys_tags() for the running interpreter, which
            # rejects manylinux tags and any cross-compiled target. Those
            # are supposed to differ from the build host.
            plat_name = (
                self.plat_name.lower()
                .replace("-", "_").replace(".", "_").replace(" ", "_")
            )
            return "py3", "none", plat_name
        _python, _abi, platform = super().get_tag()
        return "py3", "none", platform

    def run(self):
        binary_dir = Path(__file__).parent / "src" / "oats_scan" / "_bin"
        found = list(binary_dir.rglob("pheo-action-gateway*"))
        if not found:
            raise RuntimeError(
                "Refusing to build an oats-scan wheel without its classifier. "
                "No pheo-action-gateway binary under {}".format(binary_dir)
            )
        super().run()


setup(
    distclass=BinaryDistribution,
    cmdclass={"bdist_wheel": PlatformWheel},
)
