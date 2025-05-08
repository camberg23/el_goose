# api_client.py
import requests

BASE_URL = "https://elgoose.net/api/v2"

class ElGooseClient:
    def __init__(self, base_url=BASE_URL):
        self.base_url = base_url

    def _build_url(self, method, identifier=None, column=None, value=None, fmt="json"):
        parts = [self.base_url, method]
        if identifier is not None:
            parts.append(str(identifier))
        elif column and value is not None:
            parts.append(f"{column}/{value}")
        return "/".join(parts) + f".{fmt}"

    def fetch(self, method, identifier=None, column=None, value=None, fmt="json", **params):
        url = self._build_url(method, identifier, column, value, fmt)
        response = requests.get(url, params=params)

        # Normalize non-200 status into a JSON-like error dict
        if response.status_code != 200:
            return {
                "error": response.status_code,
                "error_message": f"HTTP {response.status_code}",
                "data": [],
                "raw_text": response.text[:200]
            }

        # Attempt to parse JSON; on failure return an error dict
        try:
            payload = response.json()
        except ValueError:
            return {
                "error": 1,
                "error_message": "Non-JSON response",
                "data": [],
                "raw_text": response.text[:200]
            }

        return payload
