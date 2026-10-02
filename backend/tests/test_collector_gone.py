from app.services.collector import should_mark_gone


def test_mark_gone_requires_successful_page() -> None:
    assert should_mark_gone(
        completed_pagination=True,
        pages_ok=1,
        stopped_by_challenge=False,
        rate_limited=False,
    )
    assert not should_mark_gone(
        completed_pagination=True,
        pages_ok=0,
        stopped_by_challenge=False,
        rate_limited=False,
    )


def test_block_never_marks_gone() -> None:
    assert not should_mark_gone(
        completed_pagination=True,
        pages_ok=2,
        stopped_by_challenge=True,
        rate_limited=False,
    )
    assert not should_mark_gone(
        completed_pagination=True,
        pages_ok=0,
        stopped_by_challenge=False,
        rate_limited=True,
    )
