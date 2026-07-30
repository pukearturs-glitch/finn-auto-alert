import os
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

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

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )
})

seen = set()


def get_ads():
    response = session.get(
        FINN_URL,
        timeout=20
    )

    response.raise_for_status()

    ids = re.findall(
        r"/mobility/item/(\d+)",
        response.text
    )

    return list(dict.fromkeys(ids))[:50]


def get_ad_info(ad_id):
    url = f"https://www.finn.no/mobility/item/{ad_id}"

    response = session.get(
        url,
        timeout=20
    )

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    # AUTO NOSAUKUMS
    title = "FINN auto"

    h1 = soup.find("h1")

    if h1:
        title = h1.get_text(
            " ",
            strip=True
        )

    # CENA
    price = "Cena nav atrasta"

    price_patterns = [
        r"Pris eksl\. omreg\.\s*([\d\s\xa0]+)\s*kr",
        r"Totalpris\s*([\d\s\xa0]+)\s*kr",
        r"Pris\s*([\d\s\xa0]+)\s*kr",
    ]

    for pattern in price_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            number = re.sub(
                r"\s+",
                " ",
                match.group(1).replace("\xa0", " ")
            ).strip()

            price = f"{number} kr"
            break

    # PĒDĒJĀ ATJAUNINĀŠANA
    updated = "Laiks nav atrasts"

    updated_match = re.search(
        r"Sist oppdatert\s+"
        r"(\d{1,2}\.\s+[A-Za-zæøåÆØÅ]+\s+\d{4},\s+\d{2}:\d{2})",
        text
    )

    if updated_match:
        updated = updated_match.group(1)

    return {
        "title": title,
        "price": price,
        "updated": updated,
        "url": url,
    }


def send_telegram(text):
    url = (
        f"https://api.telegram.org/"
        f"bot{BOT_TOKEN}/sendMessage"
    )

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

    print(
        "FINN Auto Alert startējas...",
        flush=True
    )

    # SVARĪGI:
    # visus sludinājumus, kas eksistē starta brīdī,
    # tikai iegaumējam un NESŪTĀM.
    initial_ads = get_ads()

    seen.update(initial_ads)

    print(
        f"Startā ignorēti {len(initial_ads)} esošie sludinājumi.",
        flush=True
    )

    send_telegram(
        "✅ FINN Auto Sniper palaists!\n\n"
        "🔎 Pārbaude ik pēc 2 sekundēm\n"
        "💰 Cena līdz 200 000 kr\n"
        "🚗 Sūtu tikai sludinājumus, kas parādās pēc šīs palaišanas."
    )

    while True:
        try:
            current_ads = get_ads()

            new_ads = [
                ad_id
                for ad_id in current_ads
                if ad_id not in seen
            ]

            # Uzreiz atzīmējam, lai vienu ID nevar nosūtīt divreiz
            seen.update(current_ads)

            for ad_id in reversed(new_ads):
                try:
                    info = get_ad_info(ad_id)

                    message = (
                        "🚨 JAUNS FINN AUTO!\n\n"
                        f"🚗 {info['title']}\n"
                        f"💰 {info['price']}\n"
                        f"🕒 {info['updated']}\n\n"
                        f"{info['url']}"
                    )

                    send_telegram(message)

                    print(
                        f"Nosūtīts: {ad_id} | "
                        f"{info['title']} | "
                        f"{info['price']}",
                        flush=True
                    )

                except Exception as ad_error:
                    print(
                        f"Kļūda sludinājumam {ad_id}: {ad_error}",
                        flush=True
                    )

            print(
                f"Pārbaudīts: {len(current_ads)} | "
                f"Jauni: {len(new_ads)}",
                flush=True
            )

        except Exception as error:
            print(
                f"Galvenā cikla kļūda: {error}",
                flush=True
            )

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
