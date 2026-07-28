import os
from io import StringIO
from pathlib import Path

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry


MAP_KEY = os.environ["FIRMS_MAP_KEY"]

SOURCES = [
    "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_NRT",
    "VIIRS_NOAA21_NRT",
    "MODIS_NRT",
]

retry_strategy = Retry(
    total=6,
    connect=6,
    read=6,
    status=6,
    backoff_factor=10,
    status_forcelist=[429, 500, 502, 503, 504],
    allowed_methods=["GET"],
)

session = requests.Session()
session.mount(
    "https://",
    HTTPAdapter(max_retries=retry_strategy),
)

frames = []

for source in SOURCES:
    url = (
        "https://firms.modaps.eosdis.nasa.gov/api/area/csv/"
        f"{MAP_KEY}/{source}/world/1"
    )

    print(f"Lade {source} ...")

    try:
        response = session.get(
            url,
            timeout=(30, 180),
            headers={
                "User-Agent": "firms-flourish-map/1.0"
            },
        )
        response.raise_for_status()

    except requests.RequestException as error:
        print(f"{source}: Download fehlgeschlagen: {error}")
        continue

    if not response.text.strip():
        print(f"{source}: Leere Antwort, wird übersprungen.")
        continue

    try:
        frame = pd.read_csv(StringIO(response.text))
    except Exception as error:
        print(f"{source}: CSV konnte nicht gelesen werden: {error}")
        print(response.text[:500])
        continue

    required_columns = {
        "latitude",
        "longitude",
        "acq_date",
        "acq_time",
    }

    if not required_columns.issubset(frame.columns):
        print(f"{source}: Unerwartete Antwort.")
        print(response.text[:500])
        continue

    frame["source"] = source
    frames.append(frame)

    print(f"{source}: {len(frame)} Zeilen geladen.")

if not frames:
    raise RuntimeError(
        "Keine FIRMS-Quelle war erreichbar. "
        "Die bestehende CSV bleibt unverändert."
    )

fires = pd.concat(
    frames,
    ignore_index=True,
)

fires["acq_time"] = (
    fires["acq_time"]
    .astype(str)
    .str.replace(r"\.0$", "", regex=True)
    .str.zfill(4)
)

fires["acq_datetime"] = pd.to_datetime(
    fires["acq_date"].astype(str)
    + " "
    + fires["acq_time"],
    format="%Y-%m-%d %H%M",
    errors="coerce",
    utc=True,
)

fires["frp"] = pd.to_numeric(
    fires.get("frp"),
    errors="coerce",
)

fires["weight"] = 1

fires = fires[
    fires["acq_datetime"].notna()
]

columns = [
    "latitude",
    "longitude",
    "acq_datetime",
    "frp",
    "satellite",
    "confidence",
    "daynight",
    "source",
    "weight",
]

existing_columns = [
    column
    for column in columns
    if column in fires.columns
]

fires = fires[existing_columns]

fires["latitude"] = pd.to_numeric(
    fires["latitude"],
    errors="coerce",
).round(4)

fires["longitude"] = pd.to_numeric(
    fires["longitude"],
    errors="coerce",
).round(4)

fires = fires.dropna(
    subset=["latitude", "longitude"]
)

fires = fires.drop_duplicates(
    subset=[
        "latitude",
        "longitude",
        "acq_datetime",
        "source",
    ]
)

fires["acq_datetime"] = (
    fires["acq_datetime"]
    .dt.strftime("%Y-%m-%dT%H:%M:%SZ")
)

fires = fires.sort_values(
    "acq_datetime",
    ascending=False,
)

output_directory = Path("data")
output_directory.mkdir(exist_ok=True)

temporary_file = output_directory / "fires.tmp.csv"
output_file = output_directory / "fires.csv"

fires.to_csv(
    temporary_file,
    index=False,
)

temporary_file.replace(output_file)

print(
    f"{len(fires)} Detektionen aus "
    f"{len(frames)} Quellen gespeichert."
)
