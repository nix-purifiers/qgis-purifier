import json
import sys
from pathlib import Path

request = json.loads(Path(sys.argv[1]).read_text())
request["destination"] = sys.argv[2]
Path(sys.argv[3]).write_text(json.dumps(request))
