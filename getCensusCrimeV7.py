import json
import pprint
import re
import time
from censusGeocodeV7 import censusRevGeocode
import requests
from crimeByZipV7 import getCrimeGradeByZip

# This function takes a dictionary from the censusRevGeocode function and returns crimeGradeVuiResponse, demographicVuiResponse, getUsCensusAndCrimeData
def getUsCensusAndCrimeData(censusGeoDict):
    censusDataDict = {}
    verbose = False
    crimeGradeVuiResponse = [f'No crime grade is available for this zip code.']
    demographicVuiResponse = [f'No census data is available for this area']
    
    # censusRevGeocode is called prior to this function
    # It takes lat/lon and returns a JSON record with 
    # census tract number, zip code, state
    # county, sometimes a city name (you must be in the city limits),
    # and more.
    
    # This should never happen, but verify error is not True
    if censusGeoDict["error"] == True:
        # TODO send message to server log
        censusGeoDict["error message"] = f'getUsCensusAndCrimeData function called with invalid parameter error == True'
        if verbose == True:
            print(f'{censusGeoDict["error message"]}')
        censusDataDict |= censusGeoDict
        return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)
    try:
        # We need these three items to call the Census API
        tract = censusGeoDict["censusTractNum"]
        state = censusGeoDict["stateNum"]
        county = censusGeoDict["countyNum"]
    except:
        # The censusGeoDict does not have the information we need
        # TODO send message to server log
        censusGeoDict["error"] = True
        censusGeoDict["error message"] = f'unknown error getting census tract for lat/lon'
        if verbose == True:
            print(f'{censusGeoDict["error message"]}')
        censusDataDict |= censusGeoDict
        return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)
    if verbose == True:
        print(f'censusGeoDict passed to getUsCensusAndCrimeData function:')
        pprint.pprint(censusGeoDict, sort_dicts=False)

    # Note:  We are currently using 2020 ACS 5 Year data.  If we change this,
    # all the row numbers will probably be changed. 5 yr data is more detailed than 1 year data
    # which is why we  use it.  See the spreadsheet for all row descriptions.
    # https://docs.google.com/spreadsheets/d/13uJ_v7GTapZltfvN5q6-ajq_UaB8tvffjteKRZawzJw/edit?usp=sharing
    # For DP codes:  https://api.census.gov/data/2020/acs/acs5/profile/variables.json
    year = '2020'
    dsource = 'acs'
    dname = 'acs5'
    api_key = "857cca98b13c9701d74e74d6745831ded722b339"
    
    # The first item in each list is the key "required" by the API,
    # the second item is the MotorMouth defined description.
    # Note:  You can add items to this list as desired
    censusDataRequested = [["NAME,", "Census Tract Name"],
                           ["DP02_0115E,", "Speaks English Less Than Very Well"],
                           ["DP03_0088E,", "Per Capita Income(dollars)"],
                           ["DP03_0063E,", "Average Household Income"],
                           ["DP04_0001E,", "Total Number of Homes"],
                           ["DP04_0046E,", "Homes Occupied by Owner"],
                           ["DP04_0089E,",
                               "Median Home Price (Owner Occupied)"],
                           ["DP04_0134E,", "Median rental price"],
                           ["DP05_0001E,", "Total Population"],
                           ["DP05_0018E,", "Median Age"],
                           ["DP03_0002PE,", "Percentage total population employed"],
                           ["DP02_0090PE,", "Born in the United States"],
                           ["DP02_0068PE,",
                               "Bachelors Degree or Higher(25+ years old)"],
                           ["DP02_0067PE,",
                               "High school graduate (includes equivalency) (25+ years old)"],
                           ["DP05_0002PE,", "Male"],
                           ["DP05_0003PE,", "Female"],
                           ["DP05_0037PE,", "White"],
                           ["DP05_0038PE,", "African American"],
                           ["DP05_0039PE,", "Native American"],
                           ["DP05_0044PE,", "Asian"],
                           ["DP05_0052PE,", "Native Hawaiian"],
                           ["DP05_0057PE,", "Other Race"],
                           ["DP05_0071PE", "Hispanic"]
                           ]
    # Note: The DP number of the last item cannot have a comma due to 
    # how we build the API request

    # Note:  You are limited to 50 requests per API call, so this allows
    # multiple rows to be added if required
    rows = [censusDataRequested]
    for row in rows:
        get_argument = ""
        # Build the api request for each row using the Census data row names    
        for item in row:
            get_argument = get_argument + item[0]
        base_url = f'https://api.census.gov/data/{year}/{dsource}/{dname}'
        data_url = f'{base_url}/profile?get={get_argument}&for=tract:{tract}&in=state:{state} county:{county}&key={api_key}'

        try:
            response = requests.get(data_url)
            if verbose == True:
                print(f'url sent to Census server: {data_url}')
            if response.status_code != 200:
                # TODO write error to log
                censusGeoDict["error"] = True
                censusGeoDict[
                    "error message"] = f'Error - Census API status code: {response.status_code} for {response.url}'
                if verbose == True:
                    print(f'{censusGeoDict["error message"]}')
                censusDataDict |= censusGeoDict
                return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)
            response = response.json()
            # Census API JSON response
            if verbose == True:
                print(f'Census API JSON response:  {json.dumps(response, indent=4)}')
        except:
            # TODO write error to log
            censusGeoDict["error"] = True
            censusGeoDict["error message"] = f'Unknown error from Census API - {data_url}'
            if verbose == True:
                print(f'{censusGeoDict["error message"]}')
            censusDataDict |= censusGeoDict
            return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)


        # This function replaces invalid census values with float "0.0" or "not available"
        def fixCensusValues(responseVal):
            # These minus values like -666666666 indicate the census data is invalid, replace with float 0.0
            # TODO Rewrite this to be faster?
            for value in ("-6666", "-9999", "-2222", "-5555", "-3333", "null"):
                if value in responseVal:
                    responseVal = "0.0"
            #  These four terms indicate the census data is invalid
            for value in ("Varies", "*", "c", "null"):
                if value == responseVal:
                    responseVal = "not available"
            return(responseVal)

        # Create a dictionary  with the record name as the key
        try:
            # Create an iterable map object of MotorMouth defined labels from the
            # row list. These will replace the cryptic Census row numbers
            # (e.g. DP05_0018E) with better labels.
            keys = map(lambda item: item[1], row)
            # Create a iterable map object of corrected values from
            # the Census API JSON response
            values = map(fixCensusValues, response[1])
            # Combine the keys/value pairs into a dictionary
            censusDataDict = censusDataDict | dict(zip(keys, values))
        except:
            # TODO write error to server log
            censusGeoDict["error"] = True
            censusGeoDict[
                "error message"] = f'Unknown error when building Census dictionary response- {data_url}'
            if verbose == True:
                print(f'{censusGeoDict["error message"]}')
            censusDataDict |= censusGeoDict
            return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)

    # Combine the input dictionary from the census geocode and the census
    # data dictionary into one dictionary for convenience.  This should have
    # all the data needed by the phone, website and VUI to form a response.
    censusDataDict = censusGeoDict | censusDataDict
    if verbose == True:
        print(f'\nData from area: {censusDataDict["Census Tract Name"]}')
    if verbose == True:
        print(f'Combined census and geocode dictionary:')
        pprint.pprint(censusDataDict, sort_dicts=False)

    # Build a response for the VUI for the crime grade and the census data
    # Return both a paragraph, and a list of sentences for each so the VUI 
    # can decide how many sentences to speak
    try:
        # Only speak the largest two or three % race values with the VUI
        if int(censusDataDict["Total Population"]) > 0:
            raceVuiResponse = [["White", censusDataDict["White"]],
                               ["African American", censusDataDict["African American"]],
                               ["Native American", censusDataDict["Native American"]],
                               ["Asian", censusDataDict["Asian"]],
                               ["Native Hawaiian", censusDataDict["Native Hawaiian"]]]
            sortedVuiResponse = sorted(
                raceVuiResponse, key=lambda x: float(x[1]), reverse=True)
            # Get the top three race groups (excluding "other" and "hispanic" - hispanic is considered
            # an overlay by the Census Bureau, not a race)
            # More than three would be too many to read aloud
            topThree = sortedVuiResponse[:3]
            hispanic = censusDataDict["Hispanic"]
            # If the third largest race is less than 5%, don't speak aloud on the VUI, TMI
            if float(topThree[2][1]) > 5:
                numberThree = f'{topThree[2][1]}% are {topThree[2][0]}, '
            else:
                numberThree = ""

            # Change census dollar values to comma delimited, with 0 significant digits, and a dollar sign prefix
            # so it will look better on the website and phone apps
            # It may also improve how the VUI speaks the info.
            if censusDataDict["Median Home Price (Owner Occupied)"] != "0.0":
                medianHomePrice = f'${"{:,.0f}".format(float(censusDataDict["Median Home Price (Owner Occupied)"]))}'
            else:
                medianHomePrice = "not available"
            if censusDataDict["Per Capita Income(dollars)"] != "0.0":
                perCapitaIncome = f'${"{:,.0f}".format(float(censusDataDict["Per Capita Income(dollars)"]))}'
            else:
                perCapitaIncome = "not available"
            if (censusDataDict["Average Household Income"]) != "0.0":
                avgHouseholdIncome = f'${"{:,.0f}".format(float(censusDataDict["Average Household Income"]))}'
            else:
                avgHouseholdIncome = "not available"
            if (censusDataDict["Median rental price"]) != "0.0":
                medianRentalPrice = f'${"{:,.0f}".format(float(censusDataDict["Median rental price"]))}'
            else:
                medianRentalPrice = "not available"
            if (censusDataDict["countySubdivision"]) != "null":
                countySubdivision = censusDataDict["countySubdivision"] + " "
            else:
                countySubdivision = ""

            # TODO make a function to determine the best neighborhood name
            # TODO 46.94632720767331, -107.07334563309844 shows Census Tract1 -
            # this does not seem correct, but it actually happens in many places
            
            # Create a list of sentences for the VUI
            percent_not_fluent_English = round(int(censusDataDict["Speaks English Less Than Very Well"]) / int(censusDataDict["Total Population"]) *100, 0)
            if percent_not_fluent_English > 33:
                non_english_speakers = f'Only {100-percent_not_fluent_English}% of the population speaks fluent English.'
            elif percent_not_fluent_English > 10 and percent_not_fluent_English <= 33:
                non_english_speakers = f'{percent_not_fluent_English}% of the population does not speak fluent English.'
            else:
                non_english_speakers = f'Only {percent_not_fluent_English}% of the population does not speak fluent English.'
            demographicVuiResponse = [
                f'For the {countySubdivision}neighborhood in which you are currently located, US Census demographics show {censusDataDict["Total Population"]} residents of which {censusDataDict["Born in the United States"]}% were born in the United States, {topThree[0][1]}% are {topThree[0][0]}, {topThree[1][1]}% are {topThree[1][0]}, {numberThree}and {hispanic}% of the population identifies as Hispanic. ',
                f'{non_english_speakers}',
                f'The median age is {censusDataDict["Median Age"]} with {censusDataDict["Female"]}% being female. {censusDataDict["High school graduate (includes equivalency) (25+ years old)"]}% graduated from high school while {censusDataDict["Bachelors Degree or Higher(25+ years old)"]}% attained a bachelors degree or higher. ',
                f'{censusDataDict["Percentage total population employed"]}% are employed with a per capita income of {perCapitaIncome}, and an average household income of {avgHouseholdIncome}. ',
                f'The median home price is {medianHomePrice} and {censusDataDict["Homes Occupied by Owner"]} of the {censusDataDict["Total Number of Homes"]} homes are occupied by owner. The median rental price is {medianRentalPrice}.',
            ]
        else:
            demographicVuiResponse = [
                f'No demographic data is available for this area.']
    except Exception as e:
        demographicVuiResponse = [
            f'Error: {e} No demographic data is available for this area.']

    # Get crime grade for both violent and property crime from database based on zip code
    propertyCrimeGrade, violentCrimeGrade = "not available", "not available"
    if censusDataDict["zipCode"] != "null":
        try:
            crimeGradeRecord = getCrimeGradeByZip(censusDataDict["zipCode"])
            # Replace crime grade "D-" with "D minus", etc. so VUI can read aloud
            replacementCharacterStrings = [[r'\+', ' plus'], [r'\-', ' minus']]
            for charString in replacementCharacterStrings:
                propertyCrimeGrade = re.sub(
                    charString[0], charString[1], crimeGradeRecord[0]["Summary_Property_PerThousand_Grade"])
                violentCrimeGrade = re.sub(
                    charString[0], charString[1], crimeGradeRecord[0]["Summary_Violent_PerThousand_Grade"])
            # Create a list of sentences for the VUI
            crimeGradeVuiResponse = [
                f'The crime grade for this entire zip code {censusDataDict["zipCode"]} is "{propertyCrimeGrade}" for property crime, and "{violentCrimeGrade}" for violent crime, however, crime varies by neighborhood.']
        except:
            # TODO send message to server log
            crimeGradeVuiResponse = [
                f'No crime grade is available for zip code {censusDataDict["zipCode"]}']
    else:
        crimeGradeVuiResponse = [
            f'No crime grade is available for this area.']

    return(crimeGradeVuiResponse, demographicVuiResponse, censusDataDict)

