import os
import re
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

CHECK_EVERY_SECONDS = 2
NORWAY_TZ = ZoneInfo("Europe/Oslo")

FINN_URL = (
    "https://www.finn.no/mobility/search/car"
    "?price_to=200000"
    "&sales_form=1"
    "&published=1"
    "&sort=PUBLISHED_DESC"
)

SENT_FILE = "sent_ids.txt"

session = requests.Session()
session.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/150.0.0.0 Safari/537.36"
    )
})


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


def load_sent_ids():
    if not os.path.exists(SENT_FILE):
        return set()

    with open(SENT_FILE, "r", encoding="utf-8") as f:
        return {
            line.strip()
            for line in f
            if line.strip()
        }


def save_sent_id(ad_id):
    with open(SENT_FILE, "a", encoding="utf-8") as f:
        f.write(ad_id + "\n")
        f.flush()


sent = load_sent_ids()


def get_ads():
    response = session.get(FINN_URL, timeout=20)
    response.raise_for_status()

    ids = re.findall(
        r"/mobility/item/(\d+)",
        response.text
    )

    return list(dict.fromkeys(ids))


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


def is_private_seller(text):
    text_lower = text.lower()

    # uzņēmuma/tirgotāja pazīmes
    dealer_markers = [
        "merkeforhandler",
        "bilforhandler",
        "forhandler",
        "organisasjonsnummer",
        "org.nr",
        "org nr",
    ]

    if any(marker in text_lower for marker in dealer_markers):
        return False

    # privātā pārdevēja pazīmes
    private_markers = [
        "privat",
        "privat selger",
    ]

    return any(marker in text_lower for marker in private_markers)


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
    private = is_private_seller(text)

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

    today = norway_today()

    # STARTĀ VISUS ŠODIENAS ESOŠOS SLUDINĀJUMUS
    # IEGAUMĒJAM UN NESŪTĀM
    initial_ads = get_ads()

    for ad_id in initial_ads:
        if ad_id not in sent:
            sent.add(ad_id)
            save_sent_id(ad_id)

    send_telegram(
        "✅ FINN Auto Sniper palaists!\n\n"
        "🔎 Pārbaude ik pēc 2 sekundēm\n"
        "👤 Tikai privātie pārdevēji\n"
        "📅 Tikai jauni šodienas sludinājumi\n"
        "💰 Cena līdz 200 000 kr"
    )

    current_day = today

    while True:
        try:
            today = norway_today()

            # ja sākusies jauna diena
            if today != current_day:
                current_day = today

                # pusnaktī visus tobrīd esošos iegaumējam,
                # lai nepienāk veci auto
                midnight_ads = get_ads()

                for ad_id in midnight_ads:
                    if ad_id not in sent:
                        sent.add(ad_id)
                        save_sent_id(ad_id)

            current_ads = get_ads()

            for ad_id in current_ads:

                if ad_id in sent:
                    continue

                # REZERVĒJAM PIRMS apstrādes
                # lai vienu ID nevar paņemt 2x
                sent.add(ad_id)
                save_sent_id(ad_id)

                try:
                    info = get_ad_info(ad_id)

                    # tikai šodien
                    if info["updated_date"] != today:
                        print(
                            f"Ignorēts vecs: {ad_id}",
                            flush=True
                        )
                        continue

                    # tikai privātie
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
