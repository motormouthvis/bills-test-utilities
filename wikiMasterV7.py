from time import perf_counter
from wikipediaApiV7 import *
from wikiDataAndVoyageV7 import *
# sys.path.append("C:\\Users\\bill\\Dropbox\\Programming\\Learning projects\\motormouth production")
from findCitiesV7 import *
from mmTestLocations import *
from censusGeocodeV7 import censusRevGeocode
from getCensusCrimeV7 import getUsCensusAndCrimeData
from walkScore import WalkAbilityScore


if __name__ == "__main__":
    verbose = False
    startTime = time.perf_counter()
    # TODO Fix Village of Indian Hill, OH 39.18792220801775, -84.32529905067847 Q34724014 no TOC
    # TODO Add political demographics to census module (i.e % Republican)
    
    # Right click on Google maps and paste here
    testLocations = [
        [[27.461326818822553, -80.30346292512938], ["Test"]],
        # [[34.066577991969304, -118.40925755999677], ["Mariner's Bow, Beverly Hills, CA"]],
        # [[40.66017990197812, -73.99014670586725], ["Jessica Zambelli"]],
    ]
    # Select which wiki topic you want a preview of
    tocItem = "history"

for location in testLocations:
    
    # This function returns a JSON response that contains:
    # census tract number, zip code, county, city and city center 
    # lat/lon (if in the city limits) # based on the provided lat/lon along with 
    # other items such as subdivision name, school district, ets.
    # Census tract number is normally smaller than a US zip code and is targeted
    # to be around 4,000 people
    # It also determines if you are within the city limits of any city - If cityName is none, you are not in the city limits.
    censusGeocoderesult = censusRevGeocode(location[0][0], location[0][1])
    
    # This function returns three things based on the provided census tract and zip code (You 
    # must provide the censusGeocodeResult dictionary when you call the function)
    #   - List of sentences with crime grade info (zip code based) suitable for the VUI
    #   - List of sentences with demographic info (census tract based) suitable for the VUI
    #   - A combined JSON record of the censusGeocode result dictionary, and the census 
    #     data dictionary for use in the website and phone apps
    crimeGradeVuiResponse, demographicVuiResponse, censusDataDict = getUsCensusAndCrimeData(
        censusGeocoderesult)
    
    
    # This code constructs a message for the VUI stating the city limits you are in, or the county
    # you are in if you are not within any city limits
    # Limitations:  This will only tell you if you in the city limits proper (white shaded area on
    # Google maps), but NOT if you are near a city.  If you are not in the city limits, you can state
    # the location is in a county (or non_US equivalent) instead.  Then you could use the FindCity class 
    # to get the two nearest cities.
    censusCityMsg = ""
    censusCountyMsg = ""
    censusCityFoundFlag = False
    censusCountyFoundFlag = False
    if censusDataDict["cityName"] != None:
        # pprint.pprint(censusDataDict, sort_dicts=False)
        censusCityFoundFlag = True
        censusCityMsg = f'You are within the city limits of {censusDataDict["cityName"]}, {censusDataDict["stateName"]}'
        
        # TODO add shorter test response message as well
        # TODO Add population if a city is found
        # Not currently used, but will be needed to get Wikipedia and Wikivoyage data for the city you are "in"
        # wikipediaUrl = f'{censusDataDict["cityName"].replace(" ", "_")},_{censusDataDict["stateName"]}'
        # wikiVoyageUrl = f'{censusDataDict["cityName"].replace(" ", "_")}_({censusDataDict["stateName"]})'
        # wikiVoyageAltUrl = f'{censusDataDict["cityName"].replace(" ", "_")})'
    
    # cityName is None, so you must not be in the city limits
    elif censusDataDict["countyName"] != None:
        censusCountyFoundFlag = True
        censusCountyMsg = f'You are in {censusDataDict["countyName"] if "county" in censusDataDict["countyName"].lower() else censusDataDict["countyName"] + "County"}, {censusDataDict["stateName"]}'

    # Gets the nearest city and nearest large (landmark) city data based on lat/lon.  
    # This will also return a wikiDataID that will be used for the wikiData API call
    city = FindCity()
    city.cityRadiusList = [80, 250, 500]
    # Radius used to find the nearest large (landmark) city for orienting VUI users
    # 80 miles is optimal for most situations unless its an extremely rural area
    city.deviceLat = location[0][0]
    city.deviceLon = location[0][1]
    city.getCities()
    
    # Get the WalkAbility, Transit and Bike scores
    walkScore = WalkAbilityScore()
    walkScore.get_walk_score(location[0][0], location[0][1])
    
    # Get the wikiData info using the wikiDataId.  This gets the wikipedia and
    # wikivoyage URLs needed for the wikipedia API call.  This also gets all
    # wikVoyage data.
    wikiDataInfo = GetWikiDataVoyageInfo()
    # Get info regarding the closest city (possibly change this to the city you are in)
    wikiDataInfo.getStructuredWikiDataInfo(
        city.response["smallCityWikiDataId"])
    # Print some of the wikiData and wikiVoyage info
    # TODO Optionally = pass the wikivoyage url to this program for the city you are in vs. the city you are near.

    if "title" in wikiDataInfo.data:
        cityPhrase = f'The nearest city center is {wikiDataInfo.data["title"]}'
    else:
        cityPhrase = ""
    if "inception" in wikiDataInfo.data and wikiDataInfo.data["inception"] != "unknown":
        inceptionPhrase = f' founded in {wikiDataInfo.data["inception"]}'
    else:
        inceptionPhrase = ""
    if "population" in wikiDataInfo.data:
        populationPhrase = f' with population {wikiDataInfo.data["population"]}'
    else:
        populationPhrase = ""
    if "elevation" in wikiDataInfo.data:
        if wikiDataInfo.data["elevation"] != "unknown":
            elevationPhrase = f', at an elevation of {wikiDataInfo.data["elevation"]} feet above mean sea level'
        else:
            elevationPhrase = ""
    else:
        elevationPhrase = ""

    print(f'\nWikidata summary info:')
    print(cityPhrase + inceptionPhrase +
          populationPhrase + elevationPhrase + ".")
    # pprint.pprint(wikiDataInfo.data, sort_dicts=False)
   
    

    # This section builds the VUI response telling the user where they are:
    #   - The city they are in (if they are in the city limits)
    #   - The city they are closest to
    #   - The nearest large (landmark) city
    if city.response["smallCityName"] != "unknown" and city.getCityResponseCode == 200:
        smallCityMsg = f'{city.response["smallCityDistance"]} miles {city.response["smallCityCardinalDir"]} of {city.response["smallCityName"]}, {city.response["smallCityState"]}, population {city.response["smallCityPopulation"]:,}'
        # print(f'WikiDataId = {city.response["smallCityWikiDataId"]}')
    else:
        smallCityMsg = ""

    if city.response["largeCityName"] != "unknown" and city.getCityResponseCode == 200:
        largeStateRef = city.response["largeCityState"] + \
            ", " if city.response["largeCityState"] != city.response["smallCityState"] else ""
        largeCityMsg = f'{city.response["largeCityDistance"]} miles {city.response["largeCityCardinalDir"]} of the center of {city.response["largeCityName"]}, {largeStateRef}population {city.response["largeCityPopulation"]:,}.'
        # largeCityMsg = f'{city.response["largeCityDistance"]} miles {city.response["largeCityCardinalDir"]} of {"the " + city.response["largeCityName"] + " city center" if city.response["largeCityDistance"] < 5 else city.response["largeCityName"] }, {largeStateRef}population {city.response["largeCityPopulation"]:,}.'
        # print(f'WikiDataId = {city.response["largeCityWikiDataId"]}')
    else:
        largeCityMsg = "not near any large cities"

    cityProximityMsg = ""
    if censusCountyFoundFlag == True and censusCityFoundFlag == False:
        cityProximityMsg = censusCountyMsg + ", " + \
            smallCityMsg + " and " + largeCityMsg
    if censusCountyFoundFlag == False and censusCityFoundFlag == True:
        cityProximityMsg = censusCityMsg + ", and " + largeCityMsg
    if censusCountyFoundFlag == False and censusCityFoundFlag == False:
        cityProximityMsg = "You are " + smallCityMsg + ", and " + largeCityMsg
    # TODO Add check for small and large city with same name, small or large city message not provided
    # TODO Test for Canada and Mexico and other countries that may not have counties
    # and where census does not work
    print(f'\nCity Proximity Message:')
    print(cityProximityMsg)




