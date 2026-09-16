"""Generate the static HomeNHealthy site from the validated JSON release."""

from pathlib import Path
import csv
import html
import json


ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = ROOT / "data/healthy-home-index.json"
DATA = json.loads(DATA_PATH.read_text())
CITIES = DATA["cities"]
META = DATA["meta"]
GENERATED = META.get("generated", "unknown")
PUBLISHED = META.get("index_status") == "published"
SITE = "https://homenhealthy.com"


def esc(value):
    return html.escape(str(value), quote=True)


def write(relative, content):
    path = ROOT / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)


def json_ld(payload):
    return '<script type="application/ld+json">' + json.dumps(payload, separators=(",", ":")) + "</script>"


def breadcrumb_schema(items):
    return {
        "@context": "https://schema.org",
        "@type": "BreadcrumbList",
        "itemListElement": [
            {"@type": "ListItem", "position": index, "name": name, "item": SITE + url}
            for index, (name, url) in enumerate(items, 1)
        ],
    }


ORGANIZATION_SCHEMA = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "@id": SITE + "/#organization",
    "name": "HomeNHealthy",
    "url": SITE + "/",
    "logo": SITE + "/assets/favicon.svg",
    "description": "A public-data resource joining U.S. environmental and housing datasets into city profiles.",
}


def layout(title, description, canonical, body, breadcrumbs=None, extra_schema=None):
    schema = [ORGANIZATION_SCHEMA]
    if breadcrumbs:
        schema.append(breadcrumb_schema(breadcrumbs))
    if extra_schema:
        schema.extend(extra_schema if isinstance(extra_schema, list) else [extra_schema])
    return f'''<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{esc(title)}</title><meta name="description" content="{esc(description)}"><meta name="robots" content="index,follow,max-image-preview:large,max-snippet:-1">
<link rel="canonical" href="{SITE}{canonical}"><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml"><link rel="stylesheet" href="/assets/style.css">
{''.join(json_ld(item) for item in schema)}<script defer src="/assets/app.js"></script></head>
<body><a class="skip" href="#content">Skip to content</a><header class="top"><div class="wrap topbar"><a class="brand" href="/"><span>HNH</span><b>HomeNHealthy</b></a><nav class="nav" aria-label="Primary"><a href="/cities/">Cities</a><a href="/rankings/">Index</a><a href="/states/">States</a><a href="/sources/">Sources</a><a href="/methodology/">Methodology</a><a href="/data-download/">Data</a></nav></div></header>
<main id="content">{body}</main>{footer()}</body></html>'''


def footer():
    return '''<footer class="foot"><div class="wrap footergrid"><div><a class="brand footerbrand" href="/"><span>HNH</span><b>HomeNHealthy</b></a><p>Public-data context for the environments around U.S. homes. Not a home inspection, medical assessment, tap-water test or indoor-air measurement.</p></div><div><h2>Explore</h2><a href="/cities/">City profiles</a><a href="/rankings/">Index</a><a href="/states/">States</a><a href="/data-status/">Data status</a><a href="/home-wellness/">Home wellness</a></div><div><h2>Research standards</h2><a href="/methodology/">Methodology</a><a href="/sources/">Source catalog</a><a href="/data-dictionary/">Data dictionary</a><a href="/editorial-standards/">Editorial standards</a><a href="/corrections/">Corrections</a></div><div><h2>About</h2><a href="/about/">About HomeNHealthy</a><a href="/data-download/">Download data</a><a href="/license/">License & citation</a><p class="muted">Methodology v2.0 · Updated ''' + esc(GENERATED) + '''</p></div></div></footer>'''


def hero(kicker, heading, copy, extra=""):
    return f'''<section class="pagehero"><div class="wrap"><div class="eyebrow">{kicker}</div><h1>{heading}</h1><p class="lede">{copy}</p>{extra}</div></section>'''


def release_notice():
    if PUBLISHED:
        return f'''<div class="statusline good"><span>Validated release</span><b>Updated {esc(GENERATED)}</b><a href="/data-status/">See source status</a></div>'''
    return '''<div class="statusline warn"><span>Index withheld</span><b>Known legacy placeholders and invalid water claims were removed.</b><a href="/data-status/">Why values are unavailable</a></div>'''


def available(component):
    return component.get("status") == "available"


def display(value, suffix="", decimals=1):
    if value is None:
        return "Unavailable"
    if isinstance(value, float):
        value = f"{value:.{decimals}f}"
    return f"{value}{suffix}"


def status_badge(component):
    status = component.get("status", "unavailable")
    label = {"available": "Available", "stale": "Stale", "unavailable": "Unavailable"}.get(status, status.title())
    return f'<span class="badge {status}">{label}</span>'


def delta(city):
    change = city.get("change")
    if change is None or change == 0:
        return "—"
    return ("▲" if change > 0 else "▼") + f" {abs(change):.1f}"


def city_row(city, state_rank=None):
    rank = state_rank if state_rank is not None else city.get("rank")
    water, climate, housing, air = (city.get(key, {}) for key in ("water", "climate", "housing", "air"))
    return f'''<tr data-city-row><td>{'#' + str(rank) if rank else '—'}</td><td><a href="/cities/{city['slug']}/"><b>{esc(city['city'])}, {city['state']}</b></a></td><td>{display(city.get('score'))}</td><td>{display(air.get('aqi'))}</td><td>{display(water.get('without_current_health_violation_pct'), '%')}</td><td>{display(climate.get('moisture_pressure'))}</td><td>{display(housing.get('pre_1980_housing_pct'), '%')}</td></tr>'''


def city_lookup():
    return "".join(
        f'<a data-lookup-city="{esc((city["city"] + " " + city["state"] + " " + city["state_name"]).lower())}" href="/cities/{city["slug"]}/">{esc(city["city"])}</a>'
        for city in CITIES
    )


coverage = {key: sum(available(city.get(key, {})) for city in CITIES) for key in ("air", "water", "climate", "housing")}
ranked = [city for city in CITIES if city.get("rank")]


# Homepage
home_schema = {
    "@context": "https://schema.org", "@type": "WebSite", "@id": SITE + "/#website",
    "url": SITE + "/", "name": "HomeNHealthy", "publisher": {"@id": SITE + "/#organization"},
}
top_rows = "".join(city_row(city) for city in ranked[:8])
if not top_rows:
    top_rows = '<tr><td colspan="7"><b>No ranking is currently published.</b> City profiles remain available with verified fields and explicit unavailable states for withheld fields.</td></tr>'
