# isc_api_client.py
import requests
import json
from typing import Dict, Any, Optional

class SailPointAPIClient:
    """
    A client for interacting with the SailPoint Identity Security Cloud (ISC) API.
    """
    def __init__(self, base_url: str, client_id: str, client_secret: str):
        self.base_url = base_url
        self.client_id = client_id
        self.client_secret = client_secret
        self._access_token = None
        self._authenticate()

    def _authenticate(self):
        """Authenticates with the SailPoint API using Client Credentials Grant."""
        token_url = f"{self.base_url}/oauth/token"
        headers = {
            "Content-Type": "application/json"
        }
        payload = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "grant_type": "client_credentials"
        }
        
        try:
            response = requests.post(token_url, headers=headers, data=json.dumps(payload))
            response.raise_for_status() # Raise an exception for HTTP errors
            token_data = response.json()
            self._access_token = token_data.get("access_token")
            print("Successfully authenticated with SailPoint ISC API.")
        except requests.exceptions.HTTPError as e:
            print(f"Authentication failed: HTTP Error {e.response.status_code} - {e.response.text}")
            self._access_token = None
            raise
        except requests.exceptions.RequestException as e:
            print(f"Authentication failed: Network or request error - {e}")
            self._access_token = None
            raise
        
        if not self._access_token:
            raise Exception("Authentication failed: Access token not received.")

    def _get_auth_headers(self) -> Dict[str, str]:
        """Returns the authorization headers for API requests."""
        if not self._access_token:
            # Attempt re-authentication if token is missing
            self._authenticate()
            if not self._access_token:
                raise Exception("Cannot make API request: Not authenticated.")
        
        return {
            "Authorization": f"Bearer {self._access_token}",
            "Content-Type": "application/json",
            "Accept": "application/json"
        }

    def create_role(self, role_data: Dict[str, Any]) -> Tuple[bool, str]:
        """
        Creates a new role in SailPoint ISC.
        
        Args:
            role_data (Dict[str, Any]): The JSON payload for the role.
            
        Returns:
            Tuple[bool, str]: A tuple (success_status, message).
        """
        roles_endpoint = f"{self.base_url}/v3/roles"
        headers = self._get_auth_headers()
        
        try:
            response = requests.post(roles_endpoint, headers=headers, data=json.dumps(role_data))
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            
            # Successful creation usually returns 201 Created
            if response.status_code == 201:
                return True, f"Role '{role_data.get('name', 'UNKNOWN')}' created successfully."
            else:
                return False, f"Role '{role_data.get('name', 'UNKNOWN')}' creation failed with unexpected status {response.status_code}: {response.text}"
                
        except requests.exceptions.HTTPError as e:
            status_code = e.response.status_code
            error_message = e.response.text
            return False, f"Role '{role_data.get('name', 'UNKNOWN')}' creation failed (HTTP {status_code}): {error_message}"
        except requests.exceptions.RequestException as e:
            return False, f"Role '{role_data.get('name', 'UNKNOWN')}' creation failed (Network Error): {e}"
        except Exception as e:
            return False, f"Role '{role_data.get('name', 'UNKNOWN')}' creation failed (Unknown Error): {e}"
