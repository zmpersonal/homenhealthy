from pathlib import Path
import os,json,re,math,csv,io,time,subprocess,sys
from datetime import date
import requests
ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'data/healthy-home-index.json'
S=requests.Session();S.headers.update({'User-Agent':'HomeNHealthy.com public environmental data index'})
CENSUS=os.environ.get('CENSUS_API_KEY','').strip()
if not CENSUS: raise RuntimeError('CENSUS_API_KEY is not set. Add it under Settings > Secrets and variables > Actions.')
STATE_FIPS={'AL':'01','AK':'02','AZ':'04','AR':'05','CA':'06','CO':'08','CT':'09','DE':'10','DC':'11','FL':'12','GA':'13','HI':'15','ID':'16','IL':'17','IN':'18','IA':'19','KS':'20','KY':'21','LA':'22','ME':'23','MD':'24','MA':'25','MI':'26','MN':'27','MS':'28','MO':'29','MT':'30','NE':'31','NV':'32','NH':'33','NJ':'34','NM':'35','NY':'36','NC':'37','ND':'38','OH':'39','OK':'40','OR':'41','PA':'42','RI':'44','SC':'45','SD':'46','TN':'47','TX':'48','UT':'49','VT':'50','VA':'51','WA':'53','WV':'54','WI':'55','WY':'56'}
NOAA_DIR='https://www.ncei.noaa.gov/data/normals-monthly/1991-2020/access/'
GHCN='https://www.ncei.noaa.gov/pub/data/ghcn/daily/ghcnd-stations.txt'
AIRNOW='https://files.airnowtech.org/airnow/today/reportingarea.dat'
ECHO='https://echodata.epa.gov/echo/sdw_rest_services.get_systems'

def clamp(x,a,b):return max(a,min(b,x))
def num(x):
 try:return float(str(x).strip())
 except:return None
def hav(a,b,c,d):
 r=3958.7613;p1,p2=math.radians(a),math.radians(c);dp=math.radians(c-a);dl=math.radians(d-b);z=math.sin(dp/2)**2+math.cos(p1)*math.cos(p2)*math.sin(dl/2)**2;return 2*r*math.asin(math.sqrt(z))
def month_num(row):
 s=str(row.get('DATE','')).strip()
 if s.isdigit() and 1<=int(s)<=12:return int(s)
 for k in ('month','MONTH'):
  if str(row.get(k,'')).isdigit():return int(row[k])
 return None
def score_air(aqi):
 if aqi is None:return None
 if aqi<=20:return 100
 if aqi<=50:return 100-(aqi-20)*.67
 if aqi<=100:return 80-(aqi-50)*.6
 if aqi<=150:return 50-(aqi-100)*.6
 if aqi<=200:return 20-(aqi-150)*.4
 return 0
def score_housing(y):return clamp(25+(y-1940)*.92,20,100)
def moisture(monthly):
 warm=[m for m in monthly if m.get('month') in (5,6,7,8,9)]
 t=sum(m.get('tavg_f',65) for m in warm)/max(1,len(warm));p=sum(m.get('prcp_in',0) or 0 for m in warm)
 pressure=clamp(.55*clamp((t-55)/35*100,0,100)+.45*clamp(p/25*100,0,100),0,100)
 return {'moisture_pressure':round(pressure,1),'score':round(100-pressure,1),'warm_avg_f':round(t,1),'warm_precip_in':round(p,1),'source':'NOAA/NCEI 1991–2020 U.S. Climate Normals'}

def fetch_airnow():
 r=S.get(AIRNOW,timeout=45);r.raise_for_status();out=[]
 for line in r.text.splitlines():
  parts=[x.strip().strip('"') for x in line.split('|')]
  if len(parts)<11:continue
  try:lat=float(parts[5]);lon=float(parts[6]);aqi=int(float(parts[8]))
  except:continue
  if aqi<0 or not parts[4]:continue
  out.append({'date':parts[0],'hour':parts[1],'tz':parts[2],'area':parts[3],'state':parts[4],'lat':lat,'lon':lon,'parameter':parts[7],'aqi':aqi,'category':parts[10]})
 if len(out)<100:raise RuntimeError(f'AirNow file parsed only {len(out)} records')
 return out

