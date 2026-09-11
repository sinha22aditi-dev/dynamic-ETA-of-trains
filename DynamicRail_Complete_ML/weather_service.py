import requests

def get_weather(lat, lon, hours=6):
    url="https://api.open-meteo.com/v1/forecast"
    params={"latitude":lat,"longitude":lon,"current":"temperature_2m,relative_humidity_2m,precipitation,wind_speed_10m,visibility,weather_code",
            "hourly":"temperature_2m,precipitation_probability,precipitation,visibility,wind_speed_10m",
            "forecast_days":2,"timezone":"auto"}
    r=requests.get(url,params=params,timeout=10); r.raise_for_status(); j=r.json()
    current=j.get("current",{})
    return {"provider":"Open-Meteo","current":current,"hourly":{k:v[:hours] for k,v in j.get("hourly",{}).items() if isinstance(v,list)}}