if __name__ == "__main__":
    
    location = [25.77369438818675, -80.23198863527952]
    censusGeocoderesult = censusRevGeocode(location[0], location[1])

    start_time = time.time()
    crimeGradeVuiResponse, demographicVuiResponse, getUsCensusAndCrimeData = getUsCensusAndCrimeData(
        censusGeocoderesult)
    duration = time.time() - start_time
    print(f'Time to get census and crime data: {duration} seconds')
    print(crimeGradeVuiResponse)
    print(demographicVuiResponse)
    pprint.pprint(getUsCensusAndCrimeData, sort_dicts=False)




















# Dictionary Output Sample Structure
# {'Census Tract Name': 'Census Tract 3813, St. Lucie County, Florida',
#  'Per Capita Income(dollars)': '55059',
#  'Average Household Income': '94056',
#  'Total Number of Homes': '4183',
#  'Homes Occupied by Owner': '1588',
#  'Median Home Price (Owner Occupied)': '279000',
#  'Median rental price': '1169',
#  'Total Population': '3805',
#  'Median Age': '63.3',
#  'Percentage total population employed': '40.8',
#  'Born in the United States': '88.6',
#  'Bachelors Degree or Higher(25+ years old)': '47.0',
#  'Male': '45.9',
#  'Female': '54.1',
#  'White': '95.0',
#  'African American': '0.6',
#  'Native American': '2.5',
#  'Asian': '0.5',
#  'Native Hawaiian': '0.0',
#  'Other Race': '1.3',
#  'Hispanic': '3.4'}


