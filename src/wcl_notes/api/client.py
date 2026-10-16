"""GraphQL client for the public WCL v2 endpoint. Queries live in ``queries/*.graphql``."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from importlib import resources
from types import TracebackType
from typing import Any, Self

import httpx

from wcl_notes import __version__
from wcl_notes.api.auth import TokenProvider
from wcl_notes.api.credentials import Credentials
from wcl_notes.api.errors import (
    PrivateReportError,
    RateLimitError,
    ReportNotFoundError,
    WclApiError,
    WclError,
    WclNetworkError,
)
from wcl_notes.cache.response_cache import ResponseCache

API_URL = "https://www.warcraftlogs.com/api/v2/client"


@dataclass(frozen=True, slots=True)
class CacheRule:
    ttl_s: float | None
    """Seconds before expiry; None = kept forever (immutable data)."""


FOREVER = CacheRule(ttl_s=None)
# A rule, or a function deciding from the response (e.g. "is this report finished?").
CachePolicy = CacheRule | Callable[[dict[str, Any]], CacheRule | None] | None


def load_query(name: str) -> str:
    return (
        resources.files("wcl_notes.api")
        .joinpath("queries", f"{name}.graphql")
        .read_text(encoding="utf-8")
    )


class WclClient:
    def __init__(
        self,
        credentials: Credentials,
        *,
        http: httpx.Client | None = None,
        timeout: float = 30.0,
        cache: ResponseCache | None = None,
    ) -> None:
        self._http = http or httpx.Client(timeout=timeout)
        self._http.headers["User-Agent"] = f"wcl-notes/{__version__}"
        self._tokens = TokenProvider(credentials, self._http)
        self._cache = cache
        self.cache_hits = 0

    def __enter__(self) -> Self:
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def execute(
        self, query_name: str, variables: Mapping[str, object], *, cache: CachePolicy = None
    ) -> dict[str, Any]:
        """Run a named query and return its ``data``; raise a ``WclError`` otherwise.

        With a ``cache`` policy, a stored response is returned without any network call
        (no API points spent), and a fresh one is stored according to the policy.
        """
        query = load_query(query_name)
        key = ResponseCache.make_key(query, variables)
        if self._cache is not None and cache is not None:
            cached = self._cache.get(key)
            if cached is not None:
                self.cache_hits += 1
                return cached
        data = self._fetch({"query": query, "variables": dict(variables)})
        if self._cache is not None and cache is not None:
            rule = cache(data) if callable(cache) else cache
            if rule is not None:
                self._cache.put(key, query_name, data, rule.ttl_s)
        return data

    def _fetch(self, payload: dict[str, object]) -> dict[str, Any]:
        response = self._post(payload)
        if response.status_code == 401:
            # Token revoked or expired early: get a fresh one once.
            self._tokens.invalidate()
            response = self._post(payload)
        _raise_for_status(response)

        body = response.json()
        if body.get("errors"):
            raise _graphql_error(body["errors"])
        data = body.get("data")
        if not isinstance(data, dict):
            raise WclApiError("Réponse inattendue de Warcraft Logs (pas de données).")
        return data

    def _post(self, payload: dict[str, object]) -> httpx.Response:
        headers = {"Authorization": f"Bearer {self._tokens.token()}"}
        try:
            return self._http.post(API_URL, json=payload, headers=headers)
        except httpx.HTTPError as exc:
            raise WclNetworkError(f"Impossible de joindre Warcraft Logs : {exc}") from exc


def _raise_for_status(response: httpx.Response) -> None:
    status = response.status_code
    if status == 200:
        return
    if status == 429:
        raise RateLimitError(
            "Quota horaire de l'API Warcraft Logs dépassé : réessayez dans quelques minutes."
        )
    if status == 403:
        raise PrivateReportError("Accès refusé par Warcraft Logs (log privé ?).")
    raise WclApiError(f"Erreur HTTP {status} renvoyée par Warcraft Logs.")


def _graphql_error(errors: list[dict[str, Any]]) -> WclError:
    message = str(errors[0].get("message", "erreur inconnue"))
    lowered = message.lower()
    if "does not exist" in lowered:
        return ReportNotFoundError("Ce report n'existe pas : vérifiez le code ou l'URL.")
    if "permission" in lowered or "private" in lowered:
        return PrivateReportError(
            "Ce report est privé : il n'est pas accessible avec l'API publique."
        )
    if "rate limit" in lowered:
        return RateLimitError(
            "Quota horaire de l'API Warcraft Logs dépassé : réessayez dans quelques minutes."
        )
    return WclApiError(f"Warcraft Logs a renvoyé une erreur : {message}")
