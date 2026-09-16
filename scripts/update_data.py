"""Refresh the HomeNHealthy public-data release.

The updater is deliberately conservative: a failed or implausible source is
shown as unavailable and cannot silently become a zero, a placeholder, or a
negative finding about a city. The composite index is published only when all
slow-moving components pass the quality gate. Current AirNow AQI is displayed
separately and never changes the long-term ranking.
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
import argparse
import csv
import io
import json
import math
import os
import random
import re
import subprocess
import sys
import time

import requests


ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "data/healthy-home-index.json"
NOAA_DIR = "https://www.ncei.noaa.gov/data/normals-monthly/1991-2020/access/"
GHCN = "https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt"
AIRNOW = "https://files.airnowtech.org/airnow/today/reportingarea.dat"
ECHO = "https://echodata.epa.gov/echo/sdw_rest_services.get_systems"
ACS_YEAR = "2024"
METHODOLOGY_VERSION = "2.0"
ECHO_REQUEST_GAP_SECONDS = 2.0
ECHO_MAX_ATTEMPTS = 6

SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "HomeNHealthy.com public environmental data index; corrections@homenhealthy.com"})

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06", "CO": "08",
    "CT": "09", "DE": "10", "DC": "11", "FL": "12", "GA": "13", "HI": "15",
    "ID": "16", "IL": "17", "IN": "18", "IA": "19", "KS": "20", "KY": "21",
    "LA": "22", "ME": "23", "MD": "24", "MA": "25", "MI": "26", "MN": "27",
    "MS": "28", "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38", "OH": "39",
    "OK": "40", "OR": "41", "PA": "42", "RI": "44", "SC": "45", "SD": "46",
    "TN": "47", "TX": "48", "UT": "49", "VT": "50", "VA": "51", "WA": "53",
    "WV": "54", "WI": "55", "WY": "56",
}

SOURCE_URLS = {
    "air": "https://www.airnow.gov/",
    "water": "https://echo.epa.gov/trends/comparative-maps-dashboards/drinking-water-dashboard",
    "climate": "https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals",
    "housing": f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5/groups/B25034.html",
}


def clamp(value, low, high):
    return max(low, min(high, value))


def number(value):
    try:
        return float(str(value).strip())
    except (TypeError, ValueError):
        return None


def unavailable(source, reason):
    return {
        "status": "unavailable",
        "source": source,
        "source_url": SOURCE_URLS[source],
        "reason": reason,
    }


def distance_miles(lat1, lon1, lat2, lon2):
    radius = 3958.7613
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * radius * math.asin(math.sqrt(a))


def month_number(row):
    raw = str(row.get("DATE", "")).strip()
    if raw.isdigit() and 1 <= int(raw) <= 12:
        return int(raw)
    for key in ("month", "MONTH"):
        if str(row.get(key, "")).isdigit():
            return int(row[key])
    return None


def score_air(aqi):
    """Display-only score retained for comparison; AQI is not in the index."""
    if aqi is None:
        return None
    if aqi <= 20:
        return 100.0
    if aqi <= 50:
        return 100 - (aqi - 20) * 0.67
    if aqi <= 100:
        return 80 - (aqi - 50) * 0.6
    if aqi <= 150:
        return 50 - (aqi - 100) * 0.6
    if aqi <= 200:
        return 20 - (aqi - 150) * 0.4
    return 0.0


def climate_component(monthly):
    warm = [month for month in monthly if month.get("month") in (5, 6, 7, 8, 9)]
    if len(warm) != 5 or any(number(month.get("prcp_in")) is None for month in warm):
        raise ValueError("incomplete warm-season climate normals")
    annual_precip = sum(number(month.get("prcp_in")) or 0 for month in monthly)
    if annual_precip <= 1:
        raise ValueError("implausible annual precipitation total")
    temperature = sum(month["tavg_f"] for month in warm) / len(warm)
    precipitation = sum(month["prcp_in"] for month in warm)
    pressure = clamp(
        0.55 * clamp((temperature - 55) / 35 * 100, 0, 100)
        + 0.45 * clamp(precipitation / 25 * 100, 0, 100),
        0,
        100,
    )
    return {
        "status": "available",
        "moisture_pressure": round(pressure, 1),
        "score": round(100 - pressure, 1),
        "warm_avg_f": round(temperature, 1),
        "warm_precip_in": round(precipitation, 1),
        "annual_precip_in": round(annual_precip, 1),
        "source": "NOAA/NCEI 1991–2020 U.S. Climate Normals",
        "source_url": SOURCE_URLS["climate"],
        "period": "1991–2020",
        "method": "Nearest valid U.S. Climate Normals station within 150 miles",
        "limitations": "A climate pressure proxy; not a measurement or prediction of mold in a building.",
    }


def fetch_airnow():
    response = SESSION.get(AIRNOW, timeout=45)
    response.raise_for_status()
    rows = []
    for line in response.text.splitlines():
        parts = [part.strip().strip('"') for part in line.split("|")]
        # reportingarea.dat columns: issue date, valid date, valid time,
        # timezone, period, record type, primary flag, area, state, lat, lon,
        # parameter, AQI, category, ...
        if len(parts) < 14 or parts[5] != "O":
            continue
        try:
            lat, lon, aqi = float(parts[9]), float(parts[10]), int(float(parts[12]))
        except (TypeError, ValueError):
            continue
        if not 0 <= aqi <= 500 or not parts[8] or not parts[1] or not parts[2]:
            continue
        rows.append({
            "date": parts[1], "hour": parts[2], "tz": parts[3], "area": parts[7],
            "state": parts[8], "lat": lat, "lon": lon, "parameter": parts[11],
            "aqi": aqi, "category": parts[13],
        })
    if len(rows) < 100:
        raise RuntimeError(f"AirNow file parsed only {len(rows)} records")
    return rows


def nearest_air(city, rows):
    candidates = []
    for row in rows:
        if row["state"] != city["state"]:
            continue
        distance = distance_miles(city["lat"], city["lon"], row["lat"], row["lon"])
        if distance <= 160:
            candidates.append((distance, row))
    if not candidates:
        return unavailable("air", "No AirNow reporting area was found within 160 miles.")
    candidates.sort(key=lambda item: item[0])
    area = candidates[0][1]["area"]
    same_area = [row for _, row in candidates if row["area"] == area]
    row = max(same_area, key=lambda item: item["aqi"])
    return {
        "status": "available",
        "aqi": row["aqi"],
        "category": row["category"],
        "reporting_area": area,
        "parameter": row["parameter"],
        "distance_miles": round(candidates[0][0], 1),
        "display_score": round(score_air(row["aqi"]), 1),
        "observed_at": f'{row["date"]} {row["hour"]} {row["tz"]}'.strip(),
        "source": "EPA AirNow current reporting-area observation",
        "source_url": SOURCE_URLS["air"],
        "method": "Closest same-state AirNow reporting area; highest reported pollutant AQI",
        "limitations": "Preliminary outdoor conditions that can change quickly; not used in the long-term index.",
    }


def echo_retry_delay(response, attempt):
    """Return a bounded delay, preferring ECHO's Retry-After header."""
    retry_after = response.headers.get("Retry-After", "").strip()
    try:
        delay = float(retry_after)
    except (TypeError, ValueError):
        delay = 15.0 * (2 ** attempt)
    return min(max(delay, 1.0), 120.0) + random.uniform(0.25, 1.25)


