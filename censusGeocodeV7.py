import json
import pprint
import requests
import time


# This function takes lat/lon in the US only, and returns census tract number, zip code and more
# It also determines if you are within the city limits of any city - If cityName is none, you are not in the city limits.
# See censusGeoDict below for the information we have chosen to capture
# API Docs: https://geocoding.geo.census.gov/geocoder/Geocoding_Services_API.html
# The link below provides a list of all available layers that the API will return.  We use layers="all".
# https://tigerweb.geo.census.gov/arcgis/rest/services/TIGERweb/tigerWMS_Current/MapServer
# Error = True is returned if census geoCode info is unable to be retrieved
# Note:  To improve performance, this function should be called immediately when the user 
# starts a MM session on the VUI, web or phone.  The resultant census tract number and zip code 
# can be used for census tract data queries and crimeGrade queries.
# The response time is usually 0.4 to 0.9 seconds
# Returns responseCode 200=OK, 204=Census data not found, 
# 400=bad API request/unknown error

def censusRevGeocode(lat, lon):
    verbose = False
    censusGeoDict = {
        "timestamp" : 0,
        "apiResponseTime" : None,
        "error" : True,
        "errorMessage" : None,
        "responseCode" : 400,
        "cityName" : None,
        "cityCenterLat" : None,
        "cityCenterLon" :None,
        "stateName" :None,
        "stateNum" :None,
        "stateAbbr" :None,
        "zipCode" :None,
        "countySubdivision" :None,
        "countyName" :None,
        "countyNum" :None,
        "censusRegion" :None,
        "censusTractNum" :None,
        "censusTractName" :None,
        "unifiedSchoolDistrict" :None,
        "votingDistrict" :None,
        "congressionalDistrict" :None,
        "micropolitanStatArea" :None
    }
    params = {
        "x": lon, 
        "y": lat,
        "format" : "json",
        "benchmark" : "Public_AR_Current",
        "vintage" : "Census2020_Current",
        "layers" : "all"
    }
    # You can also specify layers desired. E.g. "layers" : "Zip Code Tabulation Areas,Census Tracts",

    url = f'https://geocoding.geo.census.gov/geocoder/geographies/coordinates'
    censusGeoDict["timestamp"] = time.time()
    startTime = time.perf_counter()
    
    try:
        response=requests.get(url, params = params)
        if response.status_code != 200:
            censusGeoDict["errorMessage"] = f'Census geocode error for lat/lon ({lat} {lon}): API status code = {response.status_code} for url: {response.url}'
            censusGeoDict["responseCode"] = 400
            if verbose == True: print(censusGeoDict["errorMessage"])
            # TODO send error message to server log 
            return(censusGeoDict)
    except:
        censusGeoDict["errorMessage"] = f'Unknown Census geocode error for lat/lon ({lat} {lon}). Url: {url}'
        if verbose == True: print(censusGeoDict["errorMessage"])
        censusGeoDict["responseCode"] = 400
        # TODO send error message to server log and write dictionary to database
        return(censusGeoDict)
    
        
    try:
        # Map the json response from the API to our censusGeoDict dictionary using
        # more easily understood names
        result = response.json()
        if verbose == True: 
            print(f'URL for Census Request:\n {response.url}\n')
            print(f'JSON response from census API:')
            print(json.dumps(result, indent=4))
        if len(result["result"]["geographies"]) == 0:
            # No census data is available (e.g Mexico or Canada)
            censusGeoDict["errorMessage"] = f'No Census data is available for ({lat} {lon}). Url: {url}'
            censusGeoDict["responseCode"] = 204
            if verbose == True: print(censusGeoDict["errorMessage"])
            # TODO send error message to server log
            return(censusGeoDict)
        if result["result"]["geographies"].get("Census Tracts"):
            if result["result"]["geographies"]["Census Tracts"][0]["TRACT"] == "null":
                # TODO Is checking for "null" really correct?  Should we check for "" or None, or 
                # lack of a 4 digit number?
                # No tract number is available
                censusGeoDict["errorMessage"] = f'No tract number is available for ({lat} {lon}). Url: {url}'
                censusGeoDict["responseCode"] = 204
                if verbose == True: print(censusGeoDict["errorMessage"])
                # TODO send error message to server log and write dictionary to database
                return(censusGeoDict)
            else:
                # Success!  Census tract found
                censusGeoDict["error"] = False
                censusGeoDict["responseCode"] = 200
                censusGeoDict["censusTractNum"] = result["result"]["geographies"]["Census Tracts"][0]["TRACT"]
                censusGeoDict["censusTractName"] = result["result"]["geographies"]["Census Tracts"][0]["NAME"]
        
        if result["result"]["geographies"].get("Incorporated Places"):
            censusGeoDict["cityName"] = result["result"]["geographies"]["Incorporated Places"][0]["BASENAME"]
            censusGeoDict["cityCenterLat"] = result["result"]["geographies"]["Incorporated Places"][0]["CENTLAT"]
            censusGeoDict["cityCenterLon"] = result["result"]["geographies"]["Incorporated Places"][0]["CENTLON"]
        if result["result"]["geographies"].get("States"):
            censusGeoDict["stateName"] = result["result"]["geographies"]["States"][0]["NAME"]
            censusGeoDict["stateNum"] = result["result"]["geographies"]["States"][0]["STATE"]
            censusGeoDict["stateAbbr"] = result["result"]["geographies"]["States"][0]["STUSAB"]
        if result["result"]["geographies"].get("Zip Code Tabulation Areas"):
            censusGeoDict["zipCode"] = result["result"]["geographies"]["Zip Code Tabulation Areas"][0]["ZCTA5"]
        if result["result"]["geographies"].get("County Subdivisions"):
            censusGeoDict["countySubdivision"] = result["result"]["geographies"]["County Subdivisions"][0]["BASENAME"]
        if result["result"]["geographies"].get("Counties"):
            censusGeoDict["countyName"] = result["result"]["geographies"]["Counties"][0]["NAME"]
            censusGeoDict["countyNum"] = result["result"]["geographies"]["Counties"][0]["COUNTY"]
        if result["result"]["geographies"].get("Census Regions"):
            censusGeoDict["censusRegion"] = result["result"]["geographies"]["Census Regions"][0]["NAME"]
        if result["result"]["geographies"].get("Unified School Districts"):
            censusGeoDict["unifiedSchoolDistrict"] = result["result"]["geographies"]["Unified School Districts"][0]["NAME"]
        if result["result"]["geographies"].get("Voting Districts"):
            censusGeoDict["votingDistrict"] =  result["result"]["geographies"]["Voting Districts"][0]["NAME"]
        if result["result"]["geographies"].get("116th Congressional Districts"):
            censusGeoDict["congressionalDistrict"] =  result["result"]["geographies"]["116th Congressional Districts"][0]["NAME"]
        if result["result"]["geographies"].get("Micropolitan Statistical Areas"):
            censusGeoDict["micropolitanStatArea"] =  result["result"]["geographies"]["Micropolitan Statistical Areas"][0]["NAME"]
        censusGeoDict["apiResponseTime"] = time.perf_counter() - startTime
        return(censusGeoDict) 
    except:
        # TODO send error message to server log and write dictionary to database
        censusGeoDict["errorMessage"] = f'Error parsing geocode data for lat/lon ({lat} {lon}). Url: {response.url}'
        censusGeoDict["responseCode"] = 400
        if verbose == True: print(censusGeoDict["errorMessage"])
        return(censusGeoDict) 
        
if __name__ == "__main__":
    location = [27.388502736025117, -80.3947602488546] # Right click on Google maps
    result = censusRevGeocode(location[0], location[1])
    pprint.pprint(result, sort_dicts=False)
    print(f'Time to download geoCode data: {result["apiResponseTime"]} seconds')
  



# Example of retrieving a lat/lon from an address. This is free vs. Google maps.
# url = f'https://geocoding.geo.census.gov/geocoder/locations/onelineaddress?address=4600+Silver+Hill+Rd%2C+Washington%2C+DC+20233&benchmark=2020&format=json'
