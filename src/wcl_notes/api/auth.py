"""OAuth client-credentials token, cached in memory until it expires."""

import threading
import time
from collections.abc import Callable

import httpx

from wcl_notes.api.credentials import Credentials
from wcl_notes.api.errors import AuthenticationError, WclApiError, WclNetworkError

TOKEN_URL = "https://www.warcraftlogs.com/oauth/token"
_EXPIRY_MARGIN_S = 60.0


class TokenProvider:
    def __init__(
        self,
        credentials: Credentials,
        http: httpx.Client,
        *,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._credentials = credentials
        self._http = http
        self._clock = clock
        self._token: str | None = None
        self._expires_at = 0.0
        self._lock = threading.Lock()

    def token(self) -> str:
        # The UI runs requests from a thread pool: fetch the token only once.
        with self._lock:
            if self._token is None or self._clock() >= self._expires_at:
                self._token, lifetime = self._request_token()
                self._expires_at = self._clock() + max(lifetime - _EXPIRY_MARGIN_S, 0.0)
            return self._token

    def invalidate(self) -> None:
        with self._lock:
            self._token = None

    def _request_token(self) -> tuple[str, float]:
        try:
            response = self._http.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(self._credentials.client_id, self._credentials.client_secret),
            )
        except httpx.HTTPError as exc:
            raise WclNetworkError(f"Impossible de joindre Warcraft Logs : {exc}") from exc
        if response.status_code in (400, 401):
            raise AuthenticationError(
                "Identifiants Warcraft Logs refusés : vérifiez WCL_CLIENT_ID et WCL_CLIENT_SECRET."
            )
        if response.status_code != 200:
            raise WclApiError(
                f"Échec de l'authentification Warcraft Logs (HTTP {response.status_code})."
            )
        payload = response.json()
        return str(payload["access_token"]), float(payload.get("expires_in", 3600))
