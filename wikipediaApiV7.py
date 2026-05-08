import pprint
import nltk.data
import re
import sys
import unicodedata
from pyparsing import nums
import requests
import json
from requests import api
from bs4 import BeautifulSoup
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
debug = False

# Wikimedia rejects requests whose User-Agent resembles a generic crawler.
WIKIPEDIA_REQUEST_HEADERS = {
    "User-Agent": (
        "MotormouthLocalWiki/1.0 "
        "(Wikipedia/MediaWiki script; Python; +https://www.mediawiki.org/wiki/API:Etiquette)"
    ),
}

# This class provides Wikipedia TOC (table of contents), Intro Text, and 
# Section Text in a "clean" format that the VUI can read aloud.
# You must supply a Wikipedia page name in the following format:  e.g. "Fort_Pierce,_Florida"
# We normally get the Wikipedia page name from the WikiData program, but we could
# construct it from any city name (Note: there are consistency issue e.g. "Miami" works
# but "Miami,_Florida" does not)
# It also provides a sentence parser function that breaks a paragraph up into sentences.  This might 
# be useful to the VUI if we only want to read 3 of the 10 sentences in a paragraph for example

class GetWikipediaInfo:
    def __init__(self):
        self.verbose = False
        # These regex expressions clean up the text items in Wikipedia that
        # the VUI could not pronounce, or are not appropriate
        # e.g. replace "(−41.7 °C)" with "", or "(300.4 km2)" with ""
        # Note: For metric support, these will have to be modified as we get
        # rid of kilometers and celsius references
        # Note:  changed these to "raw" stings on 1-9-2025 as Python 3.13 started giving warning about invalid escape sequence "\""
        self.replacementCharacterStrings = [
            [r'\(\w{1}\)', ''], 
            [r'\(.{1,12}km\)', ''], 
            [r'\(\d{1,4}.{1,7}\sm\)', ''], 
            [r'\[edit\]', ''], 
            [r'\sel\.', ' elevation'], 
            [r'\(.{1,12}km2\)', ''], 
            [r'\[\d{0,3}\]', ''], 
            [r'\(\d{0,2}\)', ''],
            [r'\d{1,3}°.{0,80}-\d{1,3}\.\d{1,7}.{1}', ''], 
            [r'Preview of references(.|\n)*', ''], 
            [r'\(.{1,8}°C\)', ''], 
            [r'\(.{1,12}mm\)', ''], 
            [r'\s,', ','], 
            [r'(\s|\n){2,200}', " "],
            [r'\(CDP\)\s', " "],
            [r'\(.*\(listen\).*\)\s', ''],
            # removes pronunciation helpers e.g. (US: OH-kee-CHOH-bee) 
            [r'\(.*[A-Z]+[-]{1}[a-z]+.*\)\s', ''], 
            ]
        self.pageTitle = ""
        self.pageId = ""
        self.wikiPageName = ""
        self.wikiVoyagePageName = ""
        self.wikipediaIntroText = ""
        self.error = True
        self.errorMessage = ""
        self.wikipediaResponseCode = 400

    # Sets the Wikipedia URL for multiple method calls
    # Returns wikipediaResponseCode 200=OK, 204=Data not found, 
    # 400=bad API request/response/unknown error
    def setWikipediaPageName(self, wikiPageName):
        self.wikiPageName = wikiPageName
        # Example:  "Fort_Pierce,_Florida"
        return

   
    # This function gets the TOC for the given Wikipedia page (prop=sections)
    # It returns a formatted text block containing the entire TOC, and a 
    # list of all individual TOC items
    def getWikipediaToc(self):
        self.tocString = ""     # This is a formatted list of the TOC
        self.tocList = []       # This is a list of TOC items in a dictionary
        self.apiResponseCode = 400
        self.apiResponse = ""
        
        params = {
            "action" : "parse",
            "prop" : "sections",
            "format" : "json",
            "page" : self.wikiPageName      
            # get wikiPageName From getWikiData function 
        }
        try:
            # Get the wiki TOC using prop=sections
            url = f'https://en.wikipedia.org/w/api.php?'
            self.api_response = requests.request(
                "GET", url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS
            )
            self.apiResponseCode = self.api_response.status_code
            if self.apiResponseCode != 200:
                # Bad response from API call
                self.tocString = f'No Wikipedia TOC available for this location'
                self.tocList.append(self.tocString)
                self.error = True
                self.errorMessage = f'error retrieving {self.wikiPageName} Wikipedia TOC with response code {self.apiResponseCode}'
                self.wikipediaResponseCode = 400
                # TODO send error to server log
                return
        except:
            # API call did not work
            self.tocString = f'API call to Wikipedia failed due to unknown reasons. Check url {url}, and params {params}'
            self.tocList.append(self.tocString)
            self.error = True
            self.errorMessage = self.tocString
            self.wikipediaResponseCode = 400
            # TODO send error to server log
            return
        
        
        # API response = 200.  Now check to see if it contains valid TOC data
        self.wikipediaResponseCode = 200
        result = self.api_response.json()
        self.error = False
        if self.verbose == True:
            print(f'JSON response from TOC request')    
            print(json.dumps(result, indent=4))
        # TODO possibly add error handling and key checks
        # This code creates a list of a subset of TOC items and a formatted TOC string for display purposes
        try:
            self.pageTitle = result['parse']['title']
            self.pageId = result['parse']['pageid']
            self.tocList =[]
            self.tocString =""
            for tocItem in (result['parse']['sections']):
                # Return a list of all items with TOC number, Name, and Index (Index will be used to get section text), and TOC level
                self.tocList.append({"LineNum" : tocItem["number"], "Descrip" : tocItem["line"], "index" : tocItem["index"], "toclevel" : tocItem["toclevel"]})
                # Also return a formatted string for display
                self.tocString = self.tocString + (f'{"     " if tocItem["number"].__contains__(".") else ""}{tocItem["number"]}.  Title: {tocItem["line"]}  (Index: {tocItem["index"]})') + "\n"
        except:
            self.tocString = f'error retrieving {self.wikiPageName } Wikipedia TOC.  Check city/pageName spelling'
            self.tocList.append(self.tocString)
            self.error = True
            self.errorMessage = self.tocString
            # No TOC found, return error code 204
            self.wikipediaResponseCode = 204


    # This function get the intro text for a Wikipedia article.  It's usually clean and suitable for 
    # the VUI to read aloud, but to be careful, I do a find and replace with 
    # replacementCharacterString List.  You can also specify the number of sentences returned for each section.

    # These params work great!  Gets pure readable text for the intro.
    # I believe exintro gets the introduction (Return only content before the first section)
    #  - any value other than false is true
    #  - Boolean parameters work like HTML checkboxes: if the parameter is specified, 
    # regardless of value, it is considered true. 
    # For a false value, omit the parameter entirely.
    # Query:  https://en.wikivoyage.org/w/api.php?action=help&modules=query
    # Extracts:  https://en.wikivoyage.org/w/api.php?action=help&modules=query%2Bextracts
    # Info from https://stackoverflow.com/questions/24806962/get-an-article-summary-from-the-mediawiki-api
    
    def getWikipediaIntro(self, numSentences=100):
        self.verbose = False
        
        params = {  
            "action" : "query",
            "prop" : "extracts",
            "format" : "json",
            "exintro" : "",
            "explaintext" : "",
            "exsentences" : numSentences,
            "titles" : self.wikiPageName,
        }
        url = "https://en.wikipedia.org/w/api.php"
        api_response = requests.request(
            "GET", url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS
        )
        apiResponseCode = api_response.status_code
        if self.verbose == True:
            print(f"wiki intro response code: {apiResponseCode}")
        if apiResponseCode != 200:
            self.wikipediaIntroText = f'No Wikipedia Intro text is available'
            self.error = True
            self.errorMessage = f'Error from WikiPedia Intro text request:  url: {url}, params: {params}, API response code: {apiResponseCode}'
            self.wikipediaResponseCode = 400
            # TODO send error to server log

        else:
            # Response code = 200
            if self.verbose == True:
                print(f'JSON response from Wikipedia Intro request')
                print(json.dumps(api_response.json(), indent=4))
            try:
                responseDict = json.loads(api_response.text)
                # Need the pageID to get the proper field in the JSON response.
                # This can be passed to the function, or it can be retrieved using the following statement:
                pageId = next(iter(responseDict["query"]["pages"]))
                # Page ID = -1 for invalid city name, I believe.
                if pageId == "-1":
                    self.wikipediaIntroText = f'{self.wikiPageName} is is not a valid Wikipedia page'
                result = api_response.json()['query']['pages'][str(pageId)]['extract']
                if result == "":
                    self.wikipediaIntroText = f'The {self.wikiPageName} Wikipedia page does not have an intro section'
            except:
                self.wikipediaIntroText = f'No Wikipedia Intro text is available'
                self.error = True
                self.errorMessage = f'Unable to parse JSON response. url: {url}, params: {params}, API response code: {apiResponseCode}'
                self.wikipediaResponseCode = 400
                # TODO send error to server log
                # TODO Make sure this return statement is a mistake
                # return(f'Unable to parse JSON response from {self.wikiPageName} WikiPedia intro request')

        try:
            soup = BeautifulSoup(result, features="lxml")
            cleanText = self.replaceCharStrings(soup.get_text(), self.replacementCharacterStrings)
            # Get rid of weird characters like hard space '\xa0' 
            cleanText = unicodedata.normalize("NFKD",cleanText)
            self.wikipediaIntroText = cleanText
        except:
            self.wikipediaIntroText = f'No Wikipedia Intro text is available'
            self.error = True
            self.errorMessage = f'Unable clean Into text with Beautiful Soup. url: {url}, params: {params}, API response code: {apiResponseCode}'
            self.wikipediaResponseCode = 400
            # TODO send error to server log



    # Function retrieves and processes text from Wikipedia sections using API.  
    # Must supply a TOC index as well as pageName.  It returns plain readable text,
    # "finalText" and also a list of paragraphs "paraTextList".
    # Note: Biggest limitation if that it sometimes returns improperly formatted text 
    # for certain types of sections such as a list of references.  
    # Not super important as we probably won't read those aloud
    def getWikipediaSectionPlainText(self, index):
        self.sectionFinalText = ""
        self.sectionParaList = []
        self.noParagraphFoundFlag = True


        # Note:  Also tried prop=categories, links, templates and sections(sections in the section)
        # Note:  wikitext python module give notably different results
        # Extracts:  https://en.wikivoyage.org/w/api.php?action=help&modules=query%2Bextracts
        # Got info from https://stackoverflow.com/questions/24806962/get-an-article-summary-from-the-mediawiki-api
        params = {  
            "action" : "parse",
            "prop" : "text",
            "format" : "json",
            "page" : self.wikiPageName,
            "section" : index,
            "contentformat" : "text/plain",
            "sectionpreview" : "",
            "preview" : ""
        }
        url = "https://en.wikipedia.org/w/api.php"
        api_response = requests.request(
            "GET", url, params=params, headers=WIKIPEDIA_REQUEST_HEADERS
        )
        if self.verbose == True:
            print(api_response.url)
        apiResponseCode = api_response.status_code
        if apiResponseCode != 200:
            self.sectionFinalText = f'No Wikipedia data is available for this topic'
            self.sectionParaList.append(self.sectionFinalText)
            self.error = True
            self.errorMessage = f'Error from WikiPedia Section Request:  API code: {apiResponseCode}, url: {url}, params: {params}, API response code: {apiResponseCode}'
            self.wikipediaResponseCode = 400
        else:
            # API response = 200
            if self.verbose == True:
                print(f'Received JSON response from Section request')
                print(json.dumps(api_response.json(), indent=4))
            try:
                result = api_response.json()['parse']['text']['*']
            except:
                responseDict = json.loads(api_response.text)
                if "error" in responseDict:
                    self.sectionFinalText = f'No Wikipedia data is available for this topic'
                    self.sectionParaList.append(self.sectionFinalText)
                    self.error = True
                    self.errorMessage = f'Response error:  {responseDict["error"]["info"]}'
                    self.wikipediaResponseCode = 400
                else:
                    self.sectionFinalText = f'No Wikipedia data is available for this topic'
                    self.sectionParaList.append(self.sectionFinalText)
                    self.error = True
                    self.errorMessage = f'Unknown error for {self.wikiPageName} section search'
                    self.wikipediaResponseCode = 400
        try:
            # Clean the wiki text so the VUI can read it
            soup = BeautifulSoup(result, features="lxml")
            text = ""
            cleanText = ""
            self.noParagraphFoundFlag = 0
            # Remove all tables, etc. for VUI.  Keep paragraph text only.
            for paragraph in soup.find_all('p'):
                soupText = str(paragraph.text)
                cleanText = self.replaceCharStrings(soupText, self.replacementCharacterStrings)
                # Get rid of weird characters like hard space '\xa0' 
                cleanText = unicodedata.normalize("NFKD",cleanText)
                self.sectionParaList.append(str(cleanText))
                self.sectionFinalText = self.sectionFinalText + cleanText
            # If no paragraphs are available for the VUI to read, get the HTML data
            # parse it, and set a warning flag for the VUI. 
            if len(self.sectionParaList) == 0:
            # TODO Add section here to look for other tags to make more readable???
            # TODO Use NLTK function to parse sentences and only read the first 3-4 sentences
                text = soup.get_text()
                cleanText = self.replaceCharStrings(text, self.replacementCharacterStrings)
                cleanText = unicodedata.normalize("NFKD",cleanText)
                self.noParagraphFoundFlag = True
                # This is a warning to the VUI that the text might be hard to read
                self.sectionFinalText = cleanText
                print(f'Clean intro text is:  {cleanText}')
                self.sectionParaList.append(str(cleanText))
            else:
                self.noParagraphFoundFlag = False
            return
        
        # TODO Add additional text processing here such as remove parens, stray brackets or 
        # TODO Fix problem with TOC 3, 3.1, 3.2, where a request for 3, returns TOC and 3.1, 3.2, etc. 
        # TODO  Possibly compare 3 and 3.1 to see if first 100 characters are the same.  If so , make 3 blank text
        except:
            # Unable to clean/parse wiki text
            self.sectionFinalText = f'No Wikipedia data is available for this topic'
            self.sectionParaList.append(self.sectionFinalText)
            self.error = True
            self.errorMessage = f'Unable to parse {self.wikiPageName} Wikipedia section data'
            self.wikipediaResponseCode = 400
            


    # Cleans up wiki text by replace/removing unwanted strings with readable text
    def replaceCharStrings(self, textToScan, replacementCharacterStrings):
        for charString in self.replacementCharacterStrings:
            textToScan = re.sub(charString[0], charString[1], textToScan)
        return(textToScan)
    
    # This functions uses natural language processing to split sentences into a list
    # and return the desired number of sentences.
    # This could be used by the VUI to provide a shorter response fo other text if desired
    # NOTE:  If you have a problem getting NLTK to work, run Python in a terminal then issue two commands:  >>> import nltk, then >>> nltk.download('punkt_tab')
    def sentenceParser(self, textToParse, sentenceCount):
        sentenceList = []
        sentenceText = ""
        try:
            tokenizer = nltk.data.load('tokenizers/punkt/english.pickle')
            sentenceList = tokenizer.tokenize(textToParse)
            sentenceCount = sentenceCount if len(sentenceList) >= sentenceCount else len(sentenceList)
            for sentence in sentenceList:
                sentenceList.append(sentence)
                sentenceText = sentenceText + " " + sentence
                sentenceCount -= 1
                if sentenceCount == 0:
                    break
        except:
            # If NLTK can't parse text, just return the text as is
            # This wil most likely never happen
            sentenceText = textToParse
            sentenceList.append(textToParse)
        return(sentenceList, sentenceText)




