#!/usr/bin/env python3
"""Demo cover and closing page for the quotations (Quote Builder).

    python tools/video_pipeline/make_assets.py

Writes assets/offerte_voorblad.pdf and assets/offerte_achterblad.pdf, which
seed_demo.py loads as the header and footer of every quotation. The
customer's name is stamped on the cover by tectora_quote_builder at 232 mm
from the top, so the cover leaves that band free.
"""

import os
import sys

from playwright.sync_api import sync_playwright

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(os.path.dirname(HERE))
LOGO = os.path.join(REPO, "tectora_report_layout", "static", "src", "img", "tectora_logo_white.svg")
BRAND = "#2D8D8F"

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<link href="https://fonts.googleapis.com/css2?family=Montserrat:wght@400;600;700&display=swap" rel="stylesheet">
<style>
  @page {{ size: A4; margin: 0; }}
  html, body {{ margin: 0; width: 210mm; height: 297mm; font-family: Montserrat, Arial, sans-serif; color: #1d2b2b; }}
  {css}
</style></head><body>{body}</body></html>"""

COVER_CSS = f"""
  .top {{ height: 150mm; background: {BRAND}; color: #fff; position: relative; overflow: hidden; }}
  .top svg {{ position: absolute; left: 22mm; top: 26mm; width: 92mm; height: auto; }}
  .roof {{ position: absolute; right: -10mm; bottom: -1mm; width: 150mm; height: 70mm;
           background: rgba(255,255,255,.12); clip-path: polygon(0 100%, 30% 35%, 100% 0, 100% 100%); }}
  .roof2 {{ position: absolute; right: -10mm; bottom: -1mm; width: 110mm; height: 40mm;
           background: rgba(255,255,255,.18); clip-path: polygon(0 100%, 25% 30%, 100% 0, 100% 100%); }}
  .title {{ position: absolute; left: 22mm; top: 82mm; font-size: 30pt; font-weight: 700; }}
  .sub {{ position: absolute; left: 22mm; top: 100mm; font-size: 13pt; font-weight: 400; opacity: .9; }}
  .intro {{ margin: 22mm 22mm 0; font-size: 11pt; line-height: 1.6; }}
  .for {{ position: absolute; left: 0; right: 0; top: 218mm; text-align: center; font-size: 10pt;
          letter-spacing: .2em; text-transform: uppercase; color: #6b7b7b; }}
  .bottom {{ position: absolute; left: 22mm; right: 22mm; bottom: 18mm; border-top: 2px solid {BRAND};
             padding-top: 4mm; font-size: 9pt; color: #4a5a5a; display: flex; justify-content: space-between; }}
"""

CLOSING_CSS = f"""
  .wrap {{ padding: 26mm 22mm; }}
  h1 {{ color: {BRAND}; font-size: 24pt; margin: 0 0 4mm; }}
  .lead {{ font-size: 11pt; line-height: 1.6; margin-bottom: 12mm; }}
  .grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 8mm; }}
  .card {{ border: 1.5px solid #d5e6e6; border-left: 6px solid {BRAND}; border-radius: 3mm; padding: 6mm; }}
  .card b {{ display: block; font-size: 12pt; margin-bottom: 2mm; }}
  .card span {{ font-size: 10pt; line-height: 1.5; color: #4a5a5a; }}
  .steps {{ margin-top: 14mm; }}
  .steps h2 {{ font-size: 14pt; color: {BRAND}; margin: 0 0 5mm; }}
  .step {{ display: flex; gap: 5mm; align-items: baseline; margin-bottom: 3.5mm; font-size: 10.5pt; }}
  .step i {{ font-style: normal; font-weight: 700; color: #fff; background: {BRAND}; border-radius: 50%;
             width: 7mm; height: 7mm; display: inline-flex; align-items: center; justify-content: center; flex: none; }}
  .foot {{ position: absolute; left: 22mm; right: 22mm; bottom: 18mm; text-align: center; font-size: 10pt;
           color: #4a5a5a; border-top: 2px solid {BRAND}; padding-top: 4mm; }}
"""


def cover(logo):
    return f"""
  <div class="top"><div class="roof"></div><div class="roof2"></div>{logo}
    <div class="title">Uw offerte</div>
    <div class="sub">Renovatie en nieuwbouw van platte daken</div></div>
  <div class="intro">Bedankt voor uw vertrouwen. In deze offerte vindt u de werken die wij voorstellen,
    per onderdeel en in de volgorde waarin wij ze uitvoeren, met een geschatte uitvoeringstijd.
    Opties kiest u zelf aan. Heeft u vragen? Uw contactpersoon helpt u graag verder.</div>
  <div class="for">Offerte voor</div>
  <div class="bottom"><span>Tectora — de kracht achter elk plat dak</span>
    <span>EPDM · roofing · isolatie · onderhoud · herstellingen</span></div>"""


def closing():
    cards = [
        ("Eén aanspreekpunt", "Van het plaatsbezoek tot de oplevering volgt één projectleider uw werf op."),
        ("Vaste ploegen", "Onze eigen ploegen werken elke dag op platte daken."),
        ("Duidelijke offerte", "Per werkpost, met de uren en een geschatte uitvoeringstijd."),
        ("Proper opgeleverd", "Afval en oude dakbedekking voeren wij af, de werf blijft net."),
    ]
    steps = [
        "U ondertekent de offerte online of op papier.",
        "Wij plannen de werken in en bestellen het materiaal.",
        "Onze ploeg voert de werken uit; u kan ze volgen.",
        "Samen overlopen we de werf bij de oplevering.",
    ]
    grid = "".join(f'<div class="card"><b>{t}</b><span>{d}</span></div>' for t, d in cards)
    flow = "".join(f'<div class="step"><i>{n}</i><span>{s}</span></div>' for n, s in enumerate(steps, 1))
    return f"""<div class="wrap"><h1>Waarom Tectora?</h1>
  <div class="lead">Een plat dak moet decennialang meegaan. Daarom werken wij met een vaste aanpak.</div>
  <div class="grid">{grid}</div>
  <div class="steps"><h2>Hoe gaat het verder?</h2>{flow}</div></div>
  <div class="foot">Tectora — de kracht achter elk plat dak</div>"""


def main(chromium=None):
    with open(LOGO, encoding="utf-8") as handle:
        logo = handle.read()
    out = os.path.join(HERE, "assets")
    os.makedirs(out, exist_ok=True)
    with sync_playwright() as pw:
        browser = pw.chromium.launch(**({"executable_path": chromium} if chromium else {}))
        page = browser.new_page()
        for name, css, body in (("offerte_voorblad", COVER_CSS, cover(logo)),
                                ("offerte_achterblad", CLOSING_CSS, closing())):
            page.set_content(PAGE.format(css=css, body=body), wait_until="networkidle")
            path = os.path.join(out, f"{name}.pdf")
            page.pdf(path=path, format="A4", print_background=True)
            print(path)
        browser.close()


if __name__ == "__main__":
    main(os.environ.get("CHROMIUM_PATH") or (sys.argv[1] if len(sys.argv) > 1 else None))