def query_row_count(params):
    """Query ECHO with bounded retries for rate limits and transient errors."""
    for attempt in range(ECHO_MAX_ATTEMPTS):
        try:
            response = SESSION.get(ECHO, params={**params, "output": "JSON"}, timeout=45)
        except (requests.Timeout, requests.ConnectionError) as exc:
            if attempt == ECHO_MAX_ATTEMPTS - 1:
                raise
            delay = min(15.0 * (2 ** attempt), 120.0) + random.uniform(0.25, 1.25)
            print(f"ECHO request error: {exc}; retrying in {delay:.1f}s")
            time.sleep(delay)
            continue

        if response.status_code == 429 or 500 <= response.status_code < 600:
            if attempt == ECHO_MAX_ATTEMPTS - 1:
                response.raise_for_status()
            delay = echo_retry_delay(response, attempt)
            print(
                f"ECHO HTTP {response.status_code}; retrying in {delay:.1f}s "
                f"({attempt + 1}/{ECHO_MAX_ATTEMPTS - 1})"
            )
            time.sleep(delay)
            continue

        response.raise_for_status()
        return int(response.json()["Results"]["QueryRows"])

    raise RuntimeError("ECHO request exhausted all retry attempts")


def fetch_water_states(states):
    """Return state context using ECHO's documented current-violation filter."""
    results = {}
    for state in states:
        base = {"p_act": "Y", "p_st": state, "p_systyp": "CWS"}
        try:
            total = query_row_count(base)
            time.sleep(ECHO_REQUEST_GAP_SECONDS)
            # p_cs=H means systems with a current health-based violation.
            violations = query_row_count({**base, "p_cs": "H"})
            if total <= 0 or violations < 0 or violations > total:
                raise ValueError(f"impossible counts total={total}, health={violations}")
            compliance = round(100 * (1 - violations / total), 1)
            results[state] = {
                "status": "available",
                "geography": "state",
                "active_cws": total,
                "health_violation_cws": violations,
                "without_current_health_violation_pct": compliance,
                "score": compliance,
                "source": "EPA ECHO / SDWIS current health-based violation status",
                "source_url": SOURCE_URLS["water"],
                "retrieved_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                "method": "Active community water systems filtered with ECHO p_cs=H",
                "limitations": "State-level context; it does not identify the utility serving a specific address.",
            }
            print("ECHO", state, total, violations, compliance)
        except Exception as exc:
            print("ECHO unavailable", state, exc)
        time.sleep(ECHO_REQUEST_GAP_SECONDS)

    if results:
        equal = sum(1 for item in results.values() if item["active_cws"] == item["health_violation_cws"])
        if equal / len(results) > 0.10:
            raise RuntimeError(f"ECHO health filter failed plausibility gate ({equal}/{len(results)} equal counts)")
    return results


