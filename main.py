import os
import re
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# Visa Norvēģija, visas markas
# Maks. cena: 200 000 NOK
# Min. gads: 1880
FINN_URL = os.getenv(
    "FINN_URL",
    "https://www.finn.no/mobility/search/car"
)

CHECK_EVERY_SECONDS = 60
MAX_PRICE = 200000
MIN_YEAR = 1880

seen = set()


def get_ads():
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        )
    }

    response = requests.get(FINN_URL, headers=headers, timeout=20)
    response.raise_for_status()

    # Atrodam FINN auto sludinājumu ID
    ids = re.findall(r"/mobility/item/(\d+)", response.text)

    # Saglabājam secību un noņemam dublikātus
    return list(dict.fromkeys(ids))


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
        raise RuntimeError("BOT_TOKEN vai CHAT_ID nav uzstādīts Railway.")

    # Startējot botu, esošos sludinājumus atceramies,
    # bet NESŪTĀM Telegram. Tādēļ vecie vairs nenāks.
    initial_ads = get_ads()
    seen.update(initial_ads)

    send_telegram(
        "🚗 FINN Auto Alert palaists!\n"
        "Skatos tikai jaunus sludinājumus pēc bota palaišanas.\n"
        "Cena līdz 200 000 kr • visa Norvēģija • visas markas."
    )

    while True:
        try:
            current_ads = get_ads()

            # reversed, lai jaunākos nosūtītu saprotamā secībā
            new_ads = [
                ad_id
                for ad_id in reversed(current_ads)
                if ad_id not in seen
            ]

            for ad_id in new_ads:
                link = f"https://www.finn.no/mobility/item/{ad_id}"

                send_telegram(
                    "🚨 JAUNS FINN AUTO!\n\n"
                    f"{link}"
                )

                seen.add(ad_id)

            # Atceramies arī pārējos pašreiz redzamos
            seen.update(current_ads)

        except Exception as error:
            print(f"Error: {error}", flush=True)

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
