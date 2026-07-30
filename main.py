import os
import re
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

FINN_URL = os.getenv(
    "FINN_URL",
    "https://www.finn.no/mobility/search/car"
    "?price_to=200000"
    "&sales_form=1"
    "&sort=PUBLISHED_DESC"
)

CHECK_EVERY_SECONDS = 2

seen = set()


def get_ads():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/150.0.0.0 Safari/537.36"
        )
    }

    response = requests.get(
        FINN_URL,
        headers=headers,
        timeout=20
    )

    response.raise_for_status()

    ids = re.findall(
        r"/mobility/item/(\d+)",
        response.text
    )

    unique_ids = list(dict.fromkeys(ids))

    return unique_ids[:50]


def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )

    response.raise_for_status()


def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "BOT_TOKEN vai CHAT_ID nav uzstādīts Railway."
        )

    print("FINN Auto Alert startējas...", flush=True)

    # Startējot neko vecu nesūtām
    initial_ads = get_ads()
    seen.update(initial_ads)

    print(
        f"Sākumā atcerēti {len(initial_ads)} sludinājumi.",
        flush=True
    )

    send_telegram(
        "🚗 FINN Auto Alert palaists!\n\n"
        "Pārbaudu FINN ik pēc 2 sekundēm.\n"
        "Sūtu tikai jaunus sludinājumus.\n"
        "Cena līdz 200 000 kr."
    )

    while True:
        try:
            current_ads = get_ads()

            new_ads = [
                ad_id
                for ad_id in current_ads
                if ad_id not in seen
            ]

            for ad_id in reversed(new_ads):
                link = f"https://www.finn.no/mobility/item/{ad_id}"

                send_telegram(
                    "🚨 JAUNS FINN AUTO!\n\n"
                    f"{link}"
                )

                seen.add(ad_id)

            seen.update(current_ads)

            print(
                f"Pārbaudīts: {len(current_ads)} | "
                f"Jauni: {len(new_ads)}",
                flush=True
            )

        except Exception as error:
            print(
                f"Error: {error}",
                flush=True
            )

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