home = release_notice() + f'''<section class="hero"><div class="wrap"><div class="eyebrow">U.S. home environmental intelligence</div><h1>What do public data say about the environment around your home?</h1><p>HomeNHealthy joins federal air, drinking-water, climate and housing datasets into clear city profiles. Every answer includes its geography, date, source and limitation.</p><form class="lookup" data-home-lookup><label class="sr-only" for="city-lookup">Search for a city</label><input id="city-lookup" placeholder="Search Austin, Denver or a state" autocomplete="off"><button class="btn">Find a profile</button></form><div class="lookup-data" aria-hidden="true">{city_lookup()}</div></div></section>
<section class="section"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">The joined database</div><h2>Facts first. The composite score second.</h2></div><p>Primary agencies publish excellent individual datasets. HomeNHealthy adds value by joining them into one dated, readable record for each city.</p></div><div class="metric-grid"><div class="metric"><small>City profiles</small><b>{len(CITIES)}</b><span>stable URLs</span></div><div class="metric"><small>Current air</small><b>{coverage['air']}/{len(CITIES)}</b><span>AirNow areas</span></div><div class="metric"><small>Climate normals</small><b>{coverage['climate']}/{len(CITIES)}</b><span>NOAA stations</span></div><div class="metric"><small>Housing profiles</small><b>{coverage['housing']}/{len(CITIES)}</b><span>Census places</span></div></div></div></section>
<section class="section tint"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Direct answers by place</div><h2>One profile, four different kinds of evidence.</h2></div><a class="textlink" href="/methodology/">Read methodology →</a></div><div class="cards four"><article class="card"><span class="icon">AIR</span><h3>What is the current outdoor AQI?</h3><p>A timestamped AirNow reporting-area observation, kept separate from long-term ranking because it can change within hours.</p><a href="/components/air-quality/">Understand AirNow data →</a></article><article class="card"><span class="icon">H₂O</span><h3>How many water systems report a current health-based violation?</h3><p>EPA ECHO state context, with the scope stated plainly. A city page never pretends that a state equals a local utility.</p><a href="/components/water/">Understand EPA water data →</a></article><article class="card"><span class="icon">CLM</span><h3>What are the local moisture conditions?</h3><p>NOAA climate normals provide warm-season temperature and precipitation context—not a claim that mold exists in a home.</p><a href="/components/moisture/">Understand the climate proxy →</a></article><article class="card"><span class="icon">AGE</span><h3>How old is the local housing stock?</h3><p>Census age bins show the share built before 1980 and before 1940, alongside the median construction year.</p><a href="/components/housing-age/">Understand housing-age data →</a></article></div></div></section>
<section class="section"><div class="wrap"><div class="sectionhead"><div><div class="eyebrow">Experimental index</div><h2>Current city ranking</h2></div><a class="btn secondary" href="/rankings/">See every city</a></div><p class="context">The v2 index uses only slow-moving, validated fields. Current AQI is intentionally excluded. If a required source fails its quality gate, affected scores are withheld rather than treated as zero.</p><div class="tablebox"><table><thead><tr><th>Rank</th><th>City</th><th>Score</th><th>AQI now</th><th>Water systems without current health violation</th><th>Moisture pressure</th><th>Housing pre-1980</th></tr></thead><tbody>{top_rows}</tbody></table></div></div></section>
<section class="section dark"><div class="wrap split"><div><div class="eyebrow">Built for reuse</div><h2>Download, audit and cite the underlying release.</h2><p>Use the CSV for analysis, the JSON for complete field-level provenance, or the copy-ready citation. The published schema explains exactly what each field means and does not mean.</p><a class="btn pale" href="/data-download/">Open the data center</a></div><div class="citationbox"><small>Suggested citation</small><blockquote>HomeNHealthy. “U.S. Home Environmental Profiles.” Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/</blockquote><button class="copy" data-copy-text='HomeNHealthy. "U.S. Home Environmental Profiles." Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/'>Copy citation</button></div></div></section>'''
write("index.html", layout("HomeNHealthy | U.S. Home Environmental Data by City", "Explore dated, sourced U.S. city profiles joining AirNow, EPA drinking-water, NOAA climate and Census housing data.", "/", home, extra_schema=home_schema))


# Cities hub and ranking
alphabetical = sorted(CITIES, key=lambda city: (city["state_name"], city["city"]))
cities_body = hero("75 stable location profiles", "U.S. city home-environment profiles", "Browse city-level public-data context for outdoor air, state drinking-water systems, climate moisture and housing age.") + f'''<section class="section"><div class="wrap"><div class="searchbar"><label for="city-filter">Filter city profiles</label><input id="city-filter" data-city-search placeholder="Type a city or state"></div><div class="citygrid">{''.join(f'<a data-city-row href="/cities/{c["slug"]}/"><b>{esc(c["city"])}, {c["state"]}</b><span>{esc(c["state_name"])} · Profile updated {esc(GENERATED)}</span></a>' for c in alphabetical)}</div></div></section>'''
write("cities/index.html", layout("U.S. City Home Environmental Profiles | HomeNHealthy", "Browse HomeNHealthy public-data profiles for 75 U.S. cities.", "/cities/", cities_body, [("Home", "/"), ("Cities", "/cities/")]))

ranking_rows = "".join(city_row(city) for city in (ranked or alphabetical))
ranking_body = release_notice() + hero("Methodology v2.0", "U.S. Home Environment Index", "An experimental comparison using validated slow-moving fields. Scores are secondary to the underlying component values.") + f'''<section class="section"><div class="wrap"><div class="callout"><h2>How to interpret this table</h2><p>Current AQI is displayed for immediate context but has zero weight in the index. Water is state-level context, climate is a station-based proxy and housing age is not proof of a hazard. <a href="/methodology/">See the exact formula and limitations.</a></p></div><div class="searchbar"><label for="ranking-filter">Filter rankings</label><input id="ranking-filter" data-city-search placeholder="Type a city or state"></div><div class="tablebox"><table><thead><tr><th>Rank</th><th>City</th><th>Score</th><th>AQI now</th><th>Water systems without current health violation</th><th>Moisture pressure</th><th>Housing pre-1980</th></tr></thead><tbody>{ranking_rows}</tbody></table></div></div></section>'''
write("rankings/index.html", layout("U.S. Home Environment Index Rankings | HomeNHealthy", "Compare 75 U.S. cities using sourced drinking-water, climate and housing context, with current AQI shown separately.", "/rankings/", ranking_body, [("Home", "/"), ("Index", "/rankings/")]))


