import os
from pathlib import Path

import processing

output = Path(os.environ.get("QGIS_PURIFIER_OUTPUT", "output"))
output.mkdir(parents=True, exist_ok=True)
processing.run(
    "latlontools:field2geom",
    {
        "InputLayer": str(Path(__file__).with_name("coordinates.csv")),
        "Field1": "latitude",
        "Field2": "longitude",
        "InputField1Type": 0,
        "InputCRS": "EPSG:4326",
        "OutputLayer": str(output / "points.geojson"),
    },
)
