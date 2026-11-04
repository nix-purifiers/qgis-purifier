import json
import sys
from pathlib import Path

result = json.loads(Path(sys.argv[1]).read_text())
if any(result["dependencies"].values()):
    raise ValueError("locked native plugin graph has unsatisfied dependencies")