if __name__ == "__main__":  
    wikipediaPageName = "Fort Pierce, Florida"
    
    # Instantiate a class
    wikipediaInfo = GetWikipediaInfo()
    
    # Set the Wikipedia page name
    wikipediaInfo.setWikipediaPageName(wikipediaPageName)

    # Get the TOC for the above page name
    wikipediaInfo.getWikipediaToc()
    if wikipediaInfo.wikipediaResponseCode == 200:
        if debug == True:
            print("********************************** Wikipedia toc.list **********************************")
            pprint.pprint(wikipediaInfo.tocList, sort_dicts=False)
        print(wikipediaInfo.tocString)
    else: print(f'Wikipedia Table of contents is not available for this topic')

    # Get the Wikipedia Intro
    wikipediaInfo.getWikipediaIntro(10)
    if wikipediaInfo.wikipediaResponseCode == 200:
        print('Wikipedia Intro')
        print(wikipediaInfo.wikipediaIntroText)
    else: print(f'Wikipedia introduction is not available for this topic')
    
    # Search for a TOC entry that contains the following text
    tocItem = "history"
    if wikipediaInfo.wikipediaResponseCode == 200:
        for item in wikipediaInfo.tocList:
            if tocItem.lower() in item["Descrip"].lower():
                sectionIndex = item["index"]
                tocItem = item["Descrip"]
                print(f'\n{tocItem.capitalize()} section index = {sectionIndex}')
                break
        # Get the wiki text for that section
        wikipediaInfo.getWikipediaSectionPlainText(sectionIndex)
        print(wikipediaInfo.sectionFinalText)
            
    else: print(f'Wikipedia information is not available for this topic')
    
    # Truncate the number of sentences in the paragraph and remove <CR>
    # This could be used for printing out the results or by the VUI
    numSentences = 6
    if wikipediaInfo.wikipediaResponseCode == 200:
        sentenceList, sentenceText = wikipediaInfo.sentenceParser(
            wikipediaInfo.sectionFinalText, numSentences)
        print(sentenceText)
    else: print(f'Wikipedia information is not available for this topic')






















