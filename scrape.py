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
    # Ta bort “zero-width” och BOM, och gör ALL whitespace till enkla mellanslag
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

    i = 0
    while i < len(lines):
        ln = lines[i]

        # Ny enhet = en rad vars "nästa 1–3 rader" innehåller Tel:
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
            i += 1
            continue

        if current:
            m = GER_RE.match(ln)
            if m:
                current["Lediga vårdplatser"] = m.group(2)
                current["Väntande godkända remisser"] = m.group(3) if m.group(3) is not None else "0"
                i += 1
                continue

            m = UPD_RE.match(ln)
            if m:
                current["Uppdaterad senast"] = m.group(1)
                i += 1
                continue

            m = MSG_RE.match(ln)
            if m:
                current["Meddelande"] = m.group(1).strip()
                i += 1
                continue

        i += 1

    if current:
        rows.append(current)

    # Stabil sortering
    rows = sorted(rows, key=lambda x: x["Geriatrikenhet"])
    return rows

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
