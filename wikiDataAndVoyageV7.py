import pprint
import sys
import requests
import pywikibot
from pywikibot import textlib
import time
import re
import json
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
verbose = True

# This program retrieves Wikidata and Wikivoyage info based on a provided wikiDataId

class GetWikiDataVoyageInfo:
    def __init__(self):
        self.wikiVoyageRecord = []
        # List of all items to retrieve from WikiData
        self.wikidataKeyDict = {
          "elevation": "P2044",            # Elevation
          "inception": "P571",             # Inception
          "population": "P1082",           # Population (preferred)
          "postal_codes": "P281",          # Postal codes (this will be a range or a list of ranges I believe)
          "official_website": "P856",      # Official Website
          "number_of_households": "P1538", # Number of Households
          "per_capita_income": "P10622",   # Per Capita Income
        }


    def read_wikivoyage_data(self, wikivoyage_title, data):
        dictionary ={
        "eat": [],
        "see": [],
        "do": [],
        "drink": []
        }
        try:
            self.site = pywikibot.Site('en', 'wikivoyage')
            # page = pywikibot.Page(self.site, "Middletown_(Connecticut)")
            page = pywikibot.Page(self.site, wikivoyage_title)
            # print(page.text)
            tmp = textlib.extract_templates_and_params(page.text, remove_disabled_parts=True, strip=True)

            for item in tmp:
                if item[0] in dictionary:
                    dictionary[item[0]].append(item[1])
            for key in dictionary:
                data[key] = dictionary[key]
        except:
            # TODO add error message and write to server log
            return
            

    def read_wikidata_population(self, item_dict, data):
        try:
            self.item_dict = item_dict
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["population"]] # Get population data.
            for clm in clm_list:
                if (clm.rank == "preferred"):
                    data["population"] = int(clm.getTarget().amount)
                    break
                else:
                    # Use the last population.
                    data["population"] = int(clm.getTarget().amount)
        except:
            data["population"] = "unknown"
            

    def read_wikidata_elevation(self, item_dict, data):
        try:
            # for item in item_dict:
            #     print(item)
            #     print(item_dict[item])
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            # json_data = json.dumps(clm_dict, indent=2)
            # print("JSON output: \n", json_data)
            # for clm in clm_dict:
            #     print(clm)

            clm_list = clm_dict[self.wikidataKeyDict["elevation"]]

            # elevation usually only has one value so taking the first value in the list.
            for clm in clm_list:
                data["elevation"] = int(clm.getTarget().amount)
                break
        except:
            data["elevation"] = "unknown"
            

    def read_wikidata_inception(self, item_dict, data):
        try:
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["inception"]]
            # print(f'clm_list = {clm_list}')
            for clm in clm_list:
                data["inception"] = clm.getTarget().year
        except:
            # print(f'clm_list except = {clm_list}')
            data["inception"] = "unknown"

    def read_wikidata_postal_codes(self, item_dict, data):
        try:
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["postal_codes"]]
            postal_codes = []
            for clm in clm_list:
                str = clm.getTarget()
                if "–" in str:
                    lower = int(str.split("–")[0])
                    upper = int(str.split("–")[1])
                    postal_codes.extend([*range(lower, upper + 1)])
                else:
                    postal_codes.append(int(str))
            data["postal_codes"] = [*set(postal_codes)]
        except:
            data["postal_codes"] = "unknown"
            

    def read_wikidata_official_website(self, item_dict, data):
        try:
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["official_website"]]
            postal_codes = []
            for clm in clm_list:
                data["official_website"] = clm.getTarget()
                break
        except:
            data["official_website"] = "unknown"
            

    def read_wikidata_number_of_households(self, item_dict, data):
        try:
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["number_of_households"]]
            postal_codes = []
            for clm in clm_list:
                data["number_of_households"] = int(clm.getTarget().amount)
        except:
            data["number_of_households"] = "unknown"
            

    def read_wikidata_per_capita_income(self, item_dict, data):
        try:
            clm_dict = self.item_dict["claims"] # Get the claim dictionary
            clm_list = clm_dict[self.wikidataKeyDict["per_capita_income"]]
            postal_codes = []
            for clm in clm_list:
                data["per_capita_income"] = int(clm.getTarget().amount)
        except:
            data["per_capita_income"] = "unknown"
            

    # This function will retrieve WikiData and WikiVoyage data 
    # based on a provided Wikidata ID
    def getStructuredWikiDataInfo(self, wikidata_id):
        self.wikidata_id = wikidata_id
        self.data = {}
        self.data['result'] = ""
        try:
            for wikidata_id in [wikidata_id]: 
                timer_start = time.perf_counter()
                self.data["apiResponseCode"] = 400
                self.data["wikiDataId"] = wikidata_id
                self.site = pywikibot.Site("wikidata", "wikidata")
                self.repo = self.site.data_repository()
                item = pywikibot.ItemPage(self.repo, wikidata_id)
                self.item_dict = item.get()
                # print("*************************** WikiData Dictionary ******************************************")
                # pprint.pprint(self.item_dict, sort_dicts=False)
              
                if "enwiki" in self.item_dict["sitelinks"]:
                    self.wikipedia_title = self.item_dict["sitelinks"].toJSON()["enwiki"]["title"]
                    self.data['title'] = self.wikipedia_title
                    self.wikipedia_link = "https://en.wikipedia.org/wiki/" + self.wikipedia_title.replace(" ", "_")
                    self.data["wikipedia_link"] = self.wikipedia_link
                # If there is no city name, use the WikiData label instead
                elif "en" in self.item_dict["labels"]:
                    self.wikipedia_title = self.item_dict["labels"].toJSON()["en"]["value"]
                    self.data['title'] = self.wikipedia_title
                    self.wikipedia_link = "unknown"
                    self.data["wikipedia_link"] = "unknown"
                else:
                    self.wikipedia_title = "unknown"
                    self.data['title'] = "unknown"
                    self.wikipedia_link = "unknown"
                    self.data["wikipedia_link"] = "unknown"
                    
                if "enwikivoyage" in self.item_dict["sitelinks"]:
                    self.wikivoyage_title = self.item_dict["sitelinks"].toJSON()["enwikivoyage"]["title"]
                    self.wikivoyage_link = "https://en.wikivoyage.org/wiki/" + self.wikivoyage_title.replace(" ", "_")
                    self.data["wikivoyage_link"] = self.wikivoyage_link
                else: 
                    self.wikivoyage_title = "unknown"
                    self.wikivoyage_link = "unknown"
                    self.data["wikivoyage_link"] = "unknown"

                self.read_wikidata_elevation(self.item_dict, self.data)
                self.read_wikidata_inception(self.item_dict, self.data)
                self.read_wikidata_population(self.item_dict, self.data)
                self.read_wikidata_postal_codes(self.item_dict, self.data)
                self.read_wikidata_official_website(self.item_dict, self.data)
                self.read_wikidata_number_of_households(self.item_dict, self.data)
                self.read_wikidata_per_capita_income(self.item_dict, self.data)
                self.read_wikivoyage_data(self.wikivoyage_title, self.data)
                # self.read_wikipedia_summary(wikipedia_link, self.data)
                timer_end = time.perf_counter()
                self.data["apiResponseCode"] = 200

                if verbose == True: print("this request took %.2f seconds" % (timer_end - timer_start))
                json_data = json.dumps(self.data, indent=2)
                if verbose == True: print("JSON output: \n", json_data)
        except:
            self.data["apiResponseCode"] = 400
            self.data['result'] = "error"
            json_data = json.dumps(self.data, indent=2)
            if verbose == True: pprint.pprint("JSON output: \n", json_data, sort_dicts=False)
        
