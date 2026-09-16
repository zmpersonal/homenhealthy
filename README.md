# HomeNHealthy.com

GitHub Pages-ready U.S. home environmental public-data resource.

## What changed in methodology v2.0

- Placeholder AQI and housing values are prohibited in production.
- EPA ECHO uses the documented p_cs=H current health-based violation filter.
- Current AQI is displayed separately and no longer changes the long-term index.
- NOAA stations must contain 12 valid precipitation records and pass a plausibility check.
- Census ACS B25034 supplies auditable pre-1980 and pre-1940 housing shares.
- A city with a missing weighted field is not scored or ranked.
- The updater blocks publication when coverage or data invariants fail.
- Every validated release is preserved under data/archive/YYYY-MM-DD/.

## Required repository secret

CENSUS_API_KEY — used for ACS 2024 five-year place records.

AirNow, EPA ECHO and NOAA do not require secrets in this build.

## Deploy

1. Upload the changed files and folders to the repository root.
2. In Settings → Pages, use GitHub Actions as the source.
3. Add CENSUS_API_KEY under Settings → Secrets and variables → Actions.
4. Run Update Healthy Home Index and deploy once.
5. Confirm the workflow passes Verify publishable release.

The scheduled updater runs every Monday and Thursday. The checked-in release intentionally withholds the invalid legacy fields until the first validated refresh succeeds.

## Local checks

    pip install requests
    python -m py_compile scripts/update_data.py scripts/build_site.py scripts/validate_data.py
    python scripts/validate_data.py
    python scripts/build_site.py

To require a fully publishable release:

    python scripts/validate_data.py --require-publishable

## Before launch

Confirm that corrections@homenhealthy.com is monitored or replace it in scripts/build_site.py.