# City profiles
for city in CITIES:
    air, water, climate, housing = (city.get(key, {}) for key in ("air", "water", "climate", "housing"))
    score_text = f'{city["score"]:.1f} / 100' if city.get("score") is not None else "Withheld"
    rank_text = f'#{city["rank"]} of {len(ranked)}' if city.get("rank") else "Not ranked"
    air_answer = (f'The current AirNow AQI for the {esc(air.get("reporting_area"))} reporting area is <b>{air.get("aqi")}</b> ({esc(air.get("category", "category unavailable"))}), observed {esc(air.get("observed_at", "time unavailable"))}.' if available(air) else f'No current AQI is published for this release. {esc(air.get("reason", "The source did not pass validation."))}')
    water_answer = (f'Across active community water systems in {esc(city["state_name"])}, <b>{water.get("without_current_health_violation_pct")}%</b> had no current health-based violation in the ECHO query: {water.get("health_violation_cws")} of {water.get("active_cws")} systems were returned with one.' if available(water) else f'Water-system context is withheld. {esc(water.get("reason", "The source did not pass validation."))}')
    climate_answer = (f'The selected NOAA normals station has a HomeNHealthy warm-season moisture-pressure value of <b>{climate.get("moisture_pressure")}</b> out of 100, based on a May–September mean of {climate.get("warm_avg_f")}°F and {climate.get("warm_precip_in")} inches of precipitation.' if available(climate) else f'Climate moisture context is unavailable. {esc(climate.get("reason", "The source did not pass validation."))}')
    housing_answer = (f'The ACS median year built is <b>{housing.get("median_year_built")}</b>. An estimated <b>{housing.get("pre_1980_housing_pct")}%</b> of units in the Census age table were built before 1980, and {housing.get("pre_1940_housing_pct")}% before 1940.' if available(housing) else f'Housing-age context is unavailable. {esc(housing.get("reason", "The source did not pass validation."))}')
    bars = "".join(f'<span style="height:{max(5, min(100, (m.get("prcp_in") or 0) * 14))}%" data-v="{m.get("prcp_in")} in"><i>{m.get("month")}</i></span>' for m in city.get("monthly", []))
    city_dataset = {
        "@context": "https://schema.org", "@type": "Dataset",
        "name": f'{city["city"]}, {city["state"]} Home Environmental Profile',
        "description": f'Joined public-data profile for {city["city"]}, {city["state"]}, with explicit source scope and availability.',
        "url": SITE + f'/cities/{city["slug"]}/', "dateModified": GENERATED,
        "creator": {"@id": SITE + "/#organization"}, "isAccessibleForFree": True,
        "license": "https://creativecommons.org/licenses/by/4.0/",
        "spatialCoverage": {"@type": "Place", "name": f'{city["city"]}, {city["state"]}', "geo": {"@type": "GeoCoordinates", "latitude": city["lat"], "longitude": city["lon"]}},
        "isPartOf": SITE + "/data-download/",
    }
    profile = release_notice() + hero(
        f'{city["state_name"]} city profile · Updated {esc(GENERATED)}',
        f'{esc(city["city"])}, {city["state"]} home environmental profile',
        f'What federal public datasets currently say about outdoor air, drinking-water systems, climate moisture and housing age around {esc(city["city"])}.',
        f'<div class="scoreline"><div><small>Experimental index</small><b>{score_text}</b></div><div><small>National position</small><b>{rank_text}</b></div><div><small>Release status</small>{"<b>Validated</b>" if PUBLISHED else "<b>Withheld</b>"}</div></div>',
    ) + f'''<section class="section"><div class="wrap"><div class="answer"><div class="eyebrow">Answer summary</div><p>As of <b>{esc(GENERATED)}</b>, HomeNHealthy reports the following for {esc(city['city'])}: {air_answer} {climate_answer} These are geographic indicators, not measurements inside a specific home.</p></div><div class="factgrid"><article><span>Current outdoor air</span>{status_badge(air)}<b>{display(air.get('aqi'))}</b><small>{esc(air.get('category', 'AQI unavailable'))}</small></article><article><span>Water context</span>{status_badge(water)}<b>{display(water.get('without_current_health_violation_pct'), '%')}</b><small>systems without current health-based violation</small></article><article><span>Moisture pressure</span>{status_badge(climate)}<b>{display(climate.get('moisture_pressure'))}</b><small>HomeNHealthy proxy, not mold risk</small></article><article><span>Housing built pre-1980</span>{status_badge(housing)}<b>{display(housing.get('pre_1980_housing_pct'), '%')}</b><small>Census place estimate</small></article></div></div></section>
<section class="section tint"><div class="wrap prose"><h2>Questions this profile can answer</h2><h3>What is the current outdoor air quality near {esc(city['city'])}?</h3><p>{air_answer}</p><p class="note">AirNow data are preliminary outdoor observations and can change quickly. They are not a measurement of indoor air and are not used in the long-term index.</p><h3>What do EPA records say about drinking-water systems?</h3><p>{water_answer}</p><p class="note">This is state-level regulatory context. It does not establish which utility serves an address, whether a violation affected a specific tap, or whether water is unsafe today.</p><h3>How strong is warm-season moisture pressure?</h3><p>{climate_answer}</p>{f'<div class="chartrow" aria-label="Monthly precipitation chart">{bars}</div><p class="note">Monthly precipitation normals, January through December. Station: {esc(city.get("station", "unavailable"))}.</p>' if bars else ''}<h3>How old is the housing stock?</h3><p>{housing_answer}</p><p class="note">The Census groups 1970–1979 together. HomeNHealthy therefore reports the observable pre-1980 share rather than estimating an exact pre-1978 lead-paint-era percentage.</p><h3>What should a homeowner verify at the property?</h3><p>Geographic data cannot determine conditions inside a building. Depending on the property, direct checks may include radon testing, carbon-monoxide alarms, indoor humidity, visible moisture, lead evaluation for older materials, and the serving water utility’s current Consumer Confidence Report.</p></div></section>
<section class="section"><div class="wrap split"><div><div class="eyebrow">Field-level provenance</div><h2>Where each answer comes from</h2><div class="sourcecards">{''.join(f'<article><div>{status_badge(component)}<b>{label}</b></div><p>{esc(component.get("source", key.title()))}</p><p>{esc(component.get("method", component.get("reason", "No method metadata is available.")))}</p><a href="{esc(component.get("source_url", "/sources/"))}">Open primary source ↗</a></article>' for key, label, component in (("air", "Outdoor air", air), ("water", "Drinking water", water), ("climate", "Climate", climate), ("housing", "Housing age", housing)))}</div></div><aside class="citationbox"><small>Cite this profile</small><blockquote>HomeNHealthy. “{esc(city['city'])}, {city['state']} Home Environmental Profile.” Updated {esc(GENERATED)}.</blockquote><button class="copy" data-copy-text='HomeNHealthy. "{esc(city['city'])}, {city['state']} Home Environmental Profile." Updated {esc(GENERATED)}. {SITE}/cities/{city['slug']}/'>Copy citation</button><a class="textlink" href="/data-download/">Download underlying data →</a></aside></div></section>'''
    write(f'cities/{city["slug"]}/index.html', layout(f'{city["city"]}, {city["state"]} Home Environmental Profile | HomeNHealthy', f'Sourced air, drinking-water, climate and housing-age context for {city["city"]}, {city["state"]}, updated {GENERATED}.', f'/cities/{city["slug"]}/', profile, [("Home", "/"), ("Cities", "/cities/"), (f'{city["city"]}, {city["state"]}', f'/cities/{city["slug"]}/')], city_dataset))


# States hub and state pages
states = {}
for city in CITIES:
    states.setdefault(city["state"], []).append(city)
state_cards = []
for code, items in sorted(states.items(), key=lambda pair: pair[1][0]["state_name"]):
    state_cards.append(f'<a href="/states/{code.lower()}/"><b>{esc(items[0]["state_name"])}</b><span>{len(items)} indexed cit{"y" if len(items) == 1 else "ies"}</span></a>')
states_body = hero("Geographic index", "Browse home-environment data by state", "State pages collect every indexed city and make the scope of state-level drinking-water context explicit.") + f'<section class="section"><div class="wrap"><div class="citygrid">{"".join(state_cards)}</div></div></section>'
write("states/index.html", layout("U.S. State Home Environmental Profiles | HomeNHealthy", "Browse HomeNHealthy city profiles by U.S. state.", "/states/", states_body, [("Home", "/"), ("States", "/states/")]))

for code, items in states.items():
    items = sorted(items, key=lambda city: (city.get("score") is None, -(city.get("score") or 0), city["city"]))
    name = items[0]["state_name"]
    state_rows = "".join(city_row(city, index if city.get("score") is not None else None) for index, city in enumerate(items, 1))
    page = release_notice() + hero("State collection", f'{esc(name)} home environmental profiles', f'Compare {len(items)} indexed cit{"y" if len(items) == 1 else "ies"} in {esc(name)} using the same public-data definitions and release date.') + f'''<section class="section"><div class="wrap"><div class="callout"><h2>About the water column</h2><p>The drinking-water percentage is state-level EPA ECHO context, so cities in the same state share that value. It is not a substitute for identifying the community water system that serves a specific address.</p></div><div class="tablebox"><table><thead><tr><th>State rank</th><th>City</th><th>Score</th><th>AQI now</th><th>Water systems without current health violation</th><th>Moisture pressure</th><th>Housing pre-1980</th></tr></thead><tbody>{state_rows}</tbody></table></div></div></section>'''
    write(f"states/{code.lower()}/index.html", layout(f"{name} Home Environmental Profiles | HomeNHealthy", f"Compare public-data home environmental profiles for indexed cities in {name}.", f"/states/{code.lower()}/", page, [("Home", "/"), ("States", "/states/"), (name, f"/states/{code.lower()}/")]))


