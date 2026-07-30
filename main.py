import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

# FINN:
# - lietoti auto
# - līdz 200 000 NOK
# - tikai "Nye i dag"
# - jaunākie vispirms
FINN_URL = os.getenv(
    "FINN_URL",
    "https://www.finn.no/mobility/search/car"
    "?price_to=200000"
    "&sales_form=1"
    "&published=1"
    "&sort=PUBLISHED_DESC"
)

CHECK_EVERY_SECONDS = 2

NORWAY_TZ = ZoneInfo("Europe/Oslo")

session = requests.Session()

session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )
})

seen = set()

NORWEGIAN_MONTHS = {
    "januar": 1,
    "februar": 2,
    "mars": 3,
    "april": 4,
    "mai": 5,
    "juni": 6,
    "juli": 7,
    "august": 8,
    "september": 9,
    "oktober": 10,
    "november": 11,
    "desember": 12,
}


def norway_today():
    return datetime.now(NORWAY_TZ).date()


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

    unique_ids = list(dict.fromkeys(ids))

    return unique_ids[:100]


def parse_updated_date(text):
    match = re.search(
        r"Sist oppdatert\s+"
        r"(\d{1,2})\.\s+"
        r"([A-Za-zæøåÆØÅ]+)\s+"
        r"(\d{4})",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    day = int(match.group(1))
    month_name = match.group(2).lower()
    year = int(match.group(3))

    month = NORWEGIAN_MONTHS.get(month_name)

    if not month:
        return None

    return datetime(
        year,
        month,
        day,
        tzinfo=NORWAY_TZ
    ).date()


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

    # NOSAUKUMS
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
        r"Totalpris\s*([\d\s\xa0]+)\s*kr",
        r"Pris eksl\. omreg\.\s*([\d\s\xa0]+)\s*kr",
        r"Pris\s*([\d\s\xa0]+)\s*kr",
    ]

    for pattern in price_patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE
        )

        if match:
            number = match.group(1)
            number = number.replace("\xa0", " ")
            number = re.sub(r"\s+", " ", number).strip()

            price = f"{number} kr"
            break

    updated_date = parse_updated_date(text)

    return {
        "title": title,
        "price": price,
        "updated_date": updated_date,
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
        "FINN Auto Sniper startējas...",
        flush=True
    )

    # Visus sludinājumus, kas jau ir meklēšanā
    # starta brīdī, ignorējam.
    initial_ads = get_ads()

    seen.update(initial_ads)

    current_day = norway_today()

    print(
        f"Norvēģijas datums: {current_day}",
        flush=True
    )

    print(
        f"Startā ignorēti {len(initial_ads)} esošie sludinājumi.",
        flush=True
    )

    send_telegram(
        "✅ FINN Auto Sniper palaists!\n\n"
        "🔎 Pārbaude ik pēc 2 sekundēm\n"
        "📅 Tikai šodienas sludinājumi\n"
        "💰 Cena līdz 200 000 kr\n"
        "🇳🇴 Datums pēc Norvēģijas laika"
    )

    while True:
        try:
            today = norway_today()

            # Ja pienākusi jauna diena
            if today != current_day:

                print(
                    f"Jauna diena: {today}",
                    flush=True
                )

                current_day = today

                # Iztīrām seen, bet visus sludinājumus,
                # kas jau eksistē tieši pusnakts brīdī,
                # uzreiz iegaumējam un nesūtām.
                seen.clear()

                midnight_ads = get_ads()

                seen.update(midnight_ads)

            current_ads = get_ads()

            new_ads = [
                ad_id
                for ad_id in current_ads
                if ad_id not in seen
            ]

            # Uzreiz iegaumējam visus ID
            seen.update(current_ads)

            for ad_id in reversed(new_ads):

                try:
                    info = get_ad_info(ad_id)

                    # SVARĪGĀKAIS FILTRS:
                    # ja FINN datums nav ŠODIENA,
                    # Telegram neko nesūtām.
                    if info["updated_date"] != today:

                        print(
                            f"Ignorēts vecs sludinājums: "
                            f"{ad_id} | "
                            f"{info['updated_date']}",
                            flush=True
                        )

                        continue

                    message = (
                        "🚨 JAUNS FINN AUTO!\n\n"
                        f"🚗 {info['title']}\n"
                        f"💰 {info['price']}\n"
                        f"📅 {today.strftime('%d.%m.%Y')}\n\n"
                        f"{info['url']}"
                    )

                    send_telegram(message)

                    print(
                        f"NOSŪTĪTS: {ad_id} | "
                        f"{info['title']} | "
                        f"{info['price']}",
                        flush=True
                    )

                except Exception as ad_error:

                    print(
                        f"Kļūda sludinājumam "
                        f"{ad_id}: {ad_error}",
                        flush=True
                    )

        except requests.HTTPError as error:

            status = error.response.status_code

            print(
                f"FINN HTTP kļūda: {status}",
                flush=True
            )

            # Ja FINN sāk ierobežot pieprasījumus,
            # pagaidām mazliet ilgāk.
            if status in (403, 429):
                time.sleep(60)

        except Exception as error:

            print(
                f"Galvenā kļūda: {error}",
                flush=True
            )

        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