ACS_FIELDS = ["NAME", "B25035_001E"] + [f"B25034_{index:03d}E" for index in range(1, 12)]


def fetch_census_places(state, census_key):
    params = {
        "get": ",".join(ACS_FIELDS),
        "for": "place:*",
        "in": f"state:{STATE_FIPS[state]}",
        "key": census_key,
    }
    response = SESSION.get(f"https://api.census.gov/data/{ACS_YEAR}/acs/acs5", params=params, timeout=45)
    response.raise_for_status()
    rows = response.json()
    header = rows[0]
    return [dict(zip(header, row)) for row in rows[1:]]


def normalized_name(value):
    return re.sub(r"[^a-z0-9]", "", value.lower().replace("saint", "st"))


def match_housing(city, rows):
    target = normalized_name(city["city"])
    for row in rows:
        name = row["NAME"].split(",")[0]
        name = re.sub(r"\s+(city|town|village|municipality|borough|CDP)$", "", name, flags=re.I)
        if normalized_name(name) != target:
            continue
        median = number(row.get("B25035_001E"))
        total = number(row.get("B25034_001E"))
        if not median or not 1800 < median < 2030 or not total or total <= 0:
            return None
        pre_1980 = sum(number(row.get(f"B25034_{index:03d}E")) or 0 for index in range(7, 12))
        pre_1940 = number(row.get("B25034_011E")) or 0
        pre_1980_pct = round(100 * pre_1980 / total, 1)
        return {
            "status": "available",
            "median_year_built": int(median),
            "pre_1980_housing_pct": pre_1980_pct,
            "pre_1940_housing_pct": round(100 * pre_1940 / total, 1),
            "housing_units_in_age_table": int(total),
            "score": round(100 - pre_1980_pct, 1),
            "source": f"U.S. Census Bureau ACS {ACS_YEAR} 5-year, B25034 and B25035",
            "source_url": SOURCE_URLS["housing"],
            "period": f"ACS {ACS_YEAR} 5-year estimates",
            "method": "Place-level housing-age distribution and median year built",
            "limitations": "ACS publishes 1970–1979 as one bin, so HomeNHealthy reports pre-1980 rather than claiming an exact pre-1978 share.",
        }
    return None