# Source explainers
component_pages = {
    "air-quality": ("EPA AirNow outdoor AQI explained", "Current conditions, not a long-term ranking variable", '''<h2>What HomeNHealthy reports</h2><p>HomeNHealthy uses the closest same-state AirNow reporting area within 160 miles and shows the highest pollutant AQI reported for that area. The city profile includes the reporting-area name, distance, pollutant, category and observation time when available.</p><h2>What AQI means</h2><p>The Air Quality Index converts concentrations of common outdoor pollutants into a public communication scale. A higher number represents greater short-term health concern. AQI is an outdoor, area-level observation; it does not reveal the air inside a particular house.</p><h2>Why it is excluded from the index</h2><p>A smoke plume, dust event or weather shift can move AQI sharply within hours. That makes it useful for current decisions but unsuitable as a major input to a slow-moving residential-environment ranking. Methodology v2.0 displays AQI as a live tile and gives it zero index weight.</p><h2>Preliminary versus regulatory data</h2><p>AirNow describes its observations as preliminary. For regulatory and historical trend analysis, EPA’s Air Quality System or AirData should be used instead. HomeNHealthy never describes an AirNow snapshot as an annual exposure measure.</p><h2>Known limitations</h2><ul><li>A reporting area may be many miles from the city center.</li><li>Outdoor monitors do not measure filtration, ventilation or pollution sources indoors.</li><li>Conditions may be stale or unavailable when the source feed fails.</li><li>A citywide AQI cannot determine personal exposure.</li></ul><p><a href="https://www.airnow.gov/">Verify current conditions at AirNow ↗</a></p>'''),
    "water": ("EPA drinking-water violations explained", "What ECHO/SDWIS can—and cannot—say about a home", '''<h2>What counts as a health-based violation?</h2><p>EPA ECHO describes health-based violations as violations of maximum contaminant levels, maximum residual disinfectant levels or treatment-technique rules. Monitoring, reporting, public-notice and recordkeeping violations are important but are separate categories.</p><h2>How HomeNHealthy queries the data</h2><p>The updater requests active community water systems in each state, then applies ECHO’s documented <code>p_cs=H</code> current-violation filter. It reports the number and percentage of systems returned without a current health-based violation. Automated checks reject negative counts, violation counts greater than total systems and the previous failure pattern in which an ignored filter made the two counts identical across the country.</p><h2>Why the current figure is state-level</h2><p>Public-water service territories do not reliably match city boundaries or ZIP codes. Until HomeNHealthy can map utilities at the PWSID level, state context is labeled as state context. It should not be read as a claim about Austin Water, Denver Water or any other named local supplier.</p><h2>Does a violation mean tap water is unsafe today?</h2><p>Not necessarily. Violation records have different start dates, statuses and corrective actions, and federal reporting can lag. A household should identify its serving system, read its Consumer Confidence Report and check current local notices.</p><h2>What the number does not cover</h2><ul><li>Private wells.</li><li>Conditions in building plumbing.</li><li>A contaminant measurement at a specific tap.</li><li>Health standards that are not part of the regulatory query.</li></ul><p><a href="https://echo.epa.gov/trends/comparative-maps-dashboards/drinking-water-dashboard">Open EPA’s Drinking Water Dashboard ↗</a></p>'''),
    "moisture": ("NOAA climate moisture pressure explained", "A transparent climate proxy—not a mold model", '''<h2>What the proxy measures</h2><p>HomeNHealthy combines May–September mean temperature and precipitation from NOAA’s 1991–2020 U.S. Climate Normals. Warmth contributes 55% and precipitation 45% to a 0–100 moisture-pressure value. The inverse is used as one index component.</p><h2>Why use climate normals?</h2><p>Thirty-year normals describe a place’s typical climate more reliably than a single wet month or drought week. They help compare recurring warm-season conditions while avoiding a false claim that current weather changed the physical condition of every home in a city.</p><h2>The station-selection rule</h2><p>The updater checks nearby stations, prefers the same state, requires all 12 monthly temperature and precipitation records, and rejects stations with an implausible annual precipitation total. This prevents missing precipitation from silently appearing as twelve zeroes.</p><h2>What it cannot establish</h2><p>Mold and moisture damage depend on leaks, drainage, construction, ventilation, cooling, indoor humidity and maintenance. The proxy cannot diagnose any of those conditions. A dry-climate city can have a wet basement; a humid-climate home can be well controlled.</p><h2>How to use it</h2><p>Treat the value as background context for questions about dehumidification, drainage, building-envelope inspection and ventilation—not as a risk prediction for a property.</p><p><a href="https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals">Read NOAA’s U.S. Climate Normals documentation ↗</a></p>'''),
    "housing-age": ("Census housing-age data explained", "Why HomeNHealthy reports pre-1980—not a made-up pre-1978 estimate", '''<h2>What HomeNHealthy reports</h2><p>City profiles use Census American Community Survey tables B25034 and B25035 to show median year built, the share of housing units built before 1980 and the share built before 1940.</p><h2>Why pre-1980?</h2><p>The federal residential lead-paint ban makes 1978 an important threshold, but the ACS publishes 1970–1979 as a single decade bin. A precise pre-1978 percentage cannot be observed from that table. HomeNHealthy reports the defensible pre-1980 figure and explains why it is close to—but not identical to—the lead-paint threshold.</p><h2>Housing age is context, not condition</h2><p>An older home may be carefully renovated and maintained. A newer home may have moisture, ventilation or material problems. Age can help identify questions worth asking, but it does not prove the presence of lead, asbestos, radon, mold or any defect.</p><h2>About ACS estimates</h2><p>The ACS five-year dataset combines survey responses collected over a multi-year period. Values are estimates and have margins of error. HomeNHealthy uses exact Census place matches and withholds the field when a reliable match is unavailable.</p><h2>Property-level next steps</h2><p>Use the city statistic as a prompt to check the actual year of construction, renovation history and condition of the home. For potential lead hazards, follow EPA/HUD guidance and use qualified testing or risk-assessment professionals.</p><p><a href="https://api.census.gov/data/2024/acs/acs5/groups/B25034.html">Open Census table B25034 ↗</a></p>'''),
}
for slug, (title, subtitle, content) in component_pages.items():
    source_key = "air" if slug == "air-quality" else "water" if slug == "water" else "climate" if slug == "moisture" else "housing"
    body = hero("Data-source explainer", title, subtitle) + f'''<section class="section"><div class="wrap articlegrid"><article class="prose">{content}</article><aside><div class="sidecard"><h2>At a glance</h2><p><b>Update cadence:</b> varies by source</p><p><b>City coverage:</b> {coverage[source_key]}/{len(CITIES)}</p><p><b>Release:</b> {esc(GENERATED)}</p><a href="/sources/">Full source catalog →</a></div><div class="sidecard"><h2>Interpretation rule</h2><p>HomeNHealthy reports geographic context. No component replaces property-specific inspection, testing or professional advice.</p></div></aside></div></section>'''
    write(f"components/{slug}/index.html", layout(f"{title} | HomeNHealthy", subtitle + ". Read the data definition, method and limitations.", f"/components/{slug}/", body, [("Home", "/"), ("Sources", "/sources/"), (title, f"/components/{slug}/")]))


