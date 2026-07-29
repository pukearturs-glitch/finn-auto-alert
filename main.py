import os
import time
import re
import requests

FINN_URL = os.getenv(
    "FINN_URL",
    "https://www.finn.no/mobility/search/car?dealer_segment=3&price_to=150000&registration_class=1"
)

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_EVERY_SECONDS = 60
seen = set()


def get_ads():
    headers = {
        "User-Agent": "Mozilla/5.0 (compatible; FinnAutoAlert/1.0)"
    }

    response = requests.get(FINN_URL, headers=headers, timeout=20)
    response.raise_for_status()

    # Find FINN ad IDs in links
    ids = set(re.findall(r"/mobility/item/(\d+)", response.text))
    return ids


def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"

    response = requests.post(
        url,
        json={
            "chat_id": CHAT_ID,
            "text": message,
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    response.raise_for_status()


def main():
    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError("BOT_TOKEN or CHAT_ID is missing")

    global seen

    # First scan: remember existing ads without sending thousands of messages
    seen = get_ads()
    print(f"Started. Found {len(seen)} existing ads.")

    send_telegram(
        f"🚗 FINN Auto Alert ir palaists!\n"
        f"Sākumā atrasti {len(seen)} sludinājumi.\n"
        f"Tagad gaidu jaunus."
    )

    while True:
        try:
            current = get_ads()
            new_ads = current - seen

            for ad_id in new_ads:
                link = f"https://www.finn.no/mobility/item/{ad_id}"

                send_telegram(
                    "🚨 JAUNS FINN AUTO!\n\n"
                    f"{link}"
                )

            seen.update(current)

        except Exception as error:
            print(f"Error: {error}")

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
