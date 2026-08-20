# HomeNHealthy.com

GitHub Pages-ready U.S. Healthy Home Index.

## Required repository secret

`CENSUS_API_KEY` — Census now requires an API key for ACS requests.

No NOAA or EPA API key is required in this build. Air data come from AirNow's nationwide reporting-area file product; drinking-water data come from EPA ECHO/SDWIS; climate normals come from NOAA/NCEI public station files.

## First deployment

1. Upload all files including `.github`.
2. Settings → Pages → Source: GitHub Actions.
3. Add `CENSUS_API_KEY` under Settings → Secrets and variables → Actions.
4. Run **Update Healthy Home Index and deploy** once.
5. Set custom domain to `homenhealthy.com`.

The updater runs every Monday and Thursday and deploys the rebuilt site in the same workflow.
