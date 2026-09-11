from urllib.parse import quote

def directions_url(origin, destination, travelmode="driving"):
    return f"https://www.google.com/maps/dir/?api=1&origin={quote(str(origin))}&destination={quote(str(destination))}&travelmode={quote(travelmode)}"

def train_route_url(origin, destination):
    return directions_url(origin,destination,"transit")
