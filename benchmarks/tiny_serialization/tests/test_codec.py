from __future__ import annotations

from tiny_serialization import decode_record, encode_record


def test_round_trip_preserves_integer_score_keys() -> None:
    record = {
        "user": "ada",
        "scores": {
            101: 9,
            202: 10,
        },
    }

    assert decode_record(encode_record(record)) == record


def test_decode_converts_integer_like_score_keys() -> None:
    payload = '{"scores": {"101": 9, "202": 10}, "user": "ada"}'

    assert decode_record(payload)["scores"] == {101: 9, 202: 10}


def test_decode_leaves_other_string_keys_unchanged() -> None:
    payload = '{"metadata": {"101": "external-id"}, "scores": {"101": 9}}'

    decoded = decode_record(payload)

    assert decoded["metadata"] == {"101": "external-id"}
    assert decoded["scores"] == {101: 9}
