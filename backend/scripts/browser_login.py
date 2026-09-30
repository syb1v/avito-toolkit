"""Ручное прохождение антибот-проверки Авито и сохранение браузерного профиля.

Открывает видимое окно полного Chromium с постоянным профилем. Решите капчу
(если появилась) — скрипт сам определит, что проверка пройдена, сделает прогрев
и сохранит cookies в профиле. Дальше Level 2 (воркер/скрипты) использует этот
профиль через BROWSER_USER_DATA_DIR.

Запуск из каталога backend/:

    .venv/bin/python scripts/browser_login.py
    .venv/bin/python scripts/browser_login.py --url "https://www.avito.ru/moskva/telefony?q=iphone+15"
"""

import argparse
import asyncio
import time
from pathlib import Path

from app.config import get_settings

DEFAULT_PROFILE_DIR = ".browser-profile"
DEFAULT_URL = "https://www.avito.ru/"
CHECK_INTERVAL_SECONDS = 2.0
CLEAN_CHECKS_TO_WIN = 3
TIMEOUT_SECONDS = 600
CHALLENGE_MARKERS = ("firewallcaptcha", "hcaptcha", "доступ ограничен", "проверка безопасности")


async def _is_challenge(page) -> bool:
    html = await page.content()
    lowered = html.lower()
    return any(marker in lowered for marker in CHALLENGE_MARKERS)


async def _run(url: str, profile_dir: str) -> int:
    from patchright.async_api import async_playwright

    settings = get_settings()
    channel = settings.browser_channel or "chromium"
    Path(profile_dir).mkdir(parents=True, exist_ok=True)

    async with async_playwright() as playwright:
        context = await playwright.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            channel=channel,
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            viewport={"width": 1440, "height": 900},
        )
        page = context.pages[0] if context.pages else await context.new_page()
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        print(f"Профиль: {Path(profile_dir).resolve()}")
        print("Если видите проверку — пройдите её в открытом окне (капча/галочка).")
        print("Окно закроется автоматически после прохождения (максимум 10 минут).")

        deadline = time.monotonic() + TIMEOUT_SECONDS
        clean_checks = 0
        while time.monotonic() < deadline:
            try:
                if await _is_challenge(page):
                    clean_checks = 0
                    print("... проверка ещё не пройдена", end="\r", flush=True)
                else:
                    clean_checks += 1
                    print(
                        f"... проверки нет, фиксирую сессию ({clean_checks}/{CLEAN_CHECKS_TO_WIN})",
                        end="\r",
                        flush=True,
                    )
                    if clean_checks >= CLEAN_CHECKS_TO_WIN:
                        break
            except Exception:
                clean_checks = 0
            await asyncio.sleep(CHECK_INTERVAL_SECONDS)

        if clean_checks >= CLEAN_CHECKS_TO_WIN:
            try:
                await page.goto(
                    "https://www.avito.ru/", wait_until="domcontentloaded", timeout=60000
                )
                await asyncio.sleep(2)
            except Exception:
                pass
            print("\nПроверка пройдена, профиль сохранён.")
            result = 0
        else:
            print("\nТаймаут: проверка не пройдена, профиль не сохранён.")
            result = 1
        await context.close()
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Avito browser login / profile warmup")
    parser.add_argument("--url", default=DEFAULT_URL)
    parser.add_argument("--profile", default=None, help="каталог профиля")
    args = parser.parse_args()
    settings = get_settings()
    profile_dir = args.profile or settings.browser_user_data_dir or DEFAULT_PROFILE_DIR
    return asyncio.run(_run(args.url, profile_dir))


if __name__ == "__main__":
    raise SystemExit(main())