def normal_station_ids():
    response = SESSION.get(NOAA_DIR, timeout=60)
    response.raise_for_status()
    ids = set(re.findall(r'href=["\']([A-Za-z0-9_]{11})\.csv', response.text))
    return {station_id for station_id in ids if station_id.startswith(("USW", "USC"))}


def fetch_stations(ids):
    response = SESSION.get(GHCN, timeout=90)
    response.raise_for_status()
    stations = []
    for line in response.text.splitlines():
        if len(line) < 71:
            continue
        station_id = line[:11].strip()
        if station_id not in ids:
            continue
        try:
            lat, lon = float(line[12:20]), float(line[21:30])
        except ValueError:
            continue
        stations.append({"id": station_id, "lat": lat, "lon": lon, "state": line[38:40].strip(), "name": line[41:71].strip()})
    return stations


_NORMAL_CACHE = {}


def fetch_station_normals(station):
    station_id = station["id"]
    if station_id in _NORMAL_CACHE:
        return _NORMAL_CACHE[station_id]
    try:
        response = SESSION.get(NOAA_DIR + station_id + ".csv", timeout=35)
        if response.status_code != 200:
            _NORMAL_CACHE[station_id] = None
            return None
        by_month = {}
        for row in csv.DictReader(io.StringIO(response.text)):
            month = month_number(row)
            if not month:
                continue
            values = by_month.setdefault(month, {})
            for source_key, output_key in (
                ("MLY-TAVG-NORMAL", "tavg_f"), ("MLY-TMIN-NORMAL", "tmin_f"),
                ("MLY-TMAX-NORMAL", "tmax_f"), ("MLY-PRCP-NORMAL", "prcp_in"),
            ):
                value = number(row.get(source_key))
                if value is not None:
                    values[output_key] = value
        months = []
        for month in range(1, 13):
            values = by_month.get(month, {})
            if "tavg_f" not in values and "tmin_f" in values and "tmax_f" in values:
                values["tavg_f"] = (values["tmin_f"] + values["tmax_f"]) / 2
            if not all(key in values for key in ("tavg_f", "tmin_f", "tmax_f", "prcp_in")):
                _NORMAL_CACHE[station_id] = None
                return None
            months.append({
                "month": month,
                "tmin_f": round(values["tmin_f"], 1), "tmax_f": round(values["tmax_f"], 1),
                "tavg_f": round(values["tavg_f"], 1), "prcp_in": round(values["prcp_in"], 2),
            })
        climate_component(months)
        result = {"monthly": months, "station": station_id, "station_name": station["name"]}
        _NORMAL_CACHE[station_id] = result
        return result
    except Exception:
        _NORMAL_CACHE[station_id] = None
        return None


def nearest_valid_normals(city, stations):
    candidates = []
    for station in stations:
        distance = distance_miles(city["lat"], city["lon"], station["lat"], station["lon"])
        if distance < 150:
            candidates.append((distance + (0 if station["state"] == city["state"] else 15), distance, station))
    candidates.sort(key=lambda item: item[0])
    for _, distance, station in candidates[:50]:
        normals = fetch_station_normals(station)
        if normals:
            return {**normals, "distance_miles": round(distance, 1)}
    return None