# ******************************************************************************************************


    try:
        # Prints crime and census data suitable for use in the VUI
        print()
        print(f'Crime grade')
        for sentence in crimeGradeVuiResponse:
            print(sentence, end="")

        # Prints Walk ability, bike and transit scores
        print()
        print()
        print(f'Walk/Transit/Bike Scores:')
        print(walkScore.data['walkScoreMessage'], end="")

        print()
        print()
        print(f'Demographics')
        for sentence in demographicVuiResponse:
            print(sentence, end="")
        # pprint.pprint(censusDataDict, sort_dicts=False)
    except:
        pass
    
    

    print(f'\nWikivoyage eat/drink/see/do info')
    if "eat" in wikiDataInfo.data:
        if len(wikiDataInfo.data["eat"]) > 0:
            print(f'\nWikivoyage - Places to eat:')
            for item in wikiDataInfo.data["eat"]:
                if "name" in item:
                    print(item["name"])
    if "drink" in wikiDataInfo.data:
        if len(wikiDataInfo.data["drink"]) > 0:
            print(f'\nWikivoyage - Places to drink:')
            for item in wikiDataInfo.data["drink"]:
                if "name" in item:
                    print(item["name"])
    if "see" in wikiDataInfo.data:
        if len(wikiDataInfo.data["see"]) > 0:
            print(f'\nWikivoyage - Places to see:')
            for item in wikiDataInfo.data["see"]:
                if "name" in item:
                    print(item["name"])
    if "do" in wikiDataInfo.data:
        if len(wikiDataInfo.data["do"]) > 0:
            print(f'\nWikivoyage - Things to do:')
            for item in wikiDataInfo.data["do"]:
                if "name" in item:
                    print(item["name"])

    # Get Wikipedia data using the Wikipedia url from the WikiData call
    # Returns Wikipedia data suitable for use with the VUI
    try:
        # Instantiate a class
        wikipediaInfo = GetWikipediaInfo()
        # Set the Wikipedia page name
        wikipediaInfo.setWikipediaPageName(wikiDataInfo.wikipedia_title)

        # Get the TOC for the above page name
        wikipediaInfo.getWikipediaToc()
        if wikipediaInfo.wikipediaResponseCode == 200:
            print()
            print('Wikipedia Table of Contents')
            print(wikipediaInfo.tocString)
        else:
            print()
            print('Wikipedia Table of Contents')
            print(f'No Wikipedia Table of Contents is available for {wikiDataInfo.wikipedia_title}\n')
    except:
        print()
        print('Wikipedia Table of Contents')
        print(f'No Wikipedia Table of Contents is available for {wikiDataInfo.wikipedia_title}\n')
        # Print the wiki Intro (usually the first paragraph before section one)
        # supply the maximum number of sentences you want

    try:
        # Get the Wikipedia Intro text (pass the max number of sentences to return)
        wikipediaInfo.getWikipediaIntro(10)
        print('Wikipedia Intro')
        print(wikipediaInfo.wikipediaIntroText)
    except:
        print(f'No Wikipedia Intro available')

    try:
        # Get the text for a specific section(s) (TOC item number)
        # Example usage - Determine the section number for the history of the town
        for item in wikipediaInfo.tocList:
            if tocItem.lower() in item["Descrip"].lower():
                sectionIndex = item["index"]
                tocItem = item["Descrip"]
                print(f'\n{tocItem.capitalize()} section index = {sectionIndex}')
                break
        # This function returns .finalText or .paratextList (a list of all sentences)
        wikipediaInfo.getWikipediaSectionPlainText(sectionIndex)
        
        # The .sentenceParser method reduces the number of sentences in the text response.
        # If you pass a paragraph, The parser returns # both a list of sentences and
        # a new paragraph with the proper number of sentences
        numSentences = 6
        print(
            f'\nWikipedia {tocItem} section: first {numSentences} sentences (max)')
        sentenceList, sentenceText = wikipediaInfo.sentenceParser(
            wikipediaInfo.sectionFinalText, numSentences)
        print(sentenceText)

        # Optional
        # print()
        # print('Wikipedia History - Full Text')
        # print(wikipediaInfo.finalText)
    except:
        print(f'\nNo wikipedia data is available for the {tocItem} section')

    
    print(f'\n\nTime to complete query: {time.perf_counter() - startTime}')
    # TODO add exception types in all modules
