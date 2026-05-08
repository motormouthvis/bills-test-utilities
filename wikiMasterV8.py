import time
from wikipediaApiV7 import *
from wikiDataAndVoyageV7 import *
# sys.path.append("C:\\Users\\bill\\Dropbox\\Programming\\Learning projects\\motormouth production")
from findCitiesV7 import *
from mmTestLocations import *
from censusGeocodeV7 import censusRevGeocode
from getCensusCrimeV7 import getUsCensusAndCrimeData
from walkScore import WalkAbilityScore
from fuzzywuzzy import fuzz


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
    
    # The below function returns a JSON response that contains:
    # census tract number, zip code, county, city and city center 
    # lat/lon (if in the city limits) # based on the provided lat/lon along with 
    # other items such as subdivision name, school district, ets.
    # Census tract number is normally smaller than a US zip code and is targeted
    # to be around 4,000 people
    censusGeocoderesult = censusRevGeocode(location[0][0], location[0][1])
    
    # The below function returns three things based on the provided census tract and zip code (You 
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
    # Get the WalkAbility, Transit and Bike scores
    walkScore = WalkAbilityScore()
    walkScore.get_walk_score(location[0][0], location[0][1])
    
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
        print(f'\nWikipedia Title Name: {wikiDataInfo.wikipedia_title}')
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
        sectionIndex = None
        for item in wikipediaInfo.tocList:
            if not isinstance(item, dict):
                continue
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
    
    
    
    print(f'Wiki Section Retrieval and Fuzzy Logic Test')
    speech_input = "highway"
    best_match = None
    best_ratio = 0

    for item in wikipediaInfo.tocList:
        if not isinstance(item, dict):
            continue
        # ratio = fuzz.ratio(speech_input.lower(), item["Descrip"].lower())  # Case-insensitive comparison
        ratio = max(fuzz.ratio(speech_input.lower(), item["Descrip"].lower()),
                         fuzz.partial_ratio(speech_input.lower(), item["Descrip"].lower()),
                         fuzz.token_sort_ratio(speech_input.lower(), item["Descrip"].lower()))
        print(f'Speech input word: {speech_input}, TOC Item: {item["Descrip"].lower()}, Ratio: {ratio}')
        
        if ratio > best_ratio:
            best_ratio = ratio
            best_match = item["Descrip"]
    
    tocItem = best_match
    if tocItem is None:
        print(f'\nNo valid Wikipedia TOC entries for fuzzy logic test.')
    else:
        try:
            # Get the text for a specific section(s) (TOC item number)
            # Example usage - Determine the section number for the history of the town
            sectionIndex = None
            for item in wikipediaInfo.tocList:
                if not isinstance(item, dict):
                    continue
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
            print(f'Speech input word: {speech_input}, best match: {best_match}, best ratio: {best_ratio}')
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








