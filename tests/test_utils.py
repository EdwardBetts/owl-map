from matcher import utils


def test_format_wikibase_time_year():
    v = {"time": "+1950-00-00T00:00:00Z", "precision": 9}
    assert utils.format_wikibase_time(v) == "1950"


def test_format_wikibase_time_century():
    v = {"time": "+0800-00-00T00:00:00Z", "precision": 7}
    assert utils.format_wikibase_time(v) == "8th century"

    v = {"time": "+1950-00-00T00:00:00Z", "precision": 7}
    assert utils.format_wikibase_time(v) == "20th century"
