import pprint
import sys
import time
import requests
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')

verbose = True

# This function can return:
# 1. Nearby street (does good job and returns type of street and many other types)
# 2. Nearest address (not great)
# 3. Nearest intersection (does a good job)
# 4. Nearby populated place name (like city, does a good job)
# 5. Nearby POI (mostly worthless)
# 6. Extended find nearby - additional data


def geoNamesGetAddress(deviceLat, deviceLon):
    # POI finder is worthless - don't use
    url = f'http://api.geonames.org/findNearbyPOIsOSMJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    # Neighbourhood does not work well
    url = f'http://api.geonames.org/neighbourhoodJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    #findNearestAddress does not get correct street addresses many times, but OK for travelling device
    url = f'http://api.geonames.org/findNearestAddressJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    
    url = f'http://api.geonames.org/findNearbyPlaceNameJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    url = f'http://api.geonames.org/get?geonameId=4156018&username=motormouthvis'
    url = f'http://api.geonames.org/extendedFindNearby?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    url = f'http://api.geonames.org/findNearestIntersectionJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    url = f'http://api.geonames.org/findNearbyStreetsJSON?lat={deviceLat}&lng={deviceLon}&username=motormouthvis'
    try:
        response=requests.get(url)
        if response.status_code == 200:
            return response
    except:
        if verbose == True: print(f'Error {response.status_code}')
        if verbose == True: print(f'{response.text}')
        return

if __name__ == "__main__":
    start_time = time.perf_counter()
    location = [27.446046213275416, -80.32668693503692] # Right click on Google maps
    result = geoNamesGetAddress(location[0], location[1])
    # pprint.pprint(result.json(), sort_dicts=False, indent=4)
    pprint.pprint(result.text, sort_dicts=False, indent=4)
    # print(f'{result.text}')
    duration = time.perf_counter() - start_time
    print(f'Time to download geoCode data: {duration} seconds')









