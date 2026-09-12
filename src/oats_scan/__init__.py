try:
    from importlib.metadata import PackageNotFoundError, version as _version

    try:
        __version__ = _version("oats-scan")
    except PackageNotFoundError:
        __version__ = "0.0.0+source"
except ImportError:
    __version__ = "0.0.0+source"
