# This code determines the nearest small and large city within a specified radius list
# It will make use of the GeoDB Cities API

# GeoDB Cities API: MotorMouth has a $25/mo subscription that 
# allows 1,000,000 requests per day and 50 requests per second, 1000 records per request
# 'x-rapidapi-host': 'wft-geo-db.p.rapidapi.com'
# 'x-rapidapi-key': 'b000cb621dmshd1465d7c0cda2aap1cf72fjsn2bf3ae69613f'
# Website:  http://geodb-cities-api.wirefreethought.com/
# Latitude/longitude must be in ISO-6709 format: ±DD.DDDD±DDD.DDDD

import json
from operator import itemgetter
import pprint
import sys
import time
import requests
import math
from mmTestLocations import testLocations
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
verbose = False


# Given a latitude, longitude, this class determines the nearest city within a specified 
# radius, and the cardinal direction "from" that city.  (e.g. the lat/lon supplied is 30 
# miles south of Orlando, FL)
# Returns getNearestCityResponseCode 200=OK, 204=City not found, 
# 400=bad API request/unknown error
class FindCity:
    def __init__(self):
        self.distanceUnit = "MI"                # Miles (KM also available)
        self.cityRadiusList = [80, 250, 500]    # Search for cities with an increasing radius until at 
                                                # least one city is found
        self.minPopulation = 1                  # Use minimum population of 1 to make sure we find 
                                                # small cities in rural areas
        self.sort = "population"                # Sort by population in ascending order
        self.numResults = 1000                  # Our subscription returns 1000 cities max
        self.deviceLat = 0
        self.deviceLon = 0
        self.startTime = 0
        self.response = {
            "timestamp": 0,
            "apiResponseTime" : 0,
            "error" : True,
            "errorMessage" : None,
            "responseCode" : 400,
            "deviceLat": 0,
            "deviceLon": 0,
            "searchRadius": 0,
            "totalNumCitiesFound": 0,
            "smallCityName": "unknown",
            "smallCityState": "",
            "smallCityStateCode": "",
            "smallCityDistance": 0,
            "smallCityCardinalDir": "",
            "smallCityLat": 0,
            "smallCityLon": 0,
            "smallCityPopulation": 0,
            "smallCityWikiDataId": "",
            "largeCityName": "unknown",
            "largeCityState": "",
            "largeCityStateCode": "",
            "largeCityDistance": 0,
            "largeCityCardinalDir": "",
            "largeCityLat": 0,
            "largeCityLon": 0,
            "largeCityPopulation": 0,
            "largeCityWikiDataId": "",
        }

     
    # Supply lat/lon in this format:  lat:  58.19788744662251  lon:  -107.2265312450813
    def getCities(self):
        self.nearestCity = "unknown"
        self.apiResponseCode = 0
        self.getCityResponseCode = 400
        self.error = True
        self.errorMessage = ""
        self.sort = "-population"               # Sort in descending population order
        
        # API call to get list of nearby cities in a JSON format
        # Ensure Latitude/longitude is in ISO-6709 format: ±DD.DDDD±DDD.DDDD
        # Lat/lon pairs typically do not include a plus sign for positive values,
        #  so we need to add one if the value is positive
        # Call API for increasingly larger radius until a city is found
        
        self.startTime = time.perf_counter()
        for self.radius in self.cityRadiusList:
            self.response["searchRadius"] = self.radius
            try:
                locationId = ('+' if self.deviceLat > 0 else '') + str(self.deviceLat) + ('+' if self.deviceLon > 0 else '') + str(self.deviceLon)
                url = f"https://wft-geo-db.p.rapidapi.com/v1/geo/locations/{locationId}/nearbyCities"
                querystring = {
                    "radius": self.radius, 
                    "limit": self.numResults, 
                    "minPopulation": self.minPopulation,
                    "distanceUnit": self.distanceUnit, 
                    "sort": self.sort, 
                    "types": "CITY"
                    }
                headers = {
                    'x-rapidapi-host': "wft-geo-db.p.rapidapi.com",
                    'x-rapidapi-key': "b000cb621dmshd1465d7c0cda2aap1cf72fjsn2bf3ae69613f"
                    }
                self.api_response = requests.request("GET", url, headers=headers, params=querystring)
                if verbose == True: print(json.dumps(self.api_response.json(), indent=4))
                self.apiResponseCode = self.api_response.status_code
                if self.apiResponseCode != 200:
                    self.getCityResponseCode = 400
                    self.errorMessage = f'bad response from findNearestCity module url: {self.api_response.url} with response code {self.apiResponseCode}'
                    self.error = True
                    if verbose == True: print(self.errorMessage)
                    # TODO send error to server log
                    return
                
                self.api_response = self.api_response.json()
                # Check for errors in API response not indicated by a bad response code
                if ("errors" in self.api_response.keys()):
                    self.nearestCity = "unknown"
                    self.typeFound = "unknown"
                    self.getCityResponseCode = 400
                    self.errorMessage = f'errors in JSON response from findNearestCity module url: {url} with response code {self.apiResponseCode}'
                    self.error = True
                    if verbose == True: print(self.errorMessage)
                    # TODO send error to server log
                    return
                elif "data" in self.api_response.keys() and len(self.api_response['data']) > 0: 
                    # We have a list of one or more cities
                    # In rare circumstances, we might have only one unknown city in the list
                    if self.api_response['data'][0]["city"] != "unknown":
                        
            # ********** Success! Found at least one valid city. *********
                        self.nearestCity = "known"
                        self.getCityResponseCode = 200
                        self.error = False
                        # save number of cities found
                        self.response["totalNumCitiesFound"] = len(self.api_response['data'])
                        self.errorMessage = ""
                        if verbose == True: print(f'City found within a {self.radius} mile radius')
                        # break out of for loop, we don't need to check a larger radius
                        break
                        
                        
                else:
                    # self.city must be unknown which means no city found in this radius
                    # set up a 204 error in case this is the last loop
                    self.getCityResponseCode = 204
                    self.errorMessage = f'No city found in JSON response within a {self.radius} mile radius.\nProblem occcured in findNearestCity module with url: {url}\nResponse code returned by url: {self.apiResponseCode}'
                    self.error = True
                    if verbose == True: print(self.errorMessage)
                    # TODO send error to server log
                    # No city found in given radius, so do another loop if needed
                    pass
            
            except Exception as e:
                # Unknown problem, return with error = True and error mesage.
                self.getCityResponseCode = 400
                self.errorMessage = f'Unknown error in API response findNearestCity module url: {url}'
                self.error = True
                if verbose == True: print(f' except error: {e}, error msg: {self.errorMessage}')
                # TODO send error to server log
                return
        
        # This code is executed if we found at least one valid city in the given radius
        if self.getCityResponseCode == 200:
            self.sortCityByPopulation()
            self.sortCityByDistance()
        self.response["deviceLat"] = self.deviceLat
        self.response["deviceLon"] = self.deviceLon
        self.response["apiResponseTime"] = time.perf_counter() - self.startTime
        return



            
    # This function sorts the JSON response by distance for the nearest CITY record    
    def sortCityByDistance(self):
        # TODO add error handling
        sortedList = sorted(self.api_response['data'], key=itemgetter('distance'))
        # The first record should be the closest city
        cityRecord = sortedList[0] 
        self.response["timestamp"] = time.time()
        self.response["smallCityName"] = cityRecord['city']
        self.response["smallCityState"] = cityRecord['region']
        self.response["smallCityStateCode"] = cityRecord['regionCode']
        self.response["smallCityDistance"] = round(cityRecord['distance'],1)
        self.response["smallCityLat"] = cityRecord['latitude']
        self.response["smallCityLon"] = cityRecord['longitude']
        self.response["smallCityCardinalDir"] = self.getCardinalDirection(self.response["smallCityLat"], self.response["smallCityLon"])
        self.response["smallCityRadius"] = self.radius
        self.response["smallCityPopulation"] = cityRecord['population']
        self.response["smallCityWikiDataId"] = cityRecord['wikiDataId']
        # if verbose == True: pprint.pprint(sortedList, sort_dicts=False)
        return
    
    
    def sortCityByPopulation(self):
        # TODO add error handling
        # The first record should be the largest city, so no sorting is really needed
        # If we get a upgraded subscription that allows 1000 results vs. 100, we might
        # need this sort function as two API calls won't be needed.
        # sortedList = sorted(self.api_response['data'], key=itemgetter('population'))
        # cityRecord = sortedList[0] 
        cityRecord = self.api_response["data"][0] 
        self.response["timestamp"] = time.time()
        self.response["largeCityName"] = cityRecord['city']
        self.response["largeCityState"] = cityRecord['region']
        self.response["largeCityStateCode"] = cityRecord['regionCode']
        self.response["largeCityDistance"] = round(cityRecord['distance'],1)
        self.response["largeCityLat"] = cityRecord['latitude']
        self.response["largeCityLon"] = cityRecord['longitude']
        self.response["largeCityCardinalDir"] = self.getCardinalDirection(self.response["largeCityLat"], self.response["largeCityLon"])
        self.response["largeCityRadius"] = self.radius
        self.response["largeCityPopulation"] = cityRecord['population']
        self.response["largeCityWikiDataId"] = cityRecord['wikiDataId']
        if verbose == True: pprint.pprint(cityRecord, sort_dicts=False)
        return


    # This takes two lat/lon pairs and calculates the cardinal/ordinal direction "from" the
    #  nearest city "to" the car or phone coordinates (e.g. 23 miles south of Orlando, FL)
    def getCardinalDirection(self, cityLat, cityLon):
        dLon = (self.deviceLon - cityLon)
        x = math.cos(math.radians(self.deviceLat)) * math.sin(math.radians(dLon))
        y = math.cos(math.radians(cityLat)) * math.sin(math.radians(self.deviceLat)) - math.sin(math.radians(cityLat)) * math.cos(math.radians(cityLat)) * math.cos(math.radians(dLon))
        bearing = math.atan2(x,y)   # use atan2 to determine the quadrant
                                    # this returns values from +PI to -PI
        bearing = math.degrees(bearing)
                                    # Change degrees to a cardinal/ordinal value (i.e Northeast)
        bearing = bearing if bearing != 0 else ++bearing        # if = zero, chanfe to 1 t prevent division error
        bearing = bearing if bearing >= 0 else 360 + bearing    # convert negative bearing to equivalent positive bearing e.g -60 to 300 degrees
        index = round(int(bearing)/360*8)
        cardinal = ["north","northeast","east","southeast","south","southwest","west","northwest","north"]
        return(cardinal[index])


