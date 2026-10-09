from app.services.seller_filter import (
    ref_matches_seller,
    seller_filter_reason,
)


def test_ref_matches_seller_by_url_and_name() -> None:
    url = "https://www.avito.ru/user/98989ec06526358ac335c4d893f4ee35/profile"
    assert ref_matches_seller(url, name="FusionGear", url=url)
    assert ref_matches_seller("avito.ru/user/98989ec06526358ac335c4d893f4ee35", name=None, url=url)
    assert ref_matches_seller("98989ec06526358ac335c4d893f4ee35", name=None, url=url)
    assert not ref_matches_seller(
        "https://www.avito.ru/user/другой-хэш/profile", name=None, url=url
    )
    assert ref_matches_seller("fusi", name="FusionGear", url=None)
    assert ref_matches_seller("FusionGear Store", name="FusionGear", url=None)
    assert not ref_matches_seller("нет такого", name="FusionGear", url=None)
    assert not ref_matches_seller("", name="FusionGear", url=url)


def test_seller_filter_reason_targets_and_excludes() -> None:
    url = "https://www.avito.ru/user/aaaabbbbcccc/profile"
    assert seller_filter_reason(name="Target", url=url, target_refs=[], exclude_refs=[]) is None
    assert (
        seller_filter_reason(name="Target", url=url, target_refs=["target"], exclude_refs=[])
        is None
    )
    assert (
        seller_filter_reason(name="Other", url=url, target_refs=["target"], exclude_refs=[])
        == "not_target"
    )
    assert (
        seller_filter_reason(name="Target", url=url, target_refs=[], exclude_refs=["target"])
        == "excluded"
    )
    assert (
        seller_filter_reason(
            name="Target", url=url, target_refs=["target"], exclude_refs=["target"]
        )
        == "excluded"
    )
