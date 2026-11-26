"""The transfer equivalency builder reads the registrar's tables as written (data/Transfer Credit/)."""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from build_transfer_equivalencies import OUT, mines_codes, numbers  # noqa: E402


def test_numbers_and_mines_codes_read_the_table_cells() -> None:
    assert numbers("201 or 202") == (["201", "202"], False)
    assert numbers("2560 or 2561 or 2562") == (["2560", "2561", "2562"], False)
    assert numbers("N/A") == ([], False)
    assert numbers("Any Number") == ([], True)
    assert mines_codes("CHGN", "221 & 223") == (["CHGN221", "CHGN223"], None)
    assert mines_codes("CSM", "2XX") == (["CSM2XX"], None)
    assert mines_codes("PAGN", "101+") == (["PAGN1XX"], None)
    assert mines_codes("CSCI", "102 *for continuing students only") == (["CSCI102"], "for continuing students only")


def test_the_built_file_matches_the_registrar_lists() -> None:
    data = json.loads(OUT.read_text())
    by_title = {e["title"]: e for e in data["equivalencies"]}
    assert by_title["Calculus I"]["mines"] == ["MATH111"] and by_title["Calculus I"]["numbers"] == ["201", "2410"]
    assert by_title["Computer Science I"]["mines"] == ["CSCI128"]
    assert by_title["Comparative Government"]["subjects"] == ["PSC", "POS"]
    assert by_title["Engineering Projects"]["only_at"] and len(by_title["Engineering Projects"]["only_at"]) == 5
    assert sum(e["mines"] == ["HASS2XX"] for e in data["equivalencies"]) == 73
    assert not any("No CCCS" in e["title"] for e in data["equivalencies"])  # CSCI220 has no CCCS equivalent
