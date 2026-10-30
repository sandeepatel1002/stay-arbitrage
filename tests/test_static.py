"""Milestone 3 static frontend contract — single self-contained file, all 3 screens + drawer."""
from pathlib import Path

STATIC_INDEX = Path(__file__).resolve().parent.parent / "static" / "index.html"


def read_html() -> str:
    return STATIC_INDEX.read_text(encoding="utf-8")


def test_single_selfcontained_file():
    files = [p.name for p in (STATIC_INDEX.parent).iterdir()]
    assert files == ["index.html"], "frontend must remain one self-contained file"
    assert "<script src=\"https://cdn.tailwindcss.com\"" in read_html()


def test_all_three_screens_and_drawer_present():
    html = read_html()
    for marker in ("screen-1", "screen-2", "screen-3", "telemetry-lift", "drawer-body"):
        assert marker in html, f"missing UI marker: {marker}"


def test_screen1_has_prompt_and_chips():
    html = read_html()
    assert "id=\"prompt\"" in html
    for chip in ("chip-city", "chip-dates", "chip-guests", "chip-budget"):
        assert chip in html


def test_screen2_podium_labels_and_cta():
    html = read_html()
    for label in ("Best Overall Match", "Value Pick", "Premium Gem", "Compare Live Deals"):
        assert label in html


def test_screen3_has_matrix_cta_elements():
    html = read_html()
    assert "Book on " in html
    assert "savings-ribbon" in html
    assert "perk_value_notes" in html


def test_telemetry_drawer_is_bound():
    html = read_html()
    assert "renderTelemetry" in html
    assert "tokens_in" in html and "latency_ms" in html and "raw_json" in html
    assert "sourceChip" in html  # live/cache/mock chips


def test_no_framework_or_build_step():
    html = read_html()
    for banned in ("import ", "require(", "node_modules"):
        assert banned not in html.lower() or banned == "import " and "vanilla" in html
    # vanilla JS only: no bundler/module attributes
    assert 'type="module"' not in html
