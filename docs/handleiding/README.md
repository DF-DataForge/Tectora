# Handleiding Tectora Dakmeting

Bron van de drie handleidingen in `..`: `Tectora_Dakmeting_Handleiding_NL.pdf`,
`Tectora_Dakmeting_Manual_EN.pdf` en `Tectora_Dakmeting_Manuali_SQ.pdf`.

```
pip install reportlab
python3 build_manual.py nl ../Tectora_Dakmeting_Handleiding_NL.pdf
python3 build_manual.py en ../Tectora_Dakmeting_Manual_EN.pdf
python3 build_manual.py sq ../Tectora_Dakmeting_Manuali_SQ.pdf
```

* `content_nl.py`, `content_en.py`, `content_sq.py`: de hoofdstukken per taal;
* `flows.py`: het hoofdstuk met de twee werkwijzen en de best practice voor het schalen;
* `dataforge_logo.png`: het Data Forge-logo op omslag en koptekst.

Gebruikt DejaVu Sans (`/usr/share/fonts/truetype/dejavu`).