# Documentation references
# The DP numbers are row numbers that change for different annual tables.
# The E on the end is for "estimate", the PE is for "percentage estimate"
# You are limited to 50 rows per API call
# Note, no comma allowed after last "DP" item in list, ie. "DP03_0002E",
#  but comma require for all others ie. "DP05_0001E,"
# DP coding tips:           https://www.census.gov/data/developers/data-sets/acs-1year/notes-on-acs-api-variable-formats.html
# List of all DP values:    https://api.census.gov/data/2020/acs/acs5/profile/variables.json
# Table ID's explained:     https://www.census.gov/programs-surveys/acs/data/data-tables/table-ids-explained.html
# Geographies supported :   https://api.census.gov/data/2020/acs/acs5/geography.html
# Geographic info:          https://pitt.libguides.com/uscensus/understandinggeography
# Census Geocode info:      https://www.census.gov/programs-surveys/geography/technical-documentation/complete-technical-documentation/census-geocoder.html
# Area is in square meters. squareMeter * 0.00000038610215855 = squareMile
# GeoIDs                    https://www.census.gov/programs-surveys/geography/guidance/geo-identifiers.html
# Return Values             -666666666, -999999999, -222222222, -333333333, -555555555 or null indicates invalid or no data
# Return value details      https://www.census.gov/data/developers/data-sets/acs-1year/notes-on-acs-estimate-and-annotation-values.html
# censusGeocoder            https://www2.census.gov/geo/pdfs/maps-data/data/Census_Geocoder_User_Guide.pdf
# TODO Fix ["", "DP04_0080PE", "Homes Occupied by Owner", "%"] - provide total number, not percentage- Note, this is actually
#   a Census Data problem.  I verivied this on the Census Slack channel

# Add this if we ever want zip code data also
# zip_data_url = f'https://api.census.gov/data/2020/acs/acs5/profile?get=NAME,DP02_0001E&for=zip%20code%20tabulation%20area:77494'