# Note:  These regexes are particular to cleaning up wikipedia section "paragraph" text
#        But probably work on the intro section as well.
#
# *** Replacement regex explainations ***
#        Must replace strings in this order
# "(A)"             with "",            ['\(\w{1}\)', '']
# "(13 km)"         with " ",           ['\(.{1,12}km\)', '']
# "(1,520 m) "      with "",            ["\(\d{1,4}.{1,7}\sm\)", ""]
# "[edit]""         with "",            ['\[edit\]', ""]
# " el."            with " elevation"   ["\sel\.", " elevation"]
# "(300.4 km2)"     with ""             ['\(.{1,12}km2\)', '']
# "[2]"             with ""             ['\[\d{0,3}\]', '']
# "{2}"             with ""             ['\(\d{0,2}\)', '']
# "45°39′16′′N 110°56′35′′W﻿ / ﻿45.65444°N 110.94306°W﻿ / 45.65444; -110.94306﻿"
#                   with ""             ['\d{1,3}°.{0,80}-\d{1,3}\.\d{1,7}.{1}', '']          
# The long list of references at the end of a section, ['Preview of references(.|\n)*', ""]
# at the end of the section
# " ,"              with                ["\s,", ","]
# Replace  multiple occurences of white space with a single white space character. 
# " n spaces    "   with " "            ['\s{2,200}', ' ']
# Note: Possibly remove this if we want refernces, which I doubt
# "Preview of references..." 
#                   with ""             ['Preview of references(.|\n)*', '']
# "(−41.7 °C)"      with ""             ['\(.{1,8}°C\)', '']
# (200 to 300 mm)   with ""             ['\(.{1,12}mm\)', '']
# (+/-27.1° C)      with ""             ['\(.{1,8}°C\)', '']
# (2000-3000 mm)    with ""             ['\(.{1,12}mm\)', '']
# TODO Add shorter single lat/lons of each type, such as "45°39′16′′N 110°56′35′′W﻿"
# Add these at the end to do last
# cleanupCharsReplacement =[['\s,', ','], ['(\s|\n){2,200}', " "]]
# for element in cleanupCharsReplacement:
#     replacementCharacterStrings.append(element)
