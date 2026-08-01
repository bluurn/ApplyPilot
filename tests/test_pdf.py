from applypilot.scoring.pdf import build_cover_letter_html


def test_cover_letter_pdf_uses_left_aligned_prose_layout() -> None:
    html = build_cover_letter_html(
        "Dear Hiring Manager,\n\nI built reliable backend systems.\n\nVladimir Suvorov"
    )

    assert "text-align: left" in html
    assert "border-bottom" not in html
    assert "I built reliable backend systems." in html
    assert "Vladimir Suvorov" in html
