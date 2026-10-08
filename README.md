# SEO Image Studio

Applicazione desktop per convertire immagini in WebP, ottimizzarle con reSmush.it e generare metadati SEO e testo alternativo con Gemini.

## Requisiti

- Python 3.10 o superiore
- Una chiave API Gemini per le funzioni AI

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

Su Windows è disponibile anche `build_windows.bat`. Il risultato si trova nella cartella `dist/`.

Su macOS puoi usare lo stesso comando; il build deve essere eseguito su macOS e produce `SEO Image Studio.app`, compatibile con l'architettura della macchina. Per Linux usa lo stesso comando su una macchina Linux. PyInstaller non è un cross-compiler.

## Build da GitHub Actions

La workflow `Build` compila automaticamente Windows e macOS quando crei un tag con prefisso `v`, ad esempio:

```bash
git tag v1.0.0
git push origin v1.0.0
```

Gli eseguibili vengono allegati alla release GitHub. Gli utenti possono anche scaricare il codice sorgente e seguire la sezione `Build locale`.

## Configurazione API

La chiave Gemini viene salvata nel portachiavi del sistema tramite `keyring`. Non inserire mai chiavi API nel repository o nella workflow GitHub.
