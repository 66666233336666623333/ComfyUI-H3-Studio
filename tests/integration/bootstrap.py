"""Load the extension against an existing ComfyUI checkout, on CPU only."""
import importlib.util
import os
from pathlib import Path
import sys

PACKAGE = Path(__file__).resolve().parents[2]
value = os.environ.get("COMFYUI_PATH")
if not value:
    raise RuntimeError("Set COMFYUI_PATH to a compatible ComfyUI checkout before integration tests.")
COMFY = Path(value).resolve()
sys.path.insert(0, str(COMFY))
sys.argv = [sys.argv[0], "--cpu"]
import comfy.options
comfy.options.enable_args_parsing()
spec = importlib.util.spec_from_file_location("h3_studio_test", PACKAGE / "__init__.py", submodule_search_locations=[str(PACKAGE)])
package = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = package
spec.loader.exec_module(package)
