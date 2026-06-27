from poker.cards import display_card, display_cards


CARD_BACK = chr(0x1F0A0)


def test_display_card_accepts_uppercase_codes():
    assert display_card("AS") == "A\u2660"
    assert display_card("TH") == "10\u2665"


def test_display_card_accepts_lowercase_test_fixture_codes():
    assert display_card("Ah") == "A\u2665"
    assert display_card("qs") == "Q\u2660"


def test_display_card_uses_real_card_back_symbol():
    assert display_card("BACK") == CARD_BACK
    assert display_card("BACK") != "??"


def test_display_cards_accepts_mixed_case_codes_and_backs():
    assert display_cards(["Ah", "KS", "BACK"]) == ["A\u2665", "K\u2660", CARD_BACK]
