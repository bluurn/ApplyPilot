from applypilot.scoring.cover_letter import _build_cover_letter_prompt, _ensure_signoff


def test_cover_letter_uses_full_name_over_profile_nickname() -> None:
    prompt = _build_cover_letter_prompt(
        {
            "personal": {
                "full_name": "Vladimir Suvorov",
                "preferred_name": "bluurn",
            }
        }
    )

    assert "Best regards,\nVladimir Suvorov" in prompt
    assert 'Best regards,\nbluurn' not in prompt
    assert "briefly introduce yourself and name the role" in prompt


def test_cover_letter_signoff_is_normalized() -> None:
    result = _ensure_signoff(
        "Dear Hiring Manager,\n\nI built reliable backend systems.\n\nbluurn",
        {"personal": {"full_name": "Vladimir Suvorov", "preferred_name": "bluurn"}},
    )

    assert result.endswith("Best regards,\nVladimir Suvorov")
    assert not result.endswith("bluurn")