if __name__ == "__main__":  

    wikiDataInfo = GetWikiDataVoyageInfo()
    wikiDataInfo.getStructuredWikiDataInfo("Q584340")
    # Western Australia desert: Q7697195
    # Middletown, Connecticut: Q49192
    # New York City: Q60
    # Warren Ohio: Q862733
    # Fort Pierce: Q584340
    # pprint.pprint (wikiDataInfo.data, sort_dicts=False)
    
    if wikiDataInfo.data["result"] != "error":
        print(f'You are in {wikiDataInfo.data["title"]}{" founded in " + wikiDataInfo.data["inception"] if wikiDataInfo.data["inception"] != "unknown" else ""}, population {wikiDataInfo.data["population"]} at elevation {wikiDataInfo.data["elevation"]} feet above sea level.')
        print(f'\nPlaces to eat:')
        for item in wikiDataInfo.data["eat"]:
            print(f'{item["name"]}')
            print(f'{item["address"]}, {wikiDataInfo.data["title"]}')
            print(item["url"])
        print(f'\nPlaces to drink:')
        for item in wikiDataInfo.data["drink"]:
            print(item["name"])
        print(f'\nPlaces to see:')
        for item in wikiDataInfo.data["see"]:
            print(item["name"])
        print(f'\nThings to do:')
        for item in wikiDataInfo.data["do"]:
            print(item["name"])
    else: print(f'No Wikidata record available for ID: {wikiDataInfo.data["wikiDataId"]}')
    
    # To print JSON file
    # pprint.pprint(wikiDataInfo.data, sort_dicts=False, indent=4)











# Old Code
# # NOTE:  We no longer need this as we already get this with the wikipedia API
#     def read_wikipedia_summary(self, url, data):
#         # Wikipedia example
#         response = requests.get(
#             url=url,
#         )

#         soup = BeautifulSoup(response.content, 'html.parser')

#         first_paragraph = soup.find('div',id="bodyContent").find_all("p")[1].text
#         first_paragraph = re.sub("\[[0-9]+\]", '', first_paragraph)
#         data["summary"] = first_paragraph
