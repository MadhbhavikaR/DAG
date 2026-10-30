"""Manager package metadata.

The installed distribution metadata is the single source of truth for the version.
"""

from importlib.metadata import PackageNotFoundError, version

try:
    __version__ = version("manager")
except PackageNotFoundError:
    # Source checkouts that have not been installed have no distribution metadata.
    __version__ = "0+unknown"