def nearest_air(city,rows):
 cand=[]
 for r in rows:
  if r['state']!=city['state']:continue
  d=hav(city['lat'],city['lon'],r['lat'],r['lon'])
  if d<=160:cand.append((d,r))
 if not cand:return None
 cand.sort(key=lambda x:x[0]);area=cand[0][1]['area'];same=[r for d,r in cand if r['area']==area]
 r=max(same,key=lambda x:x['aqi']);sc=score_air(r['aqi'])
 return {'aqi':r['aqi'],'category':r['category'],'reporting_area':area,'parameter':r['parameter'],'distance_miles':round(cand[0][0],1),'score':round(sc,1),'source':f'AirNow current reporting-area observation ({r["date"]} {r["hour"]} {r["tz"]})'}

def water_states(states):
 out={}
 for st in states:
  base={'output':'JSON','p_act':'Y','p_st':st,'p_systyp':'CWS'}
  try:
   a=S.get(ECHO,params=base,timeout=35);a.raise_for_status();total=int(a.json()['Results']['QueryRows'])
   b=S.get(ECHO,params={**base,'p_health':'Y'},timeout=35);b.raise_for_status();hv=int(b.json()['Results']['QueryRows'])
   pct=round(100*(1-hv/total),1) if total else None
   if pct is not None:out[st]={'active_cws':total,'health_violation_cws':hv,'compliance_pct':pct,'score':pct,'source':'EPA ECHO / SDWIS current health-based violation status'}
   print('ECHO',st,total,hv,pct)
  except Exception as e:print('ECHO preserved',st,e)
  time.sleep(.10)
 return out

def census_places(st):
 url='https://api.census.gov/data/2024/acs/acs5';p={'get':'NAME,B25035_001E','for':'place:*','in':f'state:{STATE_FIPS[st]}','key':CENSUS}
 r=S.get(url,params=p,timeout=40);r.raise_for_status();rows=r.json();hdr=rows[0];return [dict(zip(hdr,x)) for x in rows[1:]]
def normname(x):return re.sub(r'[^a-z0-9]','',x.lower().replace('saint','st'))
def match_place(city,rows):
 target=normname(city['city'])
 for r in rows:
  name=r['NAME'].split(',')[0];n=normname(re.sub(r'\s+(city|town|village|municipality|borough|CDP)$','',name,flags=re.I))
  if n==target:
   y=num(r.get('B25035_001E'));return int(y) if y and 1800<y<2030 else None
 return None

def normal_ids():
 r=S.get(NOAA_DIR,timeout=60);r.raise_for_status();ids=set(re.findall(r'href=["\']([A-Za-z0-9_]{11})\.csv',r.text));return {x for x in ids if x.startswith(('USW','USC'))}
def stations(ids):
 r=S.get(GHCN,timeout=90);r.raise_for_status();out=[]
 for line in r.text.splitlines():
  if len(line)<71:continue
  sid=line[:11].strip()
  if sid not in ids:continue
  try:lat=float(line[12:20]);lon=float(line[21:30])
  except:continue
  out.append({'id':sid,'lat':lat,'lon':lon,'state':line[38:40].strip(),'name':line[41:71].strip()})
 return out
