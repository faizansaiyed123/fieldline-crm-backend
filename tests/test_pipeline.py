from app.services.pipeline import DEFAULT_PIPELINE


def test_default_pipeline_has_ordered_open_and_closed_stages() -> None:
    assert [stage[0] for stage in DEFAULT_PIPELINE] == [
        "New",
        "Qualified",
        "Proposal",
        "Negotiation",
        "Closed Won",
        "Closed Lost",
    ]
    assert DEFAULT_PIPELINE[:4] and all(not stage[3] for stage in DEFAULT_PIPELINE[:4])
    assert DEFAULT_PIPELINE[4][3:] == (True, True)
    assert DEFAULT_PIPELINE[5][3:] == (True, False)
