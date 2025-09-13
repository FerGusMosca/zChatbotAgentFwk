# logic/util/google_contact_finder.py

from __future__ import annotations

import difflib
from typing import Optional, Dict, Any
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from pathlib import Path
import logging

from common.util.loader.find_folder import FindFolder
from common.util.settings.env_deploy_reader import EnvDeployReader


class GoogleContactFinder:
    """
    Utility class to search Google Contacts for a person by name.
    Returns the first contact that has a WhatsApp-enabled phone number.
    """

    SCOPES = ["https://www.googleapis.com/auth/contacts.readonly"]

    def __init__(self, logger: Optional[logging.Logger] = None):
        cwd = Path.cwd()
        config_dir = FindFolder.find_config_dir(cwd)

        client_secret = f"{config_dir}/{EnvDeployReader.get('GOOGLE_CLIENT_SECRET').strip()}"
        token_path = f"{config_dir}/{EnvDeployReader.get('GOOGLE_TOKEN_CONTACT_FILE').strip()}"

        self.client_secret_path = Path(client_secret)
        self.token_path = Path(token_path)

        self.logger = logger or logging.getLogger(__name__)
        self.service = self._build_service()

    def _get_credentials(self) -> Credentials:
        """Return credentials, creating token file if needed."""
        creds = None
        if self.token_path.exists():
            creds = Credentials.from_authorized_user_file(str(self.token_path), self.SCOPES)

        # Si no hay credenciales válidas → refrescar o pedir login
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                self.logger.info("[GoogleContactFinder] refreshing expired token")
                creds.refresh(Request())
            else:
                self.logger.info("[GoogleContactFinder] running OAuth flow for Contacts API")
                flow = InstalledAppFlow.from_client_secrets_file(str(self.client_secret_path), self.SCOPES)
                creds = flow.run_local_server(port=0)
            # persistir token
            self.token_path.parent.mkdir(parents=True, exist_ok=True)
            self.token_path.write_text(creds.to_json(), encoding="utf-8")
        return creds

    def _build_service(self):
        creds = self._get_credentials()
        return build("people", "v1", credentials=creds)

    def find_contact(self, name: str) -> Optional[Dict[str, Any]]:
        """
        Search Google Contacts for the closest match by name that has a phone number.
        Uses fuzzy matching to handle partial names or nicknames.
        """
        try:
            # Query Google People API for up to 10 possible matches
            results = (
                self.service.people()
                .searchContacts(query=name, pageSize=10, readMask="names,emailAddresses,phoneNumbers")
                .execute()
            )
            contacts = results.get("results", [])
            if not contacts:
                return None

            # Collect candidate display names
            candidates = []
            for c in contacts:
                person = c.get("person", {})
                display = person.get("names", [{}])[0].get("displayName", "")
                candidates.append((display, person))

            # Extract just names for fuzzy matching
            display_names = [c[0] for c in candidates if c[0]]

            # Pick the closest name to the requested one
            best = difflib.get_close_matches(
                name.lower(), [d.lower() for d in display_names], n=1, cutoff=0.5
            )

            if not best:
                return None

            # Retrieve the person object corresponding to the best match
            best_name = best[0]
            for display, person in candidates:
                if display.lower() == best_name:
                    phones = person.get("phoneNumbers", [])
                    for p in phones:
                        if p.get("value"):
                            return {
                                "name": display,
                                "phone": p.get("value"),
                                "email": (person.get("emailAddresses", [{}])[0].get("value")),
                                "resourceName": person.get("resourceName"),
                            }

            return None

        except Exception as ex:
            self.logger.error(f"[GoogleContactFinder] error searching contact {name}: {ex}")
            return None