if __name__ == "__main__":
    
    # Right click on Google maps and paste here
    # deviceLatLon = ["qr", 43.33076703754544, -140.63629728013532] TODO this generates an error in the try block that the except block does not handle properly

    testLocations = deviceLatLon = [[[63.372075944330795, -113.79973399704073], "test"]] # 5 Harbour Isle
    for location in testLocations:
        city = FindCity()
        city.cityRadiusList = [80, 250, 500]
        # Note, if the first radius is too large in urban areas, you might receive more than 1000 records
        # which means you could miss the nearest small city.  In practice, this dos not seem to be an issue
        # and 80 miles works very well for most places in the US
        # These coordinates near NY, NY produce over 1000, but still provide good data
        # 40.634017873428554, -73.9658405188686
        
        # Set lat/lon in the object and search for two cities
        city.deviceLat = location[0][0]
        city.deviceLon = location[0][1]
        city.getCities()
        if city.getCityResponseCode == 200:
            print(f'You are {city.response["smallCityDistance"]} miles {city.response["smallCityCardinalDir"]} of {city.response["smallCityName"]}, {city.response["smallCityState"]}, population {city.response["smallCityPopulation"]}.')
            print(f'WikiDataId = {city.response["smallCityWikiDataId"]}')
            print(f'You are {city.response["largeCityDistance"]} miles {city.response["largeCityCardinalDir"]} of {city.response["largeCityName"]}, {city.response["largeCityState"]}, population {city.response["largeCityPopulation"]}.')
            print(f'WikiDataId = {city.response["largeCityWikiDataId"]}')
        else:
            print(f'No valid cities found within {city.radius} miles')
        # pprint.pprint(city.response, sort_dicts=False)
        print(f'Time to get city data data: {city.response["apiResponseTime"]} seconds')
        print(f'\nJSON Response:')
        pprint.pprint(city.response, sort_dicts=False)


    