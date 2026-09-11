import math

def explain_delay(data: dict):
    contrib=[]
    delay=float(data.get("current_delay_mins",0) or 0)
    speed=float(data.get("current_speed_kmh",0) or 0)
    congestion=float(data.get("section_congestion_index",0) or 0)
    ahead=int(data.get("number_of_trains_ahead",0) or 0)
    rain=float(data.get("rainfall_mm",0) or 0)
    visibility=float(data.get("visibility_meters",999999) or 999999)
    restriction=float(data.get("speed_restriction_kmh",0) or 0)
    maintenance=int(data.get("track_maintenance_active",0) or 0)
    if delay >= 15: contrib.append("high current delay")
    if speed and speed < 50: contrib.append("reduced current speed")
    if congestion >= 70: contrib.append("high section congestion")
    if ahead >= 3: contrib.append("multiple trains ahead")
    if restriction > 0 and speed > restriction: contrib.append("speed restriction")
    if maintenance: contrib.append("active track maintenance")
    if rain >= 5: contrib.append("significant rainfall")
    if visibility < 1000: contrib.append("low visibility")
    if not contrib: contrib.append("current and historical operating conditions")
    confidence = min(0.95, 0.45 + 0.07*len(contrib))
    return {"reason": "Likely contributors: " + ", ".join(contrib) + ".", "confidence": round(confidence,2), "contributors": contrib}