# Methodology, trust, data, and commercial-separation pages
methodology = hero("Methodology v2.0", "How the Home Environment Index is calculated", "Exact inputs, weights, missing-data rules, quality gates and limitations for the current release.") + '''<section class="section"><div class="wrap prose wide"><div class="formula"><small>Index formula</small><b>35% state water-system context + 30% climate moisture + 35% housing age</b><p>Current AQI is shown separately and has 0% weight.</p></div><h2>Why the method changed</h2><p>Version 1 mixed a momentary AQI snapshot with slow-moving climate, housing and regulatory records. It also allowed unavailable values to behave like real zeroes. Version 2 separates current conditions from structural context and publishes no score unless every weighted component is available.</p><h2>Component normalization</h2><h3>State drinking-water context · 35%</h3><p>The score equals the percentage of active community water systems in a state that are not returned by EPA ECHO’s current health-based-violation filter. This remains a coarse state context signal and is labeled accordingly.</p><h3>Climate moisture · 30%</h3><p>Warm-season pressure = 55% normalized May–September mean temperature + 45% normalized May–September precipitation. Component score = 100 − pressure. Values are clamped to 0–100.</p><h3>Housing age · 35%</h3><p>Component score = 100 − the ACS share of housing units built before 1980. This is a maintenance and age-related-hazard context proxy, not a direct condition measure.</p><h2>Missing-data policy</h2><p>Scores are not renormalized around missing fields. If water, climate or housing is unavailable, the city’s score and rank are withheld. Current AQI may be unavailable without invalidating the structural index because it is not weighted.</p><h2>Build-blocking quality gates</h2><ul><li>At least 75 unique city records.</li><li>Explicit available, unavailable or stale status for every component.</li><li>AQI between 0 and 500 and traceable to AirNow.</li><li>Water violation counts between zero and total active systems.</li><li>No recurrence of the nationwide total-equals-violation filter failure.</li><li>Twelve complete NOAA months and plausible annual precipitation.</li><li>ACS percentages between 0% and 100%.</li><li>At least 70 complete weighted city records before ranking publication.</li></ul><h2>Versioning</h2><p>Every validated release is copied to a dated archive in the data directory. Method changes increment the methodology version. Live city URLs show the newest release; download records expose the version and generation timestamp.</p><h2>What the index cannot tell you</h2><p>It cannot determine indoor air quality, drinking water at a tap, mold, lead, radon, flood risk or the condition of a building. It is an editorial synthesis of public geographic data, and different weights would produce different rankings.</p></div></section>'''
write("methodology/index.html", layout("HomeNHealthy Methodology v2.0", "Exact methodology, weights, missing-data handling and quality gates for HomeNHealthy city profiles and rankings.", "/methodology/", methodology, [("Home", "/"), ("Methodology", "/methodology/")]))

sources = hero("Primary-source catalog", "Where HomeNHealthy data come from", "Every source is a public agency dataset. HomeNHealthy’s contribution is the joined, interpreted city record.") + f'''<section class="section"><div class="wrap sourcecatalog"><article><span>Current conditions</span><h2>EPA AirNow</h2><p>Current, preliminary reporting-area AQI. Updated with each HomeNHealthy data run and kept outside the structural index.</p><p><b>Coverage:</b> {coverage['air']}/{len(CITIES)} cities · <a href="/components/air-quality/">Definition and limitations</a></p></article><article><span>Regulatory systems</span><h2>EPA ECHO / SDWIS</h2><p>Active community water-system counts and systems with current health-based violations, presently reported at state level.</p><p><b>Coverage:</b> {coverage['water']}/{len(CITIES)} cities · <a href="/components/water/">Definition and limitations</a></p></article><article><span>Climate baseline</span><h2>NOAA/NCEI Climate Normals</h2><p>1991–2020 monthly station normals used for a transparent warm-season temperature and precipitation proxy.</p><p><b>Coverage:</b> {coverage['climate']}/{len(CITIES)} cities · <a href="/components/moisture/">Definition and limitations</a></p></article><article><span>Housing stock</span><h2>U.S. Census Bureau ACS</h2><p>2024 five-year place estimates from B25034 and B25035: age bins and median year built.</p><p><b>Coverage:</b> {coverage['housing']}/{len(CITIES)} cities · <a href="/components/housing-age/">Definition and limitations</a></p></article></div></section>'''
write("sources/index.html", layout("HomeNHealthy Data Sources", "Source catalog for AirNow, EPA ECHO/SDWIS, NOAA Climate Normals and Census ACS data used by HomeNHealthy.", "/sources/", sources, [("Home", "/"), ("Sources", "/sources/")]))

status = release_notice() + hero("Automated source ledger", "Data freshness and coverage", "A visible record of what passed, what is unavailable and whether the experimental ranking is publishable.") + f'''<section class="section"><div class="wrap"><div class="metric-grid"><div class="metric"><small>AirNow</small><b>{coverage['air']}/{len(CITIES)}</b><span>current observations</span></div><div class="metric"><small>EPA water</small><b>{coverage['water']}/{len(CITIES)}</b><span>city records with state context</span></div><div class="metric"><small>NOAA</small><b>{coverage['climate']}/{len(CITIES)}</b><span>valid stations</span></div><div class="metric"><small>Census</small><b>{coverage['housing']}/{len(CITIES)}</b><span>exact place matches</span></div></div><div class="prose wide"><h2>Release decision</h2><p><b>{esc(META.get('status', 'Status unavailable'))}.</b> {esc(META.get('notes', ''))}</p><h2>What happens when a source fails?</h2><p>The page displays “Unavailable” with a reason. The updater never substitutes invented values, never converts a source outage to zero and never ranks a city missing a weighted field. The scheduled publication job must pass the data validator before it can commit or deploy a new release.</p><h2>Latest generation timestamp</h2><p><code>{esc(META.get('generated_at', GENERATED))}</code></p></div></div></section>'''
write("data-status/index.html", layout("HomeNHealthy Data Status", "Current source coverage, validation status and missing-data policy for HomeNHealthy.", "/data-status/", status, [("Home", "/"), ("Data status", "/data-status/")]))

