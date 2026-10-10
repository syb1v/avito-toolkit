from collections.abc import Iterable


def orphan_account_names(
    listing_accounts: Iterable[str | None], existing_accounts: set[str]
) -> set[str]:
    return {
        account
        for account in listing_accounts
        if account is not None and account not in existing_accounts
    }
