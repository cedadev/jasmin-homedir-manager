import logging
from typing import Optional

import authlib.integrations.httpx_client

from .. import settings


class BaseCommand:
    """Base class for shared authentication."""

    def __init__(
        self, settings: settings.Settings, dry_run: bool = False, careful: bool = False
    ):
        self.settings = settings
        self.dry_run = dry_run
        self.careful = careful
        self.client: Optional[authlib.integrations.httpx_client.OAuth2Client] = None
        self.logger = logging.getLogger(self.__class__.__name__)

    def get_authenticated_client(
        self,
    ) -> authlib.integrations.httpx_client.OAuth2Client:
        """Get authenticated OAuth client."""
        if self.client is None:
            self.client = authlib.integrations.httpx_client.OAuth2Client(
                self.settings.client_id,
                self.settings.client_secret,
                scope=" ".join(self.settings.scopes),
                timeout=5,
            )
            self.client.fetch_token(
                self.settings.token_endpoint, grant_type="client_credentials"
            )
            self.logger.info("Successfully authenticated with JASMIN API")

        return self.client

    def execute(self) -> None:
        """Command logic."""
        raise NotImplementedError