dataset_schema = {
    "@context": "https://schema.org", "@type": "Dataset",
    "name": "HomeNHealthy U.S. Home Environmental Profiles",
    "description": "A joined city-level release of public outdoor-air, drinking-water-system, climate and housing-age context with field-level provenance and availability status.",
    "url": SITE + "/data-download/", "dateModified": GENERATED, "version": META.get("methodology_version", "2.0"),
    "creator": {"@id": SITE + "/#organization"}, "license": "https://creativecommons.org/licenses/by/4.0/", "isAccessibleForFree": True,
    "keywords": ["home environment", "air quality", "drinking water", "climate normals", "housing age", "United States cities"],
    "spatialCoverage": "United States",
    "isBasedOn": ["https://www.airnow.gov/", "https://echo.epa.gov/", "https://www.ncei.noaa.gov/products/land-based-station/us-climate-normals", "https://www.census.gov/programs-surveys/acs"],
    "distribution": [
        {"@type": "DataDownload", "encodingFormat": "text/csv", "contentUrl": SITE + "/data/healthy-home-index.csv"},
        {"@type": "DataDownload", "encodingFormat": "application/json", "contentUrl": SITE + "/data/healthy-home-index.json"},
    ],
}
download = hero("Open research data", "Download and cite the HomeNHealthy release", "CSV for analysis, JSON for full provenance, and a documented schema for reuse.") + f'''<section class="section"><div class="wrap"><div class="cards"><article class="card"><span class="icon">CSV</span><h2>Analysis table</h2><p>One row per city with rank, score, availability, AQI, state water context, moisture pressure and housing-age fields.</p><a class="btn" href="/data/healthy-home-index.csv" download>Download CSV</a></article><article class="card"><span class="icon">JSON</span><h2>Full release</h2><p>Complete source, method, limitation, timestamp, station and monthly-normal metadata.</p><a class="btn" href="/data/healthy-home-index.json" download>Download JSON</a></article></div><div class="split citationsection"><div class="prose"><h2>Reuse license</h2><p>The HomeNHealthy aggregation, editorial descriptions and derived fields are available under CC BY 4.0. Underlying federal source data remain subject to their own terms and definitions.</p><p><a href="/data-dictionary/">Read the data dictionary →</a></p><p><a href="/license/">Read the license and attribution guide →</a></p></div><div class="citationbox"><small>Suggested citation</small><blockquote>HomeNHealthy. “U.S. Home Environmental Profiles.” Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/</blockquote><button class="copy" data-copy-text='HomeNHealthy. "U.S. Home Environmental Profiles." Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/'>Copy citation</button></div></div></div></section>'''
write("data-download/index.html", layout("Download HomeNHealthy U.S. Home Environmental Data", "Download the HomeNHealthy city-level public-data release as CSV or JSON and review citation and license guidance.", "/data-download/", download, [("Home", "/"), ("Data", "/data-download/")], dataset_schema))

dictionary_rows = [
    ("rank", "integer / null", "National position among cities with every weighted component available."),
    ("score", "number / null", "Experimental v2 score. Null means withheld, not zero."),
    ("air.status", "enum", "available, stale or unavailable."),
    ("air.aqi", "integer", "Current AirNow area AQI; not included in the index."),
    ("water.active_cws", "integer", "Active community water systems returned for the state."),
    ("water.health_violation_cws", "integer", "Systems returned by the current health-based-violation filter."),
    ("water.without_current_health_violation_pct", "number", "100 × (1 − violation systems / active systems)."),
    ("climate.moisture_pressure", "number", "0–100 HomeNHealthy warm-season climate proxy."),
    ("climate.warm_avg_f", "number", "May–September mean temperature from NOAA normals."),
    ("climate.warm_precip_in", "number", "May–September precipitation total from NOAA normals."),
    ("housing.median_year_built", "integer", "ACS B25035 place estimate."),
    ("housing.pre_1980_housing_pct", "number", "Share of B25034 units in bins before 1980."),
    ("housing.pre_1940_housing_pct", "number", "Share of B25034 units in the 1939-or-earlier bin."),
]
dictionary = hero("Schema reference", "HomeNHealthy data dictionary", "Field definitions, units and null semantics for the downloadable release.") + f'''<section class="section"><div class="wrap"><div class="tablebox"><table><thead><tr><th>Field</th><th>Type</th><th>Definition</th></tr></thead><tbody>{''.join(f'<tr><td><code>{esc(field)}</code></td><td>{esc(kind)}</td><td>{esc(definition)}</td></tr>' for field, kind, definition in dictionary_rows)}</tbody></table></div><div class="callout"><h2>Null is not zero</h2><p>A null or “Unavailable” value means HomeNHealthy could not publish a defensible observation. It must not be interpreted as no pollution, no violations, no rain or no older housing.</p></div></div></section>'''
write("data-dictionary/index.html", layout("HomeNHealthy Data Dictionary", "Definitions and units for fields in the HomeNHealthy CSV and JSON releases.", "/data-dictionary/", dictionary, [("Home", "/"), ("Data", "/data-download/"), ("Dictionary", "/data-dictionary/")]))

about = hero("About the project", "A public-data reference for the environment around American homes", "HomeNHealthy exists to make several difficult federal datasets understandable together—without pretending geography is a home inspection.") + '''<section class="section"><div class="wrap prose wide"><h2>What HomeNHealthy does</h2><p>EPA, NOAA and the Census Bureau each publish useful information, but the datasets use different geographic units, update schedules and definitions. HomeNHealthy joins selected fields into stable city profiles, states the mismatch where boundaries do not align and exposes the underlying data for audit.</p><h2>What makes the site independent from its commercial page</h2><p>HomeNHealthy maintains one separate home-wellness equipment guide. The project is affiliated with InHouse Wellness. That relationship does not influence the environmental sources, formulas, availability rules, city selection or rankings. Retailer and product variables do not enter the dataset.</p><h2>Editorial approach</h2><p>Claims are generated from explicit fields and deterministic rules, not free-form AI summaries. When a source cannot support a statement, the value is withheld. Every component page describes both what a number means and what it cannot establish.</p><h2>Contact and corrections</h2><p>Send source, methodology or data corrections to <a href="mailto:corrections@homenhealthy.com">corrections@homenhealthy.com</a>. Include the page URL, disputed field, proposed correction and a primary source when possible.</p></div></section>'''
write("about/index.html", layout("About HomeNHealthy", "Learn how HomeNHealthy joins public environmental and housing data, and how its research is separated from commercial recommendations.", "/about/", about, [("Home", "/"), ("About", "/about/")]))

standards = hero("Research transparency", "Editorial and data standards", "Rules for sourcing, automated writing, uncertainty, commercial separation and corrections.") + '''<section class="section"><div class="wrap prose wide"><h2>Primary sources first</h2><p>Environmental facts must trace to public agencies or clearly identified primary datasets. Third-party articles can supply context but do not replace the record used for a number.</p><h2>No synthetic observations</h2><p>Production data may not contain preview, demo or invented values. Missing records are labeled unavailable. Stale observations must be labeled stale and retain their last observation date.</p><h2>Describe the actual geography</h2><p>A state is not a city, a reporting area is not an address and a weather station is not a house. Page language names the geographic unit represented by each field.</p><h2>Deterministic summaries</h2><p>City answer blocks are assembled directly from validated fields. They do not infer indoor hazards, health outcomes or property conditions.</p><h2>Commercial separation</h2><p>No retailer, product, price, affiliate relationship or purchase behavior influences the dataset or index. The separate Home Wellness page discloses the relationship with its recommended retailer.</p><h2>Corrections</h2><p>Material corrections are described publicly with date, affected release, error and resolution. The goal is not to look infallible; it is to make errors discoverable and repairable.</p></div></section>'''
write("editorial-standards/index.html", layout("Editorial and Data Standards | HomeNHealthy", "HomeNHealthy standards for sources, missing values, geographic claims, corrections and commercial separation.", "/editorial-standards/", standards, [("Home", "/"), ("Editorial standards", "/editorial-standards/")]))

