import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

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
sent = set()

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
    response = session.get(FINN_URL, timeout=20)
    response.raise_for_status()

    ids = re.findall(
        r"/mobility/item/(\d+)",
        response.text
    )

    return list(dict.fromkeys(ids))[:100]


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


def is_private_seller(soup, text):
    text_lower = text.lower()

    # Ja lapā skaidri redzam tirgotāja pazīmes, ignorējam.
    dealer_markers = [
        "forhandler",
        "org.nr",
        "organisasjonsnummer",
        "bedrift",
        "bilforhandler",
    ]

    if any(marker in text_lower for marker in dealer_markers):
        return False

    # FINN privātajiem sludinājumiem parasti ir Privat/Privat selger pazīmes.
    private_markers = [
        "privat selger",
        "privat",
    ]

    if any(marker in text_lower for marker in private_markers):
        return True

    # Ja nav iespējams droši noteikt, NESŪTĀM.
    return False


def get_ad_info(ad_id):
    url = f"https://www.finn.no/mobility/item/{ad_id}"

    response = session.get(url, timeout=20)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text = soup.get_text(" ", strip=True)

    title = "FINN auto"

    h1 = soup.find("h1")
    if h1:
        title = h1.get_text(" ", strip=True)

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
    private = is_private_seller(soup, text)

    return {
        "title": title,
        "price": price,
        "updated_date": updated_date,
        "private": private,
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

    initial_ads = get_ads()

    seen.update(initial_ads)
    sent.update(initial_ads)

    current_day = norway_today()

    send_telegram(
        "✅ FINN Auto Sniper palaists!\n\n"
        "🔎 Pārbaude ik pēc 2 sekundēm\n"
        "👤 Tikai privātie pārdevēji\n"
        "📅 Tikai šodienas sludinājumi\n"
        "💰 Cena līdz 200 000 kr"
    )

    while True:
        try:
            today = norway_today()

            if today != current_day:
                current_day = today

                seen.clear()
                sent.clear()

                midnight_ads = get_ads()

                seen.update(midnight_ads)
                sent.update(midnight_ads)

            current_ads = get_ads()

            new_ads = [
                ad_id
                for ad_id in current_ads
                if ad_id not in seen
                and ad_id not in sent
            ]

            seen.update(current_ads)

            for ad_id in reversed(new_ads):
                try:
                    # REZERVĒJAM ID PIRMS jebkādas sūtīšanas.
                    # Tas neļauj tam pašam ID aiziet 2x.
                    sent.add(ad_id)

                    info = get_ad_info(ad_id)

                    # Tikai šodienas
                    if info["updated_date"] != today:
                        print(
                            f"Ignorēts datums: {ad_id} | "
                            f"{info['updated_date']}",
                            flush=True
                        )
                        continue

                    # Tikai privātie
                    if not info["private"]:
                        print(
                            f"Ignorēts tirgotājs: {ad_id}",
                            flush=True
                        )
                        continue

                    message = (
                        "🚨 JAUNS FINN AUTO!\n\n"
                        f"🚗 {info['title']}\n"
                        f"💰 {info['price']}\n"
                        f"👤 Privāts pārdevējs\n"
                        f"📅 {today.strftime('%d.%m.%Y')}\n\n"
                        f"{info['url']}"
                    )

                    send_telegram(message)

                    print(
                        f"NOSŪTĪTS: {ad_id}",
                        flush=True
                    )

                except Exception as ad_error:
                    print(
                        f"Kļūda {ad_id}: {ad_error}",
                        flush=True
                    )

        except requests.HTTPError as error:
            status = error.response.status_code

            print(
                f"HTTP kļūda: {status}",
                flush=True
            )

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
