"""Every .graphql query must be valid against the recorded WCL schema: no invented fields."""

from importlib import resources

import pytest
from graphql import build_schema, parse, validate

from conftest import FIXTURES

SCHEMA = build_schema((FIXTURES / "wcl_schema.graphql").read_text(encoding="utf-8"))
QUERIES = sorted(
    entry.name
    for entry in resources.files("wcl_notes.api").joinpath("queries").iterdir()
    if entry.name.endswith(".graphql")
)


def test_queries_exist() -> None:
    assert QUERIES


@pytest.mark.parametrize("name", QUERIES)
def test_query_is_valid_against_schema(name: str) -> None:
    source = resources.files("wcl_notes.api").joinpath("queries", name).read_text(encoding="utf-8")
    errors = validate(SCHEMA, parse(source))
    assert not errors, [e.message for e in errors]
