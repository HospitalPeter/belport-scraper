import re
import csv
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

URL = "https://www.medscinet.com/Belport/default.aspx?lan=1&avd=6"

# Mönster på sidan:
# Enhetsnamn följs typiskt av "Tel:" på nästa rad
UPD_RE = re.compile(r"^Uppdaterad:\s*(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2})$")
GER_RE = re.compile(r"^Geriatrik:\s*(\d+)\s+(-?\d+)(?:\s+(\d+))?.*$")  # dispo, lediga, väntande?
MSG_RE = re.compile(r"^Meddelande:\s*(.*)$")

def fetch_lines() -> list[str]:
    r = requests.get(URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")
    text = soup.get_text("\n", strip=True)
    return [ln.strip() for ln in text.split("\n") if ln.strip()]

def parse_units(lines: list[str]) -> list[dict]:
    rows: list[dict] = []
    current: dict | None = None

    for i, ln in enumerate(lines):
        # Start på ny enhet: rad som följs av Tel:
        if i + 1 < len(lines) and lines[i + 1].startswith("Tel:"):
            # Spara föregående enhet om den finns
            if current:
                rows.append(current)
            current = {
                "Geriatrikenhet": ln,
                "Uppdaterad senast": "",
                "Lediga vårdplatser": "",
                "Väntande godkända remisser": "",
                "Meddelande": "",
            }
            continue

        if not current:
            continue

        m = UPD_RE.match(ln)
        if m:
            current["Uppdaterad senast"] = m.group(1)
            continue

        m = GER_RE.match(ln)
        if m:
            # dispo = m.group(1) (inte efterfrågad)
            current["Lediga vårdplatser"] = m.group(2)
            current["Väntande godkända remisser"] = m.group(3) if m.group(3) is not None else "0"
            continue

        m = MSG_RE.match(ln)
        if m:
            current["Meddelande"] = m.group(1).strip()
            continue

    if current:
        rows.append(current)

    # Filtrera bort uppenbart felmatchade "enheter" (säkerhetsnät)
    rows = [r for r in rows if r["Geriatrikenhet"] and len(r["Geriatrikenhet"]) > 3]
    return rows

def write_outputs(rows: list[dict]) -> None:
    # Sortera för stabil output
    rows = sorted(rows, key=lambda x: x["Geriatrikenhet"])

    # CSV (enkelt att öppna i Excel)
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

    # JSON (enkelt för andra system)
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
