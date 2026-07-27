import os
from io import StringIO
from pathlib import Path

import pandas as pd
import requests


MAP_KEY = os.environ["FIRMS_MAP_KEY"]

SOURCE = "VIIRS_NOAA20_NRT"
AREA = "world"
DAY_RANGE = 1

url = (
    "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
    f"{MAP_KEY}/{SOURCE}/{AREA}/{DAY_RANGE}"
)

response = requests.get(url, timeout=180)
response.raise_for_status()

fires = pd.read_csv(StringIO(response.text))

# Uhrzeit immer vierstellig formatieren:
# 35 wird beispielsweise zu 0035.
fires["acq_time"] = (
    fires["acq_time"]
    .astype(str)
    .str.replace(r"\.0$", "", regex=True)
    .str.zfill(4)
)

# Datum und Uhrzeit zu einem gemeinsamen UTC-Zeitpunkt verbinden.
fires["acq_datetime"] = pd.to_datetime(
    fires["acq_date"].astype(str) + " " + fires["acq_time"],
    format="%Y-%m-%d %H%M",
    errors="coerce",
    utc=True,
)

# Nur normale und hochwahrscheinliche Detektionen verwenden.
fires["confidence"] = fires["confidence"].astype(str).str.lower()

fires = fires[
    fires["confidence"].isin(["n", "h"])
    & fires["acq_datetime"].notna()
]

# Kleine beziehungsweise schwache Messungen ausblenden.
fires["frp"] = pd.to_numeric(fires["frp"], errors="coerce")
fires = fires[fires["frp"].fillna(0) >= 5]

# Verständliche Bezeichnungen für Flourish erzeugen.
fires["confidence_label"] = fires["confidence"].map(
    {
        "n": "Normal",
        "h": "Hoch",
    }
)

fires["daynight_label"] = fires["daynight"].map(
    {
        "D": "Tag",
        "N": "Nacht",
    }
)

fires["source"] = SOURCE

# Nur die für die Visualisierung benötigten Spalten behalten.
fires = fires[
    [
        "latitude",
        "longitude",
        "acq_datetime",
        "frp",
        "confidence_label",
        "satellite",
        "daynight_label",
        "source",
    ]
]

# Koordinaten vereinheitlichen und offensichtliche Dubletten entfernen.
fires["latitude"] = fires["latitude"].round(4)
fires["longitude"] = fires["longitude"].round(4)

fires = fires.drop_duplicates(
    subset=["latitude", "longitude", "acq_datetime"]
)

fires = fires.sort_values(
    "acq_datetime",
    ascending=False,
)

# ISO-Zeitformat für Flourish.
fires["acq_datetime"] = fires["acq_datetime"].dt.strftime(
    "%Y-%m-%dT%H:%M:%SZ"
)

output_directory = Path("data")
output_directory.mkdir(exist_ok=True)

fires.to_csv(
    output_directory / "fires.csv",
    index=False,
)

print(f"{len(fires)} Detektionen gespeichert.")
