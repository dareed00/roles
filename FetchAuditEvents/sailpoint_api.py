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

    # ===================================================================
    # === THE FIX IS HERE: The correctly named generic search function ===
    def _get_all_search_results(self, url, search_body):
        """
        Paginates a search query using limit and offset in the URL parameters,
        which is a robust method for most search queries.
        """
        all_results = []; offset = 0; limit = 250
        print(f"Fetching all pages for endpoint: {url}")
        while True:
            pagination_params = {'limit': limit, 'offset': offset}
            response = requests.post(url, headers=self.headers, json=search_body, params=pagination_params, verify=False)
            response.raise_for_status()
            page_results = response.json()
            if not page_results:
                print("Received an empty page. Assuming all results have been fetched."); break
            all_results.extend(page_results)
            print(f"  ... Fetched {len(all_results)} total records so far...")
            offset += limit
        return all_results
    # ===================================================================

    def get_all_identities_with_access(self):
        """
        Fetches ALL identities and their access assignments.
        This now correctly calls the standardized search function.
        """
        print("Fetching all identities with included access assignments...")
        url = f"{self.base_url}/v3/search"
        search_payload = {
            "query": { "query": "*" },
            "indices": ["identities"],
            "sort": ["name"],
            "queryResultFilter": { "includes": ["id", "name", "email", "access"] }
        }
        return self._get_all_search_results(url, search_body=search_payload)
