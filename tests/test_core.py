from app.core import canonical, lots_key, sign


def test_appendix_a_vector_1_signature():
    payload = {"team_id": "t1", "event_type": "goal"}
    assert canonical(payload) == '{"event_type":"goal","team_id":"t1"}'
    assert sign("evt-1", payload, key="demo-salt") == (
        "972a8b558690b19121cc5bea84978f85e8eb15a3735018db36616bab1d7ec501"
    )


def test_appendix_a_vector_2_draw_lots():
    assert lots_key(42, "lg-1", "t1") == "0613316991ce0ac31e88d6003e3ff4d5e21bb072ac5f81b42c0cdc6598453293"
    assert lots_key(42, "lg-1", "t2") == "e3e3a14e22727f936e1f288cf5d02a8a9362b1da13c5432725fc10b2c7955dd9"
    assert lots_key(42, "lg-1", "t3") == "c8f28e3c2f1eb6c4f636b4f57050e3362a2b39c07fda9b61742a26dd20397028"


def test_canonical_keeps_non_ascii_and_sorts_recursively():
    assert canonical({"b": {"z": 1, "a": "café"}, "a": [3, 1]}) == '{"a":[3,1],"b":{"a":"café","z":1}}'
