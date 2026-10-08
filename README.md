# SEO Image Studio

Applicazione desktop per convertire immagini in WebP, ottimizzarle con reSmush.it e generare metadati SEO e testo alternativo con Gemini.

## Requisiti

- Python 3.10 o superiore
- Una chiave API Gemini per le funzioni AI (gratis, in caso chiedete a Luigi)

## Build locale

Clona il repository e crea un ambiente virtuale:

```bash
git clone https://github.com/juquiel/Seo-Image-Studio.git
cd Seo-Image-Studio
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Su Windows PowerShell usa `.venv\Scripts\Activate.ps1` al posto di `source .venv/bin/activate`.

Avvia l'applicazione durante lo sviluppo:

```bash
python index.py
```

Genera un eseguibile con PyInstaller:

```bash
python -m PyInstaller --noconfirm --clean --windowed --onefile --name "SEO Image Studio" index.py
```

## Configurazione API

La chiave Gemini viene salvata nel portachiavi del sistema tramite `keyring`. Non inserire mai chiavi API nel repository o nella workflow GitHub.
