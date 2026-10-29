"""Tiny local PEP 517 backend; the project has no build-time dependencies."""
from pathlib import Path
import zipfile

WHEEL = "Wheel-Version: 1.0\nGenerator: manager-local\nRoot-Is-Purelib: true\nTag: py3-none-any\n"

def _dist(): return "manager-1.0.0rc0"

def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    name=_dist()+"-py3-none-any.whl"; out=Path(wheel_directory)/name
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        for p in Path("src").rglob("*.py"):
            z.write(p, p.as_posix())
        z.writestr(f"{_dist()}.dist-info/WHEEL",WHEEL)
        z.writestr(f"{_dist()}.dist-info/METADATA","Metadata-Version: 2.1\nName: manager\nVersion: 1.0.0-rc\n")
        z.writestr(f"{_dist()}.dist-info/entry_points.txt","[console_scripts]\nmanager = manager.cli:main\n")
        z.writestr(f"{_dist()}.dist-info/RECORD","")
    return name

def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    d=Path(metadata_directory)/f"{_dist()}.dist-info"; d.mkdir(); (d/"METADATA").write_text("Metadata-Version: 2.1\nName: manager\nVersion: 1.0.0-rc\n"); (d/"WHEEL").write_text(WHEEL); return d.name

def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    name=_dist()+"-py3-none-any.whl"; out=Path(wheel_directory)/name
    with zipfile.ZipFile(out,"w",zipfile.ZIP_DEFLATED) as z:
        z.writestr("manager.pth", str(Path("src").resolve()) + "\n")
        z.writestr(f"{_dist()}.dist-info/WHEEL",WHEEL)
        z.writestr(f"{_dist()}.dist-info/METADATA","Metadata-Version: 2.1\nName: manager\nVersion: 1.0.0-rc\n")
        z.writestr(f"{_dist()}.dist-info/entry_points.txt","[console_scripts]\nmanager = manager.cli:main\n")
        z.writestr(f"{_dist()}.dist-info/RECORD","")
    return name
