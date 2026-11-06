# sailpoint_api.py

import requests
import urllib3

# Suppress warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class SailPointAPI:
    def __init__(self, isc_config):
        self.client_id = isc_config.get("ClientId")
        self.client_secret = isc_config.get("ClientSecret")
        self.base_url = isc_config.get("BaseURL")
        self.access_token = self._get_access_token()
        self.headers = {'Authorization': f'Bearer {self.access_token}', 'Content-Type': 'application/json'}

    def _get_access_token(self):
        print("Attempting to get access token...")
        token_url = f"{self.base_url}/oauth/token"
        payload = {'grant_type': 'client_credentials', 'client_id': self.client_id, 'client_secret': self.client_secret}
        try:
            response = requests.post(token_url, data=payload, verify=False)
            response.raise_for_status()
            print("Successfully obtained access token.")
            return response.json().get("access_token")
        except requests.exceptions.RequestException as e:
            print(f"FATAL: Failed to obtain access token: {e}"); raise

    def _get_all_pages_by_link_header(self, url, search_body):
        """
        Paginates using the 'Link' response header, which is the correct
        method for this specific, complex search query.
        """
        all_results = []
        print(f"Fetching results for endpoint: {url}")
        
        # Make the first, clean request with no pagination parameters
        response = requests.post(url, headers=self.headers, json=search_body, verify=False)
        response.raise_for_status()
        
        page_results = response.json()
        all_results.extend(page_results)
        
        total_count = int(response.headers.get('X-Total-Count', len(all_results)))
        print(f"Total records to fetch (from header): {total_count}")
        print(f"  ... Fetched {len(all_results)} / {total_count} records")

        # Loop and follow the 'next' link in the Link header
        while 'next' in response.links:
            next_url = response.links['next']['url']
            print(f"  ... Following next page link...")
            response = requests.get(next_url, headers=self.headers, verify=False)
            response.raise_for_status()
            
            page_results = response.json()
            all_results.extend(page_results)
            print(f"  ... Fetched {len(all_results)} / {total_count} records")

        print("All pages fetched.")
        return all_results

    def get_all_identities_with_access(self):
        """
        Fetches ALL identities and includes their access assignments using the
        correct payload that was proven to work.
        """
        print("Fetching all identities with included access assignments...")
        url = f"{self.base_url}/v3/search"
        # ===================================================================
        # === THE CORRECT PAYLOAD FROM YOUR RESEARCH AND OUR SUCCESSFUL TEST ===
        search_payload = {
            "query": { "query": "*" },
            "indices": ["identities"],
            "sort": ["name"],
            "queryResultFilter": {
                "includes": ["id","email","name","access"]
            }
        }
        # ===================================================================
        return self._get_all_pages_by_link_header(url, search_body=search_payload)
