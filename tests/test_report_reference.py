import pytest

from wcl_notes.services.report_reference import (
    InvalidReportReferenceError,
    ReportReference,
    parse_report_reference,
)

CODE = "cmw7ZBvfaJV6DyKQ"


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (CODE, ReportReference(CODE)),
        (f"  {CODE}\n", ReportReference(CODE)),
        (f"https://www.warcraftlogs.com/reports/{CODE}", ReportReference(CODE)),
        (f"https://www.warcraftlogs.com/reports/{CODE}/", ReportReference(CODE)),
        (f"www.warcraftlogs.com/reports/{CODE}", ReportReference(CODE)),
        (f"https://fr.warcraftlogs.com/reports/{CODE}", ReportReference(CODE)),
        (
            f"https://www.warcraftlogs.com/reports/{CODE}#fight=7&source=118",
            ReportReference(CODE, fight=7, source_id=118),
        ),
        (
            f"https://www.warcraftlogs.com/reports/{CODE}?fight=7&type=damage-done&source=118",
            ReportReference(CODE, fight=7, source_id=118),
        ),
        (
            f"https://www.warcraftlogs.com/reports/{CODE}#fight=last",
            ReportReference(CODE, fight="last"),
        ),
        (
            f"https://www.warcraftlogs.com/reports/{CODE}?fight=LAST",
            ReportReference(CODE, fight="last"),
        ),
    ],
)
def test_parses_codes_and_urls(text: str, expected: ReportReference) -> None:
    assert parse_report_reference(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "not a code",
        "abc123",
        "https://lorrgs.io/spec_ranking/rogue-assassination/nekzali",
        "https://www.warcraftlogs.com/character/eu/ysondre/kraùck",
        "https://www.warcraftlogs.com/reports/tooShort",
        f"https://classic.warcraftlogs.com/reports/{CODE}",
        f"https://www.warcraftlogs.com/reports/{CODE}#fight=abc",
        f"https://www.warcraftlogs.com/reports/{CODE}#fight=7&source=x",
    ],
)
def test_rejects_invalid_references(text: str) -> None:
    with pytest.raises(InvalidReportReferenceError):
        parse_report_reference(text)
