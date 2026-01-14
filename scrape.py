import csv
import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone

URL = "https://www.medscinet.com/Belport/default.aspx?lan=1&avd=6"


def fetch_html(url: str) -> str:
    r = requests.get(url, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    return r.text


def _clean(s: str) -> str:
    return " ".join((s or "").replace("\u200b", "").replace("\ufeff", "").split()).strip()


def parse_units_from_html(html: str) -> list[dict]:
    """
    Robust parsing based on the table structure you showed:

    - Unit name is in the <tr> above the "Geriatrik:" row:
        <span class="dataheader">Löwetgeriatriken</span>

    - The "Geriatrik:" row has four <td>:
        td[0] = "Geriatrik:"
        td[1] = disponibla
        td[2] = lediga
        td[3] = väntande

    - "Uppdaterad:" and "Meddelande:" (if present) are in rows between the unit row and the "Geriatrik:" row.
    """
    soup = BeautifulSoup(html, "html.parser")
    out = []
    seen = set()

    # Find all cells that are exactly "Geriatrik:" (these belong to the capacity row)
    for ger_td in soup.find_all("td", id="rightSide"):
        if _clean(ger_td.get_text()) != "Geriatrik:":
            continue

        ger_tr = ger_td.find_parent("tr")
        if not ger_tr:
            continue

        tds = ger_tr.find_all("td", recursive=False)
        if len(tds) < 4:
            # Sometimes extra wrappers exist; fall back to recursive
            tds = ger_tr.find_all("td")
        if len(tds) < 4:
            continue

        disponibla = _clean(tds[1].get_text())
        lediga = _clean(tds[2].get_text())
        vantande = _clean(tds[3].get_text())

        # Unit row is the previous <tr> sibling that has span.dataheader
        unit_tr = ger_tr.find_previous_sibling("tr")
        while unit_tr:
            if unit_tr.find("span", class_="dataheader"):
                break
            unit_tr = unit_tr.find_previous_sibling("tr")

        if not unit_tr:
            continue

        unit_span = unit_tr.find("span", class_="dataheader")
        unit_name = _clean(unit_span.get_text()) if unit_span else ""
        if not unit_name:
            continue

        # ---- Hämta "Uppdaterad:" och "Meddelande:" EFTER Geriatrik-raden ----
        updated = ""
        message = ""
        next_row = tr_capacity.find_next_sibling("tr")
        while next_row:
            # Stoppa om vi nått nästa kapacitetsrad (id="rightSide" + text "Geriatrik:")
            cap_cell = next_row.find("td", id="rightSide")
            if cap_cell and _clean(cap_cell.get_text()) == "Geriatrik:":
                break

            text = _clean(next_row.get_text(" ", strip=True))
            if text.startswith("Uppdaterad:"):
                updated = _clean(text.split("Uppdaterad:", 1)[1])
            elif text.startswith("Meddelande:"):
                message = _clean(text.split("Meddelande:", 1)[1])

            next_row = next_row.find_next_sibling("tr")


        # Avoid duplicates if the page contains repeated structures
        key = (unit_name, updated, lediga, vantande, message)
        if key in seen:
            continue
        seen.add(key)

        out.append(
            {
                "Geriatrikenhet": unit_name,
                "Uppdaterad senast": updated,
                "Lediga vårdplatser": lediga,
                "Väntande godkända remisser": vantande,
                "Meddelande": message,
            }
        )

    # Stable ordering
    out.sort(key=lambda r: r["Geriatrikenhet"])
    return out


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
    html = fetch_html(URL)
    rows = parse_units_from_html(html)
    write_outputs(rows)


if __name__ == "__main__":
    main()

