from dataclasses import dataclass

from app.config import get_settings

API_BASE_URL = "https://api.avito.ru"
TOKEN_PATH = "/token"


class AvitoApiNotConfiguredError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class AvitoCredentials:
    client_id: str
    client_secret: str
    user_id: int | None = None


class AvitoApiClient:
    """Обёртка официального Avito Business API (контур A, фаза 5).

    Полный набор операций реализуется поверх SDK avito-py
    (дополнительная зависимость: pip install ".[avito-api]").
    """

    def __init__(self, credentials: AvitoCredentials) -> None:
        self._credentials = credentials

    @classmethod
    def from_settings(cls) -> "AvitoApiClient":
        settings = get_settings()
        if not settings.avito_client_id or not settings.avito_client_secret:
            raise AvitoApiNotConfiguredError(
                "AVITO_CLIENT_ID/AVITO_CLIENT_SECRET не заданы. "
                "Получить доступ: avito.ru/professionals/api"
            )
        return cls(
            AvitoCredentials(
                client_id=settings.avito_client_id,
                client_secret=settings.avito_client_secret,
                user_id=settings.avito_user_id,
            )
        )

    async def get_access_token(self) -> str:
        """OAuth2 client_credentials → access_token (реализация фазы 5)."""
        raise NotImplementedError("интеграция официального API — фаза 5")