_cache={}
def station_norm(st):
 sid=st['id']
 if sid in _cache:return _cache[sid]
 try:
  r=S.get(NOAA_DIR+sid+'.csv',timeout=35)
  if r.status_code!=200:_cache[sid]=None;return None
  rows=list(csv.DictReader(io.StringIO(r.text)));by={}
  for row in rows:
   m=month_num(row)
   if not m:continue
   d=by.setdefault(m,{})
   for k,o in [('MLY-TAVG-NORMAL','tavg_f'),('MLY-TMIN-NORMAL','tmin_f'),('MLY-TMAX-NORMAL','tmax_f'),('MLY-PRCP-NORMAL','prcp_in')]:
    v=num(row.get(k))
    if v is not None:d[o]=v
  months=[]
  for m in range(1,13):
   d=by.get(m,{})
   if 'tavg_f' not in d and 'tmin_f' in d and 'tmax_f' in d:d['tavg_f']=(d['tmin_f']+d['tmax_f'])/2
   if not all(k in d for k in ('tavg_f','tmin_f','tmax_f')):_cache[sid]=None;return None
   months.append({'month':m,'tmin_f':round(d['tmin_f'],1),'tmax_f':round(d['tmax_f'],1),'tavg_f':round(d['tavg_f'],1),'prcp_in':round(d.get('prcp_in',0),2)})
  _cache[sid]={'monthly':months,'station':sid,'station_name':st['name']};return _cache[sid]
 except:_cache[sid]=None;return None
def city_norm(c,sts):
 cand=[]
 for st in sts:
  d=hav(c['lat'],c['lon'],st['lat'],st['lon'])
  if d<150:cand.append((d+(0 if st['state']==c['state'] else 15),d,st))
 cand.sort(key=lambda x:x[0])
 for _,d,st in cand[:35]:
  n=station_norm(st)
  if n:return {**n,'distance_miles':round(d,1)}
 return None

def main():
 obj=json.load(open(DATA));cities=obj['cities'];old={c['slug']:c['score'] for c in cities}
 air=[]
 try:air=fetch_airnow();print('AirNow records',len(air))
 except Exception as e:print('AirNow preserved',e)
 w=water_states(sorted({c['state'] for c in cities}))
 acs={};acount=0
 for st in sorted({c['state'] for c in cities}):
  try:acs[st]=census_places(st);print('ACS',st,len(acs[st]))
  except Exception as e:print('ACS preserved',st,e)
 ncount=0
 try:ids=normal_ids();sts=stations(ids);print('NOAA candidate stations',len(sts))
 except Exception as e:sts=[];print('NOAA unavailable',e)
 for c in cities:
  if air:
   a=nearest_air(c,air)
   if a:c['air']=a
  if c['state'] in w:c['water']=w[c['state']]
  if c['state'] in acs:
   y=match_place(c,acs[c['state']])
   if y:c['housing']={'median_year_built':y,'score':round(score_housing(y),1),'source':'U.S. Census Bureau ACS 2024 5-year, B25035_001E'};acount+=1
  if sts:
   n=city_norm(c,sts)
   if n:c['monthly']=n['monthly'];c['station']=f"{n['station']} — {n['station_name']} ({n['distance_miles']} mi)";c['climate']=moisture(n['monthly']);ncount+=1
  c['previous_score']=old.get(c['slug'],c.get('score',0));c['score']=round(.30*c['air']['score']+.30*c['water']['score']+.20*c['climate']['score']+.20*c['housing']['score'],1);c['change']=round(c['score']-c['previous_score'],1)
 cities.sort(key=lambda x:x['score'],reverse=True)
 for i,c in enumerate(cities,1):c['rank']=i
 obj['cities']=cities;obj['meta']={'generated':date.today().isoformat(),'starter':False,'status':'Live public-data refresh','sources':{'airnow':sum(1 for c in cities if 'AirNow' in c['air'].get('source','')),'echo_states':len(w),'noaa_cities':ncount,'acs_cities':acount},'notes':'Missing source values preserve the last successful observation rather than being replaced with invented data.'}
 json.dump(obj,open(DATA,'w'),indent=2);print(json.dumps(obj['meta'],indent=2))
 if len(w)<40 or acount<40 or ncount<40:raise RuntimeError('Too little live source coverage; refusing to deploy. See source counts above.')
 subprocess.check_call([sys.executable,str(ROOT/'scripts/build_site.py')])
if __name__=='__main__':main()
