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

BASE_URL = "https://www.finn.no/mobility/search/car"

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


def norway_today():
    return datetime.now(NORWAY_TZ).date()


def build_search_url(page=1):
    return (
        f"{BASE_URL}"
        f"?price_to=200000"
        f"&sales_form=1"
        f"&published=1"
        f"&sort=PUBLISHED_DESC"
        f"&page={page}"
    )


def get_page_ads(page):
    url = build_search_url(page)

    response = session.get(url, timeout=20)
    response.raise_for_status()

    ids = re.findall(
        r"/mobility/item/(\d+)",
        response.text
    )

    return list(dict.fromkeys(ids))


def get_all_today_ads():
    all_ids = []
    known = set()

    # FINN dokumentācija norāda līdz 50 lapām.
    for page in range(1, 51):
        ids = get_page_ads(page)

        if not ids:
            break

        new_on_page = [
            ad_id
            for ad_id in ids
            if ad_id not in known
        ]

        if not new_on_page:
            break

        for ad_id in new_on_page:
            known.add(ad_id)
            all_ids.append(ad_id)

        print(
            f"Starta scan: lapa {page}, kopā {len(all_ids)}",
            flush=True
        )

        # Nedaudz saudzējam FINN startup laikā
        time.sleep(0.3)

    return all_ids


def get_latest_ads():
    latest = []

    # Ikdienas darbībā pārbaudām tikai pirmās 2 lapas,
    # jo tās ir sakārtotas PUBLISHED_DESC.
    for page in (1, 2):
        ids = get_page_ads(page)

        for ad_id in ids:
            if ad_id not in latest:
                latest.append(ad_id)

    return latest


def is_private_seller(text):
    text_lower = text.lower()

    # Meklējam sludinājuma pārdevēja tipu.
    # FINN rezultātos privātie tiek atzīmēti kā "Privat".
    if "merkeforhandler" in text_lower:
        return False

    if "forhandler" in text_lower:
        return False

    if "privat" in text_lower:
        return True

    # Ja nevaram droši noteikt, nesūtām.
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

    private = is_private_seller(text)

    return {
        "title": title,
        "price": price,
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


def initialize_today():
    print(
        "Skenēju VISUS jau esošos šodienas sludinājumus...",
        flush=True
    )

    existing = get_all_today_ads()

    seen.update(existing)
    sent.update(existing)

    print(
        f"Startā iegaumēti {len(existing)} sludinājumi.",
        flush=True
    )


def main():
    global seen, sent

    if not BOT_TOKEN or not CHAT_ID:
        raise RuntimeError(
            "BOT_TOKEN vai CHAT_ID nav uzstādīts Railway."
        )

    current_day = norway_today()

    # SVARĪGĀKAIS:
    # palaišanas brīdī iegaumējam VISUS šodien jau esošos.
    initialize_today()

    send_telegram(
        "✅ FINN Auto Sniper palaists!\n\n"
        "🔎 Pārbaude ik pēc 2 sekundēm\n"
        "👤 Tikai privātie pārdevēji\n"
        "💰 Cena līdz 200 000 kr\n"
        "🚗 Sūtu tikai tos, kas parādās pēc bota palaišanas"
    )

    while True:
        try:
            today = norway_today()

            # Ja Norvēģijā sākusies jauna diena
            if today != current_day:
                current_day = today

                seen.clear()
                sent.clear()

                # Pusnaktī iegaumējam visu, kas jau ir rezultātos,
                # lai nekas vecs neuzpeld vēlāk.
                initialize_today()

            current_ads = get_latest_ads()

            new_ads = [
                ad_id
                for ad_id in current_ads
                if ad_id not in seen
                and ad_id not in sent
            ]

            # Visus pašreiz redzamos iegaumējam
            seen.update(current_ads)

            for ad_id in reversed(new_ads):
                try:
                    # Rezervējam PIRMS sūtīšanas
                    sent.add(ad_id)

                    info = get_ad_info(ad_id)

                    if not info["private"]:
                        print(
                            f"Ignorēts ne-privāts: {ad_id}",
                            flush=True
                        )
                        continue

                    message = (
                        "🚨 JAUNS FINN AUTO!\n\n"
                        f"🚗 {info['title']}\n"
                        f"💰 {info['price']}\n"
                        f"👤 Privāts pārdevējs\n\n"
                        f"{info['url']}"
                    )

                    send_telegram(message)

                    print(
                        f"NOSŪTĪTS: {ad_id}",
                        flush=True
                    )

                except Exception as ad_error:
                    print(
                        f"Kļūda sludinājumam {ad_id}: {ad_error}",
                        flush=True
                    )

        except requests.HTTPError as error:
            status = error.response.status_code

            print(
                f"FINN HTTP kļūda: {status}",
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
