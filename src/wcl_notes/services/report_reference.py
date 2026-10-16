"""Parse what the user pastes: a WCL report code or URL, with optional fight/source."""

import re
from dataclasses import dataclass
from typing import Literal
from urllib.parse import parse_qs, urlsplit

from wcl_notes.i18n import tr

FightSelector = int | Literal["last"]

REPORT_CODE_RE = re.compile(r"^[A-Za-z0-9]{16}$")

# Classic flavours live on other subdomains and use a different API endpoint.
_CLASSIC_SUBDOMAINS = frozenset({"classic", "vanilla", "fresh", "sod"})


class InvalidReportReferenceError(ValueError):
    """The text is not a usable WCL report code or URL. Message is user-facing."""


@dataclass(frozen=True, slots=True)
class ReportReference:
    code: str
    fight: FightSelector | None = None
    source_id: int | None = None


def parse_report_reference(text: str) -> ReportReference:
    raw = text.strip()
    if not raw:
        raise InvalidReportReferenceError(tr("Collez une URL Warcraft Logs ou un code de report."))
    if REPORT_CODE_RE.match(raw):
        return ReportReference(code=raw)

    parts = urlsplit(raw if "://" in raw else f"https://{raw}")
    host = (parts.hostname or "").lower()
    if host != "warcraftlogs.com" and not host.endswith(".warcraftlogs.com"):
        raise InvalidReportReferenceError(
            tr("Ce n'est ni une URL Warcraft Logs ni un code : {text}").format(text=raw)
        )
    if host.split(".", 1)[0] in _CLASSIC_SUBDOMAINS:
        raise InvalidReportReferenceError(tr("Seuls les logs retail sont pris en charge."))

    segments = [s for s in parts.path.split("/") if s]
    if len(segments) < 2 or segments[0] != "reports":
        raise InvalidReportReferenceError(tr("URL sans code de report : {url}").format(url=raw))
    code = segments[1]
    if not REPORT_CODE_RE.match(code):
        raise InvalidReportReferenceError(tr("Code de report invalide : {code}").format(code=code))

    # Older links put fight/source in the fragment, newer ones in the query string.
    params = parse_qs(parts.query) | parse_qs(parts.fragment)
    return ReportReference(
        code=code,
        fight=_parse_fight(_first(params, "fight")),
        source_id=_parse_int(_first(params, "source"), "source"),
    )


def _first(params: dict[str, list[str]], key: str) -> str | None:
    values = params.get(key)
    return values[0] if values else None


def _parse_fight(value: str | None) -> FightSelector | None:
    if value is not None and value.lower() == "last":
        return "last"
    return _parse_int(value, "fight")


def _parse_int(value: str | None, key: str) -> int | None:
    if value is None:
        return None
    if not value.isdigit():
        raise InvalidReportReferenceError(
            tr("Valeur de « {key} » invalide dans l'URL : {value}").format(key=key, value=value)
        )
    return int(value)
