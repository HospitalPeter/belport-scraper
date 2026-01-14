import re
import csv
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

URL = "https://www.medscinet.com/Belport/default.aspx?lan=1&avd=6"

UPD_RE = re.compile(r"^Uppdaterad:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})$")
# dispo, lediga, väntande (väntande kan saknas)
GER_RE = re.compile(r"^Geriatrik:\s*(\d+)\s+(-?\d+)(?:\s+(\d+))?")
MSG_RE = re.compile(r"^Meddelande:\s*(.*)$")

def normalize(s: str) -> str:
    # gör ALL whitespace normal + ta bort osynliga tecken
    s = s.replace("\u200b", "").replace("\ufeff", "")
    s = re.sub(r"\s+", " ", s, flags=re.UNICODE).strip()
    return s

def fetch_lines() -> list[str]:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)

    lines = []
    for ln in text.split("\n"):
        ln = normalize(ln)
        if ln:
            lines.append(ln)
    return lines

def next_nonempty(lines: list[str], start: int, max_ahead: int = 3) -> str | None:
    # Leta efter nästa rad inom några steg (för att hantera ibland tomrad mellan namn och Tel:)
    for j in range(start, min(len(lines), start + max_ahead + 1)):
        if lines[j]:
            return lines[j]
    return None

def parse_units(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None
    numbers_done = False  # flagga för varje enhet

    i = 0
    while i < len(lines):
        ln = lines[i]

        # Ny enhet om nästa rad (inom 3 rader) börjar med Tel:
        look = next_nonempty(lines, i + 1, max_ahead=3)
        if look and look.startswith("Tel:"):
            if current:
                rows.append(current)
            current = {
                "Geriatrikenhet": ln,
                "Uppdaterad senast": "",
                "Lediga vårdplatser": "",
                "Väntande godkända remisser": "",
                "Meddelande": "",
            }
            numbers_done = False
            i += 1
            continue

        if current:
            # Hoppa över uppdaterad- och meddelande-rader
            if ln.startswith("Uppdaterad:"):
                m = UPD_RE.match(ln)
                if m:
                    current["Uppdaterad senast"] = m.group(1)
                i += 1
                continue
            if ln.startswith("Meddelande:"):
                current["Meddelande"] = ln.split(":", 1)[1].strip()
                i += 1
                continue

            # Hoppa över övriga hjälprader
            skip_keywords = ("Tel:", "Jourtid", "Geografiskt", "Geriatrik:", "Enhet", "Prio")
            if any(k in ln for k in skip_keywords):
                i += 1
                continue

            # Hitta talraden, men bara om vi inte redan sparat siffror för enheten
            if not numbers_done:
                # extrahera heltal
                nums = [int(x) for x in re.findall(r"-?\d+", ln) if abs(int(x)) < 1000]
                # om minst två små tal: (disponibla, lediga [, väntande])
                if len(nums) >= 2:
                    current["Lediga vårdplatser"] = str(nums[1])
                    current["Väntande godkända remisser"] = str(nums[2]) if len(nums) > 2 else "0"
                    numbers_done = True
                    i += 1
                    continue

        i += 1

    if current:
        rows.append(current)

    return sorted(rows, key=lambda x: x["Geriatrikenhet"])
def write_outputs(rows: list[dict]) -> None:
    with open("latest.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "Geriatrikenhet",
                "Uppdaterad senast",
                "Lediga vårdplatser",
                "Väntande godkända remisser",
                "Meddelande",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    payload = {
        "source_url": URL,
        "scraped_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "rows": rows,
    }
    with open("latest.json", "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)

def main():
    lines = fetch_lines()
    rows = parse_units(lines)
    write_outputs(rows)

if __name__ == "__main__":
    main()
