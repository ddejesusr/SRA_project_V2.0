from sra_production.state_model import (
    FestoProcessState,
    get_state_info,
    infer_top_cover,
    is_valid_transition,
)


BLUE_PATH = [0, 100, 200, 301, 401, 501, 601, 701]
RED_PATH = [0, 100, 200, 300, 402, 502, 602, 702]


def test_blue_path_is_valid():
    assert all(
        is_valid_transition(current, following)
        for current, following in zip(BLUE_PATH, BLUE_PATH[1:])
    )


def test_red_path_is_valid():
    assert all(
        is_valid_transition(current, following)
        for current, following in zip(RED_PATH, RED_PATH[1:])
    )


def test_repeated_state_read_is_valid_observation():
    assert is_valid_transition(501, 501)


def test_cross_branch_transition_is_rejected():
    assert not is_valid_transition(301, 402)
    assert not is_valid_transition(300, 401)


def test_skipped_process_stage_is_rejected():
    assert not is_valid_transition(200, 501)
    assert not is_valid_transition(401, 601)


def test_top_cover_is_inferred_from_state_code():
    assert infer_top_cover(300) == "red"
    assert infer_top_cover(501) == "blue"
    assert infer_top_cover(702) == "red"
    assert infer_top_cover(200) is None


def test_state_metadata_is_canonical():
    state = get_state_info(401)
    assert state.process_state is FestoProcessState.TOP_COVER_COMPLETED_BLUE
    assert state.top_cover == "blue"