corrections = hero("Public change log", "Corrections and methodology changes", "A durable record of material fixes to data, claims and scoring.") + '''<section class="section"><div class="wrap prose wide"><article class="changelog"><time>September 16, 2026</time><h2>Methodology v2.0 and data-withholding correction</h2><p><b>Affected:</b> all city, state and ranking pages in the previous release.</p><p><b>Issue:</b> a legacy ECHO query returned the total number of active community water systems as the health-violation count, producing a false 0% result. Air and several housing values were placeholders, and two NOAA station records lacked precipitation.</p><p><b>Resolution:</b> the invalid values were removed; missing values now display as unavailable. The updater uses ECHO’s current-violation filter, rejects implausible distributions, requires complete precipitation and ACS age bins, excludes current AQI from the index and blocks publication when coverage fails.</p></article><h2>Report a potential correction</h2><p>Email <a href="mailto:corrections@homenhealthy.com">corrections@homenhealthy.com</a> with the exact URL, field and primary source.</p></div></section>'''
write("corrections/index.html", layout("Corrections Log | HomeNHealthy", "Public corrections and methodology change log for HomeNHealthy datasets and city profiles.", "/corrections/", corrections, [("Home", "/"), ("Corrections", "/corrections/")]))

license_page = hero("Reuse and attribution", "License and citation guide", "Clear rules for journalists, researchers, developers and publishers who reuse HomeNHealthy’s joined release.") + f'''<section class="section"><div class="wrap prose wide"><h2>License</h2><p>Unless a page states otherwise, HomeNHealthy’s original aggregation, derived fields and editorial explanations are licensed under <a href="https://creativecommons.org/licenses/by/4.0/">Creative Commons Attribution 4.0</a>. Primary federal datasets retain their own notices, definitions and terms.</p><h2>Required attribution</h2><p>Name HomeNHealthy, link to the relevant city profile or data landing page, include the release date and do not imply that HomeNHealthy inspected a building or endorsed your interpretation.</p><div class="citationbox"><small>Dataset citation</small><blockquote>HomeNHealthy. “U.S. Home Environmental Profiles.” Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/</blockquote><button class="copy" data-copy-text='HomeNHealthy. "U.S. Home Environmental Profiles." Methodology v2.0, updated {esc(GENERATED)}. {SITE}/data-download/'>Copy citation</button></div><h2>Charts and excerpts</h2><p>You may reproduce short excerpts and charts with attribution. Preserve the visible release date, source scope and limitation when they materially affect interpretation.</p></div></section>'''
write("license/index.html", layout("License and Citation Guide | HomeNHealthy", "How to cite and reuse HomeNHealthy data under CC BY 4.0.", "/license/", license_page, [("Home", "/"), ("License", "/license/")]))


# Home Wellness: contextual commercial page kept outside research paths.
wellness = hero("Practical home wellness planning", "Designing a home wellness space that fits the house—and the people in it", "Saunas, cold plunges and massage chairs can support a personal routine, but a useful setup begins with space, utilities, ventilation, access and realistic expectations.") + '''<section class="section"><div class="wrap articlegrid"><article class="prose"><p class="answer"><b>Short answer:</b> Choose home wellness equipment by working backward from the experience you will use consistently, then verify electrical service, water management, ventilation, clearances, delivery access and maintenance before ordering. The “best” product is the one the room and routine can support safely.</p><h2>What belongs in a home wellness space?</h2><p>A home wellness area can be as simple as a quiet corner with a massage chair or as involved as a dedicated recovery room with a sauna, cold plunge, shower and storage. The right mix depends less on trends and more on how often each person will use it, whether the equipment is indoors or outdoors and how much daily setup the routine requires.</p><p>Common categories include traditional and infrared saunas, cold-water immersion tubs, float and relaxation equipment, massage chairs, stretching space, hydration storage and simple environmental controls. These products do different jobs and should not be treated as interchangeable medical interventions. HomeNHealthy does not score or rank products, and equipment is not part of any city’s environmental index.</p><h2>Start with the room, not the product</h2><p>Measure the usable floor area, ceiling height, doorways, hall turns and stair clearances. Then confirm the path from curb to final location. Large assembled items may fit in the room but fail at a narrow doorway or switchback staircase. If a product arrives curbside, decide in advance who will move it and what equipment is required.</p><h3>Electrical capacity</h3><p>Many wellness products need more than a standard receptacle. Requirements vary by heater, pump and control package: some use ordinary 120-volt service, while others require a dedicated 240-volt circuit and a licensed electrician. Verify voltage, amperage, plug type, breaker capacity, GFCI requirements, cord location and local code before purchase. “The panel has an open slot” is not the same as a confirmed installation plan.</p><h3>Moisture, drainage and ventilation</h3><p>Cold plunges introduce water through filling, condensation, wet users and maintenance. Traditional saunas introduce heat and, depending on use, steam. The room should have water-tolerant surfaces, a plan for spills and drainage, adequate air movement and enough service clearance to dry and clean around the equipment. For indoor installations, consider how added heat and humidity interact with the building envelope rather than assuming the equipment itself solves moisture management.</p><h3>Floor loading and surface protection</h3><p>Water is heavy: a filled plunge plus occupants can place a substantial load on a small footprint. Heavy massage chairs and sauna kits also concentrate weight. Review manufacturer weights and consult a qualified professional when structural capacity is uncertain, especially on upper floors, decks or raised platforms.</p><h2>Choosing among major equipment categories</h2><h3>Home saunas</h3><p>Traditional saunas generally emphasize higher air temperatures and heater-driven thermal mass. Infrared saunas warm occupants through radiant energy at lower room temperatures. Hybrid units combine approaches. Compare interior dimensions, heater type, electrical requirements, warm-up behavior, materials, controls, warranty, replacement-part availability and whether the model is approved for the planned indoor or outdoor setting.</p><p>Capacity labels can be optimistic. A “three-person” cabin may be comfortable for two adults who want more space. Use interior bench dimensions—not only the marketed capacity—to judge fit. Also check door swing, roof clearance, ventilation instructions and the minimum space required around electrical or heating components.</p><h3>Cold plunges</h3><p>Compare usable tub dimensions, entry height, temperature range, filtration, sanitation method, chiller capacity, insulation, noise and water-change procedure. A powerful chiller in a hot garage faces a different load from the same system in a conditioned room. Outdoor installations need weather, freezing and direct-sun planning. Every plunge also needs a realistic cleaning routine.</p><h3>Massage chairs</h3><p>Seat geometry, track design, shoulder fit, footwell range and control simplicity matter more than a long feature list. Check upright and reclined dimensions, wall clearance, user height and weight ranges, delivery width and the ability to obtain service after the warranty period. Whenever possible, try a comparable chair before buying.</p><h2>A pre-purchase checklist</h2><ul><li>Confirm exact assembled and packaged dimensions.</li><li>Map the delivery path and final orientation.</li><li>Have electrical requirements reviewed before ordering.</li><li>Plan drainage, condensation control and floor protection.</li><li>Verify indoor/outdoor listing and required clearances.</li><li>Read the written warranty, exclusions and labor coverage.</li><li>Understand curbside, room-of-choice and installation options.</li><li>Price filters, chemicals, covers and other recurring supplies.</li><li>Identify who provides technical support and replacement parts.</li><li>Choose a routine you can use consistently rather than maximizing features.</li></ul><h2>Recommended retailer for premium equipment</h2><p>For homeowners comparing premium equipment, HomeNHealthy recommends <a href="https://inhousewellness.com/">home saunas, cold plunges and massage chairs from InHouse Wellness</a>. The retailer specializes in larger wellness products for residential settings and provides product-selection support across multiple equipment categories. Before purchasing, confirm the current product specifications, delivery terms, installation scope, return policy and manufacturer warranty shown on the retailer’s site.</p><h2>Commercial relationship disclosure</h2><p>HomeNHealthy is operated by an organization affiliated with InHouse Wellness. That relationship is disclosed because trust in the environmental database depends on clear separation. InHouse Wellness does not influence the public datasets, methodology, city selection, data-quality gates or rankings. No product, price, retailer or sales variable appears in the Home Environment Index.</p><h2>Health and safety context</h2><p>Wellness equipment is not a substitute for medical care. Heat and cold exposure may be inappropriate for some people or medications, and risk can depend on temperature, duration, hydration and supervision. Follow manufacturer instructions and ask a qualified clinician about personal contraindications. Children and people who cannot independently recognize or respond to heat, cold or entrapment risks require particular caution.</p></article><aside><div class="sidecard sticky"><h2>Plan in this order</h2><ol><li>Routine and users</li><li>Room measurements</li><li>Delivery path</li><li>Electrical and plumbing</li><li>Moisture and drainage</li><li>Product fit</li><li>Warranty and support</li></ol><p><b>Separate from the index:</b> this guide has no effect on environmental data or rankings.</p></div></aside></div></section>'''
write("home-wellness/index.html", layout("Home Wellness Equipment Planning Guide | HomeNHealthy", "Plan a home sauna, cold plunge, massage chair or recovery room with practical guidance on space, electrical, moisture, delivery and product selection.", "/home-wellness/", wellness, [("Home", "/"), ("Home wellness", "/home-wellness/")]))