def compute_scores(cities):
    """Version 2 index: slow-moving public data only; no current AQI."""
    for city in cities:
        old_score = city.get("score") if isinstance(city.get("score"), (int, float)) else None
        components = [city.get("water", {}), city.get("climate", {}), city.get("housing", {})]
        if all(component.get("status") == "available" and isinstance(component.get("score"), (int, float)) for component in components):
            city["score"] = round(
                0.35 * city["water"]["score"] + 0.30 * city["climate"]["score"] + 0.35 * city["housing"]["score"], 1
            )
            city["previous_score"] = old_score
            city["change"] = round(city["score"] - old_score, 1) if old_score is not None else None
        else:
            city["score"] = None
            city["previous_score"] = old_score
            city["change"] = None
            city["rank"] = None
    ranked = sorted((city for city in cities if city["score"] is not None), key=lambda city: city["score"], reverse=True)
    for rank, city in enumerate(ranked, 1):
        city["rank"] = rank
    cities.sort(key=lambda city: (city.get("rank") is None, city.get("rank") or 9999, city["city"]))


def validate_dataset(obj, require_publishable=False):
    errors, warnings = [], []
    cities = obj.get("cities", [])
    if len(cities) < 75:
        errors.append(f"expected at least 75 cities, found {len(cities)}")
    slugs = [city.get("slug") for city in cities]
    if len(slugs) != len(set(slugs)):
        errors.append("duplicate city slugs")
    equal_water = 0
    for city in cities:
        label = city.get("slug", "unknown")
        for key in ("air", "water", "climate", "housing"):
            if city.get(key, {}).get("status") not in {"available", "unavailable", "stale"}:
                errors.append(f"{label}: {key} has no explicit availability status")
        air = city.get("air", {})
        if air.get("status") == "available" and not 0 <= air.get("aqi", -1) <= 500:
            errors.append(f"{label}: invalid AQI")
        water = city.get("water", {})
        if water.get("status") == "available":
            total, violations = water.get("active_cws", -1), water.get("health_violation_cws", -1)
            if total <= 0 or not 0 <= violations <= total:
                errors.append(f"{label}: impossible water counts")
            equal_water += int(total == violations)
        climate = city.get("climate", {})
        if climate.get("status") == "available":
            monthly = city.get("monthly", [])
            if len(monthly) != 12 or sum(number(month.get("prcp_in")) or 0 for month in monthly) <= 1:
                errors.append(f"{label}: missing or implausible precipitation normals")
        housing = city.get("housing", {})
        if housing.get("status") == "available":
            pct = housing.get("pre_1980_housing_pct")
            if pct is None or not 0 <= pct <= 100:
                errors.append(f"{label}: housing record lacks a valid pre-1980 share")
        if city.get("score") is not None and any(component.get("status") != "available" for component in (water, climate, housing)):
            errors.append(f"{label}: published score contains an unavailable component")
    available_water = sum(city.get("water", {}).get("status") == "available" for city in cities)
    if available_water and equal_water / available_water > 0.10:
        errors.append("water filter plausibility failure: too many violation counts equal total systems")
    if require_publishable or obj.get("meta", {}).get("index_status") == "published":
        coverage = {key: sum(city.get(key, {}).get("status") == "available" for city in cities) for key in ("air", "water", "climate", "housing")}
        for key, minimum in {"air": 60, "water": 70, "climate": 70, "housing": 70}.items():
            if coverage[key] < minimum:
                errors.append(f"{key} coverage {coverage[key]} is below publication threshold {minimum}")
        if sum(city.get("score") is not None for city in cities) < 70:
            errors.append("fewer than 70 cities have a complete index score")
    return errors, warnings


def sanitize_existing():
    """Remove known legacy placeholders and the broken water release."""
    obj = json.loads(DATA.read_text())
    for city in obj["cities"]:
        city["air"] = unavailable("air", "The legacy placeholder was removed; run the scheduled updater for a current observation.")
        city["water"] = unavailable("water", "The prior ECHO filter was invalid; this value is withheld pending a validated refresh.")
        if sum(number(month.get("prcp_in")) or 0 for month in city.get("monthly", [])) <= 1:
            city["climate"] = unavailable("climate", "The prior station record did not contain valid precipitation normals.")
            city["monthly"] = []
            city.pop("station", None)
        else:
            city["climate"] = {**city["climate"], "status": "available", "source_url": SOURCE_URLS["climate"]}
        city["housing"] = unavailable("housing", "Refresh required to add the auditable ACS housing-age distribution.")
        city["score"] = None
        city["rank"] = None
        city["change"] = None
    now = datetime.now(timezone.utc)
    obj["meta"] = {
        "generated": now.date().isoformat(), "generated_at": now.isoformat(timespec="seconds"),
        "methodology_version": METHODOLOGY_VERSION, "index_status": "withheld",
        "status": "Legacy claims removed; validated refresh required",
        "notes": "Known placeholder and invalid ECHO values were removed rather than represented as observations.",
    }
    DATA.write_text(json.dumps(obj, indent=2) + "\n")
    subprocess.check_call([sys.executable, str(ROOT / "scripts/build_site.py")])


