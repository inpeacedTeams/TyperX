from typerx.domain.typing_physics import finger_for_key


def test_same_finger_keys_share_a_bucket() -> None:
    assert finger_for_key("f") == finger_for_key("r")
    assert finger_for_key("а") == finger_for_key("к")
    assert finger_for_key("j") == finger_for_key("u")


def test_opposite_hands_use_different_buckets() -> None:
    assert finger_for_key("f") != finger_for_key("j")
    assert finger_for_key("а") != finger_for_key("о")


def test_space_uses_thumb() -> None:
    assert finger_for_key(" ") == "thumb"
