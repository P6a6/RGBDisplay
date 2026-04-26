import importlib.util
import sys
from pathlib import Path

from base_mode import BaseMode


class PluginManager:
    """
    Auto-discovers BaseMode subclasses by scanning every .py file
    inside modes/<category>/ subdirectories.

    Mode IDs follow the pattern  'category/module_stem',
    e.g. 'ambient/solid_color' or 'games/snake'.

    Dropping a new .py file in the folder and calling reload() (or
    restarting the server) is all that's needed to add a new mode.
    """

    def __init__(self, modes_dir: Path) -> None:
        self.modes_dir = Path(modes_dir)
        self.modes: dict[str, type[BaseMode]] = {}

    def discover(self) -> None:
        """Scan modes/ and load all BaseMode subclasses found."""
        self.modes.clear()
        for category_dir in sorted(self.modes_dir.iterdir()):
            if not category_dir.is_dir() or category_dir.name.startswith("_"):
                continue
            category = category_dir.name
            for py_file in sorted(category_dir.glob("*.py")):
                if py_file.name.startswith("_"):
                    continue
                try:
                    self._load_file(py_file, category)
                except Exception as exc:
                    print(f"[plugins] ERROR loading {py_file.name}: {exc}")
            for pkg_dir in sorted(category_dir.iterdir()):
                if not pkg_dir.is_dir() or pkg_dir.name.startswith("_"):
                    continue
                init_file = pkg_dir / "__init__.py"
                if not init_file.exists():
                    continue
                try:
                    self._load_file(init_file, category, stem=pkg_dir.name)
                except Exception as exc:
                    print(f"[plugins] ERROR loading package {pkg_dir.name}: {exc}")

    def _load_file(self, path: Path, category: str, stem: str = None) -> None:
        module_name = f"modes.{category}.{stem or path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            return
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)  # type: ignore[attr-defined]
        for attr_name in dir(module):
            attr = getattr(module, attr_name)
            if (
                isinstance(attr, type)
                and issubclass(attr, BaseMode)
                and attr is not BaseMode
            ):
                mode_id = f"{category}/{stem or path.stem}"
                self.modes[mode_id] = attr
                print(f"[plugins] loaded  {mode_id!r}  ({attr.metadata().get('name', '?')})")

    def reload(self) -> None:
        """Hot-reload: re-discover all plugins without restarting."""
        # Remove previously loaded mode modules so they're re-imported fresh
        stale = [k for k in sys.modules if k.startswith("modes.")]
        for k in stale:
            del sys.modules[k]
        self.discover()