# ******************************************************************************************************
# JSON response from TOC request
# {
#     "parse": {
#         "title": "Fort Pierce, Florida",
#         "pageid": 109793,
#         "sections": [
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "History",
#                 "number": "1",
#                 "index": "1",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 7993,
#                 "anchor": "History",
#                 "linkAnchor": "History"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Lincoln Park",
#                 "number": "1.1",
#                 "index": "2",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 9081,
#                 "anchor": "Lincoln_Park",
#                 "linkAnchor": "Lincoln_Park"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "The Florida Highwaymen",
#                 "number": "1.2",
#                 "index": "3",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 9699,
#                 "anchor": "The_Florida_Highwaymen",
#                 "linkAnchor": "The_Florida_Highwaymen"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Geography",
#                 "number": "2",
#                 "index": "4",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 10869,
#                 "anchor": "Geography",
#                 "linkAnchor": "Geography"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Environment",
#                 "number": "2.1",
#                 "index": "5",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 11210,
#                 "anchor": "Environment",
#                 "linkAnchor": "Environment"
#             },
#             {
#                 "toclevel": 3,
#                 "level": "4",
#                 "line": "Shore Protection project",
#                 "number": "2.1.1",
#                 "index": "6",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 11228,
#                 "anchor": "Shore_Protection_project",
#                 "linkAnchor": "Shore_Protection_project"
#             },
#             {
#                 "toclevel": 3,
#                 "level": "4",
#                 "line": "Ecology",
#                 "number": "2.1.2",
#                 "index": "7",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 13103,
#                 "anchor": "Ecology",
#                 "linkAnchor": "Ecology"
#             },
#             {
#                 "toclevel": 3,
#                 "level": "4",
#                 "line": "Marina",
#                 "number": "2.1.3",
#                 "index": "8",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 13847,
#                 "anchor": "Marina",
#                 "linkAnchor": "Marina"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Climate",
#                 "number": "2.2",
#                 "index": "9",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 14700,
#                 "anchor": "Climate",
#                 "linkAnchor": "Climate"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Demographics",
#                 "number": "3",
#                 "index": "10",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 19214,
#                 "anchor": "Demographics",
#                 "linkAnchor": "Demographics"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Economy",
#                 "number": "4",
#                 "index": "11",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 24020,
#                 "anchor": "Economy",
#                 "linkAnchor": "Economy"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Port of Fort Pierce",
#                 "number": "4.1",
#                 "index": "12",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 24655,
#                 "anchor": "Port_of_Fort_Pierce",
#                 "linkAnchor": "Port_of_Fort_Pierce"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Arts and culture",
#                 "number": "5",
#                 "index": "13",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 26137,
#                 "anchor": "Arts_and_culture",
#                 "linkAnchor": "Arts_and_culture"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Tourist attractions",
#                 "number": "5.1",
#                 "index": "14",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 26158,
#                 "anchor": "Tourist_attractions",
#                 "linkAnchor": "Tourist_attractions"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Government",
#                 "number": "6",
#                 "index": "15",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 29020,
#                 "anchor": "Government",
#                 "linkAnchor": "Government"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Education",
#                 "number": "7",
#                 "index": "16",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 29327,
#                 "anchor": "Education",
#                 "linkAnchor": "Education"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Colleges and universities",
#                 "number": "7.1",
#                 "index": "17",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 29341,
#                 "anchor": "Colleges_and_universities",
#                 "linkAnchor": "Colleges_and_universities"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "High schools",
#                 "number": "7.2",
#                 "index": "18",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 29767,
#                 "anchor": "High_schools",
#                 "linkAnchor": "High_schools"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Middle schools",
#                 "number": "7.3",
#                 "index": "19",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 29998,
#                 "anchor": "Middle_schools",
#                 "linkAnchor": "Middle_schools"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Elementary schools",
#                 "number": "7.4",
#                 "index": "20",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 30324,
#                 "anchor": "Elementary_schools",
#                 "linkAnchor": "Elementary_schools"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Infrastructure",
#                 "number": "8",
#                 "index": "21",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 30657,
#                 "anchor": "Infrastructure",
#                 "linkAnchor": "Infrastructure"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Transportation",
#                 "number": "8.1",
#                 "index": "22",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 30676,
#                 "anchor": "Transportation",
#                 "linkAnchor": "Transportation"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "Notable people",
#                 "number": "9",
#                 "index": "23",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 36416,
#                 "anchor": "Notable_people",
#                 "linkAnchor": "Notable_people"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Actors",
#                 "number": "9.1",
#                 "index": "24",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 36596,
#                 "anchor": "Actors",
#                 "linkAnchor": "Actors"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Businesspeople",
#                 "number": "9.2",
#                 "index": "25",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 37057,
#                 "anchor": "Businesspeople",
#                 "linkAnchor": "Businesspeople"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Writers and artists",
#                 "number": "9.3",
#                 "index": "26",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 37240,
#                 "anchor": "Writers_and_artists",
#                 "linkAnchor": "Writers_and_artists"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Musicians",
#                 "number": "9.4",
#                 "index": "27",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 38094,
#                 "anchor": "Musicians",
#                 "linkAnchor": "Musicians"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Politicians",
#                 "number": "9.5",
#                 "index": "28",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 38207,
#                 "anchor": "Politicians",
#                 "linkAnchor": "Politicians"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Activists",
#                 "number": "9.6",
#                 "index": "29",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 39060,
#                 "anchor": "Activists",
#                 "linkAnchor": "Activists"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Sports",
#                 "number": "9.7",
#                 "index": "30",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 39178,
#                 "anchor": "Sports",
#                 "linkAnchor": "Sports"
#             },
#             {
#                 "toclevel": 2,
#                 "level": "3",
#                 "line": "Other",
#                 "number": "9.8",
#                 "index": "31",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 42730,
#                 "anchor": "Other",
#                 "linkAnchor": "Other"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "References",
#                 "number": "10",
#                 "index": "32",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 43901,
#                 "anchor": "References",
#                 "linkAnchor": "References"
#             },
#             {
#                 "toclevel": 1,
#                 "level": "2",
#                 "line": "External links",
#                 "number": "11",
#                 "index": "33",
#                 "fromtitle": "Fort_Pierce,_Florida",
#                 "byteoffset": 43934,
#                 "anchor": "External_links",
#                 "linkAnchor": "External_links"
#             }
#         ],
#         "showtoc": ""
#     }