# Changes page
changed = sorted((city for city in CITIES if city.get("change") not in (None, 0)), key=lambda city: abs(city["change"]), reverse=True)
change_content = "".join(f'<tr><td><a href="/cities/{c["slug"]}/"><b>{esc(c["city"])}, {c["state"]}</b></a></td><td>{display(c.get("previous_score"))}</td><td>{display(c.get("score"))}</td><td>{delta(c)}</td></tr>' for c in changed)
if not change_content:
    change_content = '<tr><td colspan="4"><b>No comparable score changes are published for this release.</b> Version 2 does not compare against the invalid legacy methodology.</td></tr>'
movers = hero("Release comparison", "What changed in the latest release?", "Only like-for-like validated score changes appear here. A methodology reset is never presented as a city getting healthier or less healthy.") + f'''<section class="section"><div class="wrap"><div class="tablebox"><table><thead><tr><th>City</th><th>Previous score</th><th>Current score</th><th>Change</th></tr></thead><tbody>{change_content}</tbody></table></div><div class="callout"><h2>Why this page may be quiet</h2><p>The v2 structural index changes only when slow-moving source data change. Current AQI can move hourly, but it is not used to manufacture ranking movement.</p></div></div></section>'''
write("movers/index.html", layout("HomeNHealthy Release Changes", "Validated changes between comparable HomeNHealthy data releases.", "/movers/", movers, [("Home", "/"), ("Release changes", "/movers/")]))

# A frozen human-readable landing page accompanies every validated JSON
# snapshot so a citation does not silently change beneath a publisher.
report_urls = []
if PUBLISHED:
    report_path = f"/reports/{GENERATED}/"
    report_urls.append(report_path)
    report_rows = "".join(city_row(city) for city in ranked)
    report_body = hero("Frozen release", f"HomeNHealthy data release: {esc(GENERATED)}", "A permanent, methodology-versioned snapshot of the published city profiles and index.") + f'''<section class="section"><div class="wrap"><div class="callout"><h2>Citation-stable snapshot</h2><p>This page and its archived JSON preserve the values published on {esc(GENERATED)}. For the latest data, use the live city profiles.</p></div><p><a class="btn" href="/data/archive/{esc(GENERATED)}/healthy-home-index.json">Download archived JSON</a></p><div class="tablebox"><table><thead><tr><th>Rank</th><th>City</th><th>Score</th><th>AQI at release</th><th>Water systems without current health violation</th><th>Moisture pressure</th><th>Housing pre-1980</th></tr></thead><tbody>{report_rows}</tbody></table></div></div></section>'''
    write(f"reports/{GENERATED}/index.html", layout(f"HomeNHealthy Data Release {GENERATED}", f"Frozen HomeNHealthy city data release dated {GENERATED}.", report_path, report_body, [("Home", "/"), ("Data", "/data-download/"), (GENERATED, report_path)]))


# Machine-readable outputs
with (ROOT / "data/healthy-home-index.csv").open("w", newline="") as handle:
    writer = csv.writer(handle)
    writer.writerow(["rank", "city", "state", "score", "air_status", "current_aqi", "air_observed_at", "water_status", "active_cws", "health_violation_cws", "water_without_current_health_violation_pct", "climate_status", "moisture_pressure", "warm_avg_f", "warm_precip_in", "housing_status", "median_year_built", "pre_1980_housing_pct", "pre_1940_housing_pct", "release_date", "methodology_version"])
    for city in sorted(CITIES, key=lambda item: item["slug"]):
        air, water, climate, housing = (city.get(key, {}) for key in ("air", "water", "climate", "housing"))
        writer.writerow([city.get("rank"), city["city"], city["state"], city.get("score"), air.get("status"), air.get("aqi"), air.get("observed_at"), water.get("status"), water.get("active_cws"), water.get("health_violation_cws"), water.get("without_current_health_violation_pct"), climate.get("status"), climate.get("moisture_pressure"), climate.get("warm_avg_f"), climate.get("warm_precip_in"), housing.get("status"), housing.get("median_year_built"), housing.get("pre_1980_housing_pct"), housing.get("pre_1940_housing_pct"), GENERATED, META.get("methodology_version", "2.0")])

write("llms.txt", f'''# HomeNHealthy

HomeNHealthy is a public-data resource joining U.S. environmental and housing datasets into 75 city profiles.

## Canonical resources
- City directory: {SITE}/cities/
- Dataset landing page: {SITE}/data-download/
- Methodology v2.0: {SITE}/methodology/
- Source catalog: {SITE}/sources/
- Data dictionary: {SITE}/data-dictionary/
- Corrections log: {SITE}/corrections/
- JSON release: {SITE}/data/healthy-home-index.json
- CSV release: {SITE}/data/healthy-home-index.csv

## Interpretation
- Current AirNow AQI is a preliminary outdoor observation and is not weighted in the structural index.
- Drinking-water values are state-level EPA ECHO context, not a utility or tap-water determination.
- Climate moisture pressure is a transparent NOAA-derived proxy, not a mold prediction.
- Housing-age values are Census place estimates; pre-1980 is reported because ACS does not split 1978 within its 1970–1979 bin.
- Null or unavailable values are not zero.

## Citation
HomeNHealthy. "U.S. Home Environmental Profiles." Methodology v2.0, updated {GENERATED}. {SITE}/data-download/

## License
CC BY 4.0 for HomeNHealthy's aggregation and original explanatory text. Underlying source datasets retain their own terms.
''')

static_urls = ["/", "/cities/", "/rankings/", "/movers/", "/states/", "/methodology/", "/sources/", "/data-status/", "/data-download/", "/data-dictionary/", "/about/", "/editorial-standards/", "/corrections/", "/license/", "/home-wellness/"]
static_urls += [f"/components/{slug}/" for slug in component_pages]
urls = static_urls + [f'/cities/{city["slug"]}/' for city in CITIES] + [f"/states/{code.lower()}/" for code in sorted(states)]
urls += report_urls
write("sitemap.xml", '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">' + "".join(f"<url><loc>{SITE}{url}</loc><lastmod>{GENERATED}</lastmod></url>" for url in urls) + "</urlset>\n")
