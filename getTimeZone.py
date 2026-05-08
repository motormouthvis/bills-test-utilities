
import pprint
import requests
location = (27.460030075510502, -80.3052323353209)
device_lat = location[0]
device_lon = location[1]
radius = 10
num_results = 1
min_population = 1
distance_unit = "MI"
sort = "population"

# Get nearest city to lat/lon
location_id = ('+' if device_lat > 0 else '') + str(device_lat) + ('+' if device_lon > 0 else '') + str(device_lon)
url = f"https://wft-geo-db.p.rapidapi.com/v1/geo/locations/{location_id}/nearbyCities"
querystring = {
    "radius": radius, 
    "limit": num_results, 
    "minPopulation": min_population,
    "distanceUnit": distance_unit, 
    "sort": sort, 
    "types": "CITY"
    }
headers = {
    'x-rapidapi-host': "wft-geo-db.p.rapidapi.com",
    'x-rapidapi-key': "b000cb621dmshd1465d7c0cda2aap1cf72fjsn2bf3ae69613f"
    }
api_response = requests.request("GET", url, headers=headers, params=querystring).json()
# Get city ID
id = api_response["data"][0]["id"]
print(f'ID: {id}')

url = f"https://wft-geo-db.p.rapidapi.com/v1/geo/cities/{id}"
querystring = {
    }
headers = {
    'x-rapidapi-host': "wft-geo-db.p.rapidapi.com",
    'x-rapidapi-key': "b000cb621dmshd1465d7c0cda2aap1cf72fjsn2bf3ae69613f"
    }
api_response = requests.request("GET", url, headers=headers, params=querystring).json()
pprint.pprint(api_response, sort_dicts=False)
print(f'Timezone for {device_lat}{device_lon}: {api_response["data"]["timezone"]}')
