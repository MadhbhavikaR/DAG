# Versioning and releases

The project and Calibre plugin version is `0.1.0`. Keep `pyproject.toml` and `src/__init__.py` synchronized when preparing future versions.

The builder produces `dist/annas-archieve-callibre-plugin-v<VERSION>.zip`. GitHub Actions builds development artifacts on branch pushes and can publish a release for tags named `annas-archieve-callibre-plugin_<VERSION>` (for example, `annas-archieve-callibre-plugin_0.1.0`). The ZIP contains only the runtime files from `src/`, at archive root.

Do not commit generated ZIP files. Review the Actions run and confirm the release asset exists before announcing a successful release.