def refresh():
    census_key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not census_key:
        raise RuntimeError("CENSUS_API_KEY is not set. Add it under Settings > Secrets and variables > Actions.")
    obj = json.loads(DATA.read_text())
    cities = obj["cities"]
    states = sorted({city["state"] for city in cities})
    try:
        air_rows = fetch_airnow()
        print("AirNow records", len(air_rows))
    except Exception as exc:
        print("AirNow unavailable", exc)
        air_rows = []
    try:
        water = fetch_water_states(states)
    except Exception as exc:
        print("ECHO source-wide failure", exc)
        water = {}
    census = {}
    for state in states:
        try:
            census[state] = fetch_census_places(state, census_key)
            print("ACS", state, len(census[state]))
        except Exception as exc:
            print("ACS unavailable", state, exc)
    try:
        stations = fetch_stations(normal_station_ids())
        print("NOAA candidate stations", len(stations))
    except Exception as exc:
        stations = []
        print("NOAA unavailable", exc)

    for city in cities:
        city["air"] = nearest_air(city, air_rows) if air_rows else unavailable("air", "AirNow retrieval failed for this build.")
        city["water"] = deepcopy(water.get(city["state"], unavailable("water", "No validated ECHO state result was available.")))
        city["housing"] = match_housing(city, census.get(city["state"], [])) or unavailable("housing", "No exact Census place match was available.")
        normals = nearest_valid_normals(city, stations) if stations else None
        if normals:
            city["monthly"] = normals["monthly"]
            city["station"] = f'{normals["station"]} — {normals["station_name"]} ({normals["distance_miles"]} mi)'
            city["climate"] = climate_component(normals["monthly"])
            city["climate"]["station"] = city["station"]
        else:
            city["monthly"] = []
            city["climate"] = unavailable("climate", "No complete, plausible NOAA normals station was found within 150 miles.")

    compute_scores(cities)
    now = datetime.now(timezone.utc)
    coverage = {key: sum(city.get(key, {}).get("status") == "available" for city in cities) for key in ("air", "water", "climate", "housing")}
    obj["meta"] = {
        "generated": now.date().isoformat(), "generated_at": now.isoformat(timespec="seconds"),
        "methodology_version": METHODOLOGY_VERSION, "index_status": "published",
        "status": "Validated public-data release", "coverage": coverage,
        "sources": {"airnow": coverage["air"], "echo_cities": coverage["water"], "noaa_cities": coverage["climate"], "acs_cities": coverage["housing"]},
        "notes": "Current AQI is displayed separately and does not affect the long-term index.",
    }
    errors, warnings = validate_dataset(obj, require_publishable=True)
    for warning in warnings:
        print("WARNING", warning)
    if errors:
        raise RuntimeError("Data quality gate failed:\n- " + "\n- ".join(errors))
    DATA.write_text(json.dumps(obj, indent=2) + "\n")
    archive = ROOT / "data" / "archive" / obj["meta"]["generated"]
    archive.mkdir(parents=True, exist_ok=True)
    (archive / "healthy-home-index.json").write_text(json.dumps(obj, indent=2) + "\n")
    subprocess.check_call([sys.executable, str(ROOT / "scripts/build_site.py")])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--sanitize-existing", action="store_true", help="remove known legacy placeholder/invalid values")
    args = parser.parse_args()
    sanitize_existing() if args.sanitize_existing else refresh()


if __name__ == "__main__":
    main()
