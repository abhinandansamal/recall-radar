from datetime import date
from pathlib import Path

import pytest

from rr_ingest.safety_gate import (
    InvalidReportError,
    WeeklyReport,
    content_fingerprint,
    count_alerts,
    detail_url_for,
    landing_name,
    parse_index,
)

FIXTURES = Path(__file__).parents[2] / "fixtures" / "safety_gate"
ERROR_PAGE = b"<!DOCTYPE html><html><body><h1>Oops! Something went wrong!</h1></body></html>"


def test_parse_index_reads_entries_newest_first():
    reports = parse_index((FIXTURES / "index_small.xml").read_bytes())

    assert [r.reference for r in reports] == ["Report-2026-45", "Report-2026-44"]
    assert reports[0].publication_date == date(2026, 11, 13)


def test_parse_index_decodes_ampersand_in_url():
    report = parse_index((FIXTURES / "index_small.xml").read_bytes())[0]

    assert "&amp;" not in report.detail_url
    assert report.detail_url.endswith("?language=en&search=WEB_REPORT%7C:%7C10000331,")


def test_parse_index_rejects_other_documents():
    with pytest.raises(InvalidReportError):
        parse_index(ERROR_PAGE)


def test_detail_url_changes_only_the_language():
    report = WeeklyReport(
        "Report-2026-45", date(2026, 11, 13), "https://x/detail/xml/1?language=en&search=A%7C:%7C1,"
    )

    assert detail_url_for(report, "de") == "https://x/detail/xml/1?language=de&search=A%7C:%7C1,"


@pytest.mark.parametrize("language", ["DE", "deu", "", "d1"])
def test_detail_url_rejects_bad_language(language):
    report = WeeklyReport("R", date(2026, 1, 1), "https://x/detail?language=en")

    with pytest.raises(ValueError, match="invalid language"):
        detail_url_for(report, language)


def test_detail_url_needs_a_language_parameter():
    report = WeeklyReport("R", date(2026, 1, 1), "https://x/detail?mylanguage=en")

    with pytest.raises(ValueError, match="no language parameter"):
        detail_url_for(report, "de")


def test_count_alerts_on_real_report():
    assert count_alerts((FIXTURES / "detail_small.xml").read_bytes()) == 2


@pytest.mark.parametrize("content", [ERROR_PAGE, b"not xml at all", b""])
def test_count_alerts_rejects_error_pages_and_garbage(content):
    with pytest.raises(InvalidReportError):
        count_alerts(content)


def test_landing_name_is_stable_for_same_content_and_changes_with_content():
    first = landing_name("Report-2026-45", b"<a/>")

    assert first == landing_name("Report-2026-45", b"<a/>")
    assert first != landing_name("Report-2026-45", b"<a>x</a>")
    assert first.startswith("Report-2026-45_") and first.endswith(".xml")
    assert len(first) == len("Report-2026-45_") + 12 + len(".xml")


# Both styles were served by the EC for the same report within 30 minutes (2026-11-13).
STYLE_CDATA = b"""<?xml version="1.0" encoding="UTF-8"?>
<Safety-Gate><report_addendum><![CDATA[]]></report_addendum>
<notifications xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="X">
<caseNumber>SR/1/26</caseNumber><name><![CDATA[]]></name><URLrecall/>
<pictures><picture><![CDATA[https://x/1]]></picture></pictures></notifications></Safety-Gate>"""
STYLE_NIL = b"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Safety-Gate>
  <report_addendum xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:nil="true"/>
  <notifications xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:type="X">
    <caseNumber>SR/1/26</caseNumber>
    <name xsi:nil="true"/>
    <URLrecall xsi:nil="true"/>
    <pictures><picture>https://x/1</picture></pictures>
  </notifications>
</Safety-Gate>"""


def test_fingerprint_ignores_empty_field_style_and_declaration():
    assert content_fingerprint(STYLE_CDATA) == content_fingerprint(STYLE_NIL)


def test_fingerprint_changes_when_a_value_changes():
    changed = STYLE_NIL.replace(b"SR/1/26", b"SR/2/26")

    assert content_fingerprint(STYLE_NIL) != content_fingerprint(changed)


def test_fingerprint_changes_when_a_picture_is_added():
    more = STYLE_NIL.replace(b"</pictures>", b"<picture>https://x/2</picture></pictures>")

    assert content_fingerprint(STYLE_NIL) != content_fingerprint(more)
