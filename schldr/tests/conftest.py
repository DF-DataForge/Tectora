"""The measuring library is plain Python: load it without the Odoo addon
around it (whose __init__ imports odoo)."""
import importlib.util
import sys
from pathlib import Path

LIB = Path(__file__).resolve().parent.parent / "schldr_paint" / "lib"

if "schldr_lib" not in sys.modules:
    spec = importlib.util.spec_from_file_location(
        "schldr_lib", LIB / "__init__.py", submodule_search_locations=[str(LIB)]
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules["schldr_lib"] = module
    spec.loader.exec_module(module)
