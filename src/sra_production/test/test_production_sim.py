from sra_production.production_sim_node import ProductionSimNode


def test_blue_simulation_emits_valid_blue_path():
    events = ProductionSimNode._build_events(
        {
            "carrier_id": 8,
            "bottom_cover": "red",
            "top_cover": "blue",
            "fuse_configuration": "both",
            "dispatch_position": 2,
        }
    )

    state_codes = [
        event["state_code"]
        for event in events
        if event["type"] in {"state_update", "dispatch_handoff"}
    ]
    assert state_codes == [200, 301, 401, 501, 601, 701]
    assert events[0]["type"] == "camera_inspection"
    assert events[-1]["dispatch_position"] == 2


def test_red_simulation_emits_valid_red_path():
    events = ProductionSimNode._build_events(
        {
            "carrier_id": 9,
            "bottom_cover": "black",
            "top_cover": "red",
            "fuse_configuration": "lower",
            "dispatch_position": 1,
        }
    )

    state_codes = [
        event["state_code"]
        for event in events
        if event["type"] in {"state_update", "dispatch_handoff"}
    ]
    assert state_codes == [200, 300, 402, 502, 602, 702]


def test_simulation_rejects_invalid_dispatch_position():
    try:
        ProductionSimNode._build_events(
            {
                "carrier_id": 10,
                "bottom_cover": "blue",
                "top_cover": "blue",
                "fuse_configuration": "none",
                "dispatch_position": 3,
            }
        )
    except ValueError as exc:
        assert "dispatch_position" in str(exc)
    else:
        raise AssertionError("Invalid dispatch position was accepted")
