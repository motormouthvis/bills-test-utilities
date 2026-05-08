import pprint
import sys
import requests
import time
import json
sys.stdin.reconfigure(encoding='utf-8')
sys.stdout.reconfigure(encoding='utf-8')
verbose = False
# API Key for WalkScore.com
API_KEY = 'f5d4abe0b13a8f92bc7397ee6bf8bf2f'

# This program retrieves Walkability, Bikeability and Transitability scores

class WalkAbilityScore:
    def __init__(self):
        self.data = {}

    def get_walk_score(self, device_lat=None, device_lon=None):
        base_url = "https://api.walkscore.com/score"
        params = {
            'format': 'json',
            'wsapikey': API_KEY,
            'transit' : 1,
            'bike' : 1,
            'lat' : device_lat,
            'lon' : device_lon
        }
      
        try:
            # Making the API call
            response = requests.get(base_url, params=params)
            # response.raise_for_status() 
            # TODO "What is this?  It is recommended by the API guide"
            
            # Parse the JSON response and add the API response code to the dictionary
            self.data = response.json()
            self.data["apiResponseCode"] = response.status_code
            self.data["walkScoreMessage"] = ""
            
            if verbose == True:
                pprint.pprint(self.data, sort_dicts=False)

            if self.data['status'] == 1:
                self.data["walkScoreMessage"] = (f"The Walk Score for your location is {self.data['walkscore']} out of 100: {self.data.get('description', '')}")
                if 'transit' in self.data:
                    self.data["walkScoreMessage"] = self.data["walkScoreMessage"] + (f"\nThe Transit Score is {self.data['transit']['score']} out of 100: {walkScore.data['transit']['description']}")
                if 'bike' in self.data:
                    self.data["walkScoreMessage"] = self.data["walkScoreMessage"] + (f"\nThe Bike Score is {self.data['bike']['score']} out of 100: {self.data['bike']['description']}")
            elif walkScore.data["status"] == 2:
                    self.data["walkScoreMessage"] = (f"A Walk Score is unavailable for this location")
            elif walkScore.data["status"] == 30:
                    self.data["walkScoreMessage"] = (f"Invalid latitude and longitude")
            elif walkScore.data["status"] == 31:
                    self.data["walkScoreMessage"] = (f"Walk Score API internal error.")
            elif walkScore.data["status"] == 40:
                    self.data["walkScoreMessage"] = (f"Your WSAPIKEY is invalid")
            elif walkScore.data["status"] == 41:
                    self.data["walkScoreMessage"] = (f"Your daily API quota has been exceeded")
            elif walkScore.data["status"] == 42:
                    self.data["walkScoreMessage"] = (f"Your IP address has been blocked.")
            else:
                    self.data["walkScoreMessage"] = (f"Error retrieving Walk Score: {walkScore.data.get('status_text', 'Unknown error')}")



            return self.data
            
        except requests.RequestException as e:
            self.data["walkScoreMessage"] = (f"An error occurred in the WalkScore API Module: {e}")
            self.data["apiResponseCode"] = f"From WalkScore module: Unknown error retrieving data from URL {base_url}"
            return self.data
            
if __name__ == "__main__":  
    
    location = (40.74294043173723, -73.9930926747201)
    lat = location[0]
    lon = location[1]
    
    # Instantiate Class and call function in Class
    walkScore = WalkAbilityScore()
    walkScore.get_walk_score(lat, lon)
    
    print(walkScore.data.get('walkScoreMessage'))
    pprint.pprint(walkScore.data, sort_dicts=False, indent=4)

