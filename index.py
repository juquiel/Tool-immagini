"""SEO Image Studio: conversione WebP, reSmush.it e metadati SEO."""
import base64
import io
import json
import os
import re
import threading
import time
from tkinter import StringVar, filedialog, messagebox

import customtkinter as ctk
from PIL import Image

try:
	import requests
except ImportError:
	requests = None

try:
	import keyring
except ImportError:
	keyring = None


_gemini_models = {}
KEYRING_SERVICE = "SEO Image Studio"
KEYRING_USER = "Gemini API key"


def load_saved_api_key():
	if keyring is None:
		return ""
	try:
		return keyring.get_password(KEYRING_SERVICE, KEYRING_USER) or ""
	except Exception:
		return ""


def save_api_key(api_key):
	if keyring is None:
		return False
	try:
		keyring.set_password(KEYRING_SERVICE, KEYRING_USER, api_key)
		return True
	except Exception:
		return False


def make_seo_data(filename):
	name = os.path.splitext(os.path.basename(filename))[0]
	name = re.sub(r"[_\-.]+", " ", name)
	name = re.sub(r"\b(img|image|dsc|foto|photo|screenshot)\b", "", name, flags=re.I)
	name = re.sub(r"\s+", " ", name).strip()
	title = (name.title() or "Immagine")[:80]
	return title, f"{title} - immagine"[:125]


def clean_alt_text(text):
	"""Riduce la risposta del modello a una sola frase SEO utilizzabile."""
	lines = [re.sub(r"^[\s>*•\-]+", "", line).strip() for line in text.splitlines()]
	lines = [line for line in lines if line]
	for line in reversed(lines):
		line = re.sub(r"^(alt text|alt|descrizione)\s*:\s*", "", line, flags=re.I)
		if not re.match(r"^(task|constraints?|only the alt text|maximum|max)\s*:", line, re.I):
			return line.strip('"`')[:125]
	return ""


def get_gemini_models(api_key):
	configured = os.environ.get("GEMINI_MODEL")
	if configured:
		return [configured.removeprefix("models/")]
	if api_key in _gemini_models:
		return _gemini_models[api_key]
	response = requests.get(
		"https://generativelanguage.googleapis.com/v1beta/models",
		headers={"x-goog-api-key": api_key},
		timeout=30,
	)
	response.raise_for_status()
	available = []
	for model in response.json().get("models", []):
		name = model["name"].removeprefix("models/")
		unsupported_for_images = (
			"tts", "embedding", "imagen", "aqa", "preview", "gemma", "learnlm", "robotics"
		)
		if "generateContent" in model.get("supportedGenerationMethods", []) and not any(
			term in name.lower() for term in unsupported_for_images
		):
			available.append(name)
	if not available:
		raise RuntimeError("Nessun modello Gemini abilitato per questa chiave API")
	preferences = ("gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash")
	ordered = [model for model in preferences if model in available]
	ordered.extend(model for model in available if model not in ordered)
	_gemini_models[api_key] = ordered
	return ordered


def make_gemini_alt(path, api_key=None, article_title=""):
	"""Genera un alt text breve analizzando l'immagine con Gemini."""
	if requests is None:
		raise RuntimeError("Installa requests per usare Gemini")
	api_key = api_key or os.environ.get("GEMINI_API_KEY")
	if not api_key:
		raise RuntimeError("Variabile GEMINI_API_KEY non configurata")
	with Image.open(path) as image:
		image.thumbnail((1024, 1024), Image.Resampling.LANCZOS)
		buffer = io.BytesIO()
		image.convert("RGB").save(buffer, format="JPEG", quality=80, optimize=True)
	encoded_image = base64.b64encode(buffer.getvalue()).decode("ascii")
	context = (
		f" Il titolo dell'articolo è: {article_title}. Usa questo contesto per scegliere "
		"il lessico più pertinente, ma non inventare dettagli non visibili."
		if article_title else ""
	)
	request_data = {
		"contents": [{"parts": [
			{"text": (
				"Osserva l'immagine e scrivi una sola frase di testo alternativo SEO "
				"in italiano. Descrivi esclusivamente ciò che è visibile. "
				"Non scrivere istruzioni, spiegazioni, elenchi o etichette, ma includi il titolo dell'articolo. "
				"Rispondi solo con la frase, senza virgolette, massimo 125 caratteri."
				+ context
			)},
			{"inline_data": {"mime_type": "image/jpeg", "data": encoded_image}},
		]}],
		"generationConfig": {"temperature": 0.15, "maxOutputTokens": 256},
	}
	last_response = None
	for model in get_gemini_models(api_key):
		for attempt in range(3):
			response = requests.post(
				f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
				headers={"x-goog-api-key": api_key},
				json=request_data,
				timeout=180,
			)
			if response.status_code in (400, 404):
				last_response = response
				break
			if response.status_code in (429, 500, 502, 503, 504):
				last_response = response
				if attempt < 2:
					time.sleep(2 ** attempt)
					continue
				break
			break
		if response.status_code in (400, 404, 429, 500, 502, 503, 504):
			continue
		response.raise_for_status()
		data = response.json()
		candidates = data.get("candidates", [])
		if not candidates:
			feedback = data.get("promptFeedback", {}).get("blockReason", "risposta vuota")
			raise RuntimeError(f"Gemini ha bloccato la risposta: {feedback}")
		parts = candidates[0].get("content", {}).get("parts", [])
		text = "\n".join(part.get("text", "") for part in parts if part.get("text"))
		if not text:
			finish_reason = candidates[0].get("finishReason", "contenuto mancante")
			if finish_reason == "MAX_TOKENS":
				raise RuntimeError("Gemini ha raggiunto il limite token senza testo")
			raise RuntimeError(f"Gemini non ha restituito testo: {finish_reason}")
		alt = clean_alt_text(text)
		if not alt:
			raise RuntimeError("Gemini non ha restituito un alt text")
		return alt[:125]
	if last_response is not None:
		try:
			details = last_response.json().get("error", {}).get("message", "")
		except ValueError:
			details = last_response.text[:300]
		raise RuntimeError(
			f"Nessun modello Gemini vision invocabile (HTTP {last_response.status_code}): {details}"
		)
	raise RuntimeError("Gemini non ha restituito un modello utilizzabile")


def optimize_with_resmush(path):
	if requests is None:
		raise RuntimeError("Installa requests con: pip install requests")
	with open(path, "rb") as source:
		result = requests.post(
			"https://api.resmush.it/ws.php",
			files={"files[]": (os.path.basename(path), source, "image/webp")},
			timeout=120,
		)
	result.raise_for_status()
	url = result.json().get("dest")
	if not url:
		return False
	optimized = requests.get(url, timeout=120)
	optimized.raise_for_status()
	with open(path, "wb") as target:
		target.write(optimized.content)
	return True


def compression_stats(original_size, optimized_size):
	saved_bytes = max(0, original_size - optimized_size)
	percent = (saved_bytes / original_size * 100) if original_size else 0
	return percent, saved_bytes / (1024 * 1024)


class ImageApp(ctk.CTk):
	def __init__(self):
		super().__init__()
		ctk.set_appearance_mode("dark")
		ctk.set_default_color_theme("blue")
		self.title("SEO Image Studio")
		self.geometry("980x720")
		self.minsize(760, 560)
		self.files = []
		self.cards = []
		self.output = StringVar(value=os.path.expanduser("~/Desktop/webp"))
		self.prefix = StringVar(value="immagine")
		self.article_title = StringVar()
		saved_api_key = load_saved_api_key()
		self.api_key = StringVar(value=os.environ.get("GEMINI_API_KEY", "") or saved_api_key)
		self.remember_key = ctk.BooleanVar(value=bool(saved_api_key))
		self.status = StringVar(value="Seleziona le immagini da elaborare")
		self.build_ui()

	def build_ui(self):
		root = ctk.CTkFrame(self, fg_color="transparent")
		root.pack(fill="both", expand=True, padx=28, pady=24)
		ctk.CTkLabel(root, text="SEO Image Studio", font=ctk.CTkFont(size=28, weight="bold")).pack(anchor="w")
		ctk.CTkLabel(root, text="WebP · reSmush.it · alt text Gemini", text_color="#9ca3af").pack(anchor="w", pady=(4, 18))
		actions = ctk.CTkFrame(root, fg_color="transparent")
		actions.pack(fill="x", pady=(0, 14))
		ctk.CTkButton(actions, text="＋  Aggiungi immagini", command=self.select_files, width=180).pack(side="left")
		ctk.CTkButton(actions, text="Svuota", command=self.clear_files, width=90, fg_color="#374151", hover_color="#4b5563").pack(side="left", padx=10)
		self.gallery = ctk.CTkScrollableFrame(root, label_text="Immagini selezionate", label_font=ctk.CTkFont(size=14, weight="bold"))
		self.gallery.pack(fill="both", expand=True, pady=(0, 14))
		for column in range(3):
			self.gallery.grid_columnconfigure(column, weight=1)
		settings = ctk.CTkFrame(root, fg_color="transparent")
		settings.pack(fill="x", pady=(0, 8))
		ctk.CTkLabel(settings, text="Prefisso file").pack(side="left")
		ctk.CTkEntry(settings, textvariable=self.prefix, width=190).pack(side="left", padx=(10, 20))
		ctk.CTkLabel(settings, text="Titolo articolo").pack(side="left")
		ctk.CTkEntry(settings, textvariable=self.article_title, placeholder_text="Es. La storia dell'armatura medievale").pack(side="left", fill="x", expand=True, padx=10)
		ctk.CTkLabel(settings, text="Destinazione").pack(side="left")
		ctk.CTkEntry(settings, textvariable=self.output).pack(side="left", fill="x", expand=True, padx=10)
		ctk.CTkButton(settings, text="Scegli", command=self.select_output, width=85).pack(side="left")
		api_settings = ctk.CTkFrame(root, fg_color="transparent")
		api_settings.pack(fill="x", pady=(0, 8))
		ctk.CTkLabel(api_settings, text="Gemini API key").pack(side="left")
		ctk.CTkEntry(api_settings, textvariable=self.api_key, show="*", placeholder_text="Incolla la chiave API qui").pack(side="left", fill="x", expand=True, padx=10)
		ctk.CTkCheckBox(api_settings, text="Ricorda", variable=self.remember_key, width=90).pack(side="left")
		self.progress = ctk.CTkProgressBar(root, height=10)
		self.progress.pack(fill="x", pady=(8, 8))
		self.progress.set(0)
		ctk.CTkLabel(root, textvariable=self.status, text_color="#9ca3af").pack(anchor="w")
		self.start_button = ctk.CTkButton(root, text="CONVERTI E OTTIMIZZA", command=self.start, height=42, font=ctk.CTkFont(weight="bold"))
		self.start_button.pack(anchor="e", pady=(12, 0))

	def select_files(self):
		self.files = list(filedialog.askopenfilenames(
			title="Seleziona immagini",
			filetypes=[("Immagini", "*.jpg *.jpeg *.png *.tif *.tiff *.bmp *.webp")],
		))
		for card in self.cards:
			card["frame"].destroy()
		self.cards = [self.create_card(path, index) for index, path in enumerate(self.files)]
		self.status.set(f"{len(self.files)} immagini selezionate")

	def clear_files(self):
		self.files = []
		for card in self.cards:
			card["frame"].destroy()
		self.cards = []
		self.status.set("Seleziona le immagini da elaborare")

	def create_card(self, path, index):
		card = ctk.CTkFrame(self.gallery, corner_radius=14, fg_color="#172033")
		card.grid(row=index // 3, column=index % 3, padx=8, pady=8, sticky="nsew")
		try:
			with Image.open(path) as image:
				preview = image.copy()
		except Exception:
			preview = Image.new("RGB", (640, 420), "#26354d")
		photo = ctk.CTkImage(light_image=preview, dark_image=preview, size=(220, 145))
		image_label = ctk.CTkLabel(card, image=photo, text="")
		image_label.pack(fill="x", padx=10, pady=(10, 8))
		name_label = ctk.CTkLabel(card, text=os.path.basename(path), anchor="w", font=ctk.CTkFont(size=12, weight="bold"))
		name_label.pack(fill="x", padx=10)
		metric_label = ctk.CTkLabel(card, text="In attesa di elaborazione", anchor="w", text_color="#93c5fd", font=ctk.CTkFont(size=11))
		metric_label.pack(fill="x", padx=10, pady=(3, 10))
		return {"frame": card, "metric": metric_label}

	def select_output(self):
		folder = filedialog.askdirectory(title="Cartella di destinazione")
		if folder:
			self.output.set(folder)

	def start(self):
		if not self.files:
			messagebox.showwarning("Nessuna immagine", "Aggiungi almeno un'immagine.")
			return
		safe_prefix = re.sub(r"\s+", "-", self.prefix.get().strip())
		safe_prefix = re.sub(r"[^\w-]", "", safe_prefix).strip("-")
		if not safe_prefix:
			messagebox.showwarning("Prefisso non valido", "Inserisci un prefisso per i file.")
			return
		self.prefix.set(safe_prefix)
		api_key = self.api_key.get().strip()
		if api_key and self.remember_key.get() and not save_api_key(api_key):
			self.status.set("Chiave non salvata nel Portachiavi; continuo comunque")
		os.makedirs(self.output.get(), exist_ok=True)
		self.start_button.configure(state="disabled")
		self.progress.set(0)
		threading.Thread(target=self.process, daemon=True).start()

	def process(self):
		errors = []
		gemini_error_reported = False
		prefix = self.prefix.get()
		api_key = self.api_key.get().strip()
		article_title = self.article_title.get().strip()
		for index, source in enumerate(self.files, 1):
			try:
				title, alt = make_seo_data(source)
				alt_source = "nome file"
				try:
					alt = make_gemini_alt(source, api_key, article_title)
					alt_source = "Gemini"
				except Exception as error:
					if not gemini_error_reported:
						errors.append(f"Gemini non disponibile: {error}")
						gemini_error_reported = True
				destination = os.path.join(self.output.get(), f"{prefix}-{index}.webp")
				original_size = os.path.getsize(source)
				with Image.open(source) as image:
					image.convert("RGB").save(destination, "WEBP", quality=85, method=6)
				resmush_ok = False
				try:
					resmush_ok = optimize_with_resmush(destination)
				except Exception as error:
					errors.append(f"reSmush.it {os.path.basename(source)}: {error}")
				optimized_size = os.path.getsize(destination)
				percent, saved_mb = compression_stats(original_size, optimized_size)
				self.after(0, self.update_file_row, index - 1, percent, saved_mb, resmush_ok)
				metadata = {
					"title": title,
					"alt": alt,
					"alt_source": alt_source,
					"file": os.path.basename(destination),
					"compression_percent": round(percent, 2),
					"saved_mb": round(saved_mb, 3),
				}
				with open(os.path.splitext(destination)[0] + ".json", "w", encoding="utf-8") as file:
					json.dump(metadata, file, ensure_ascii=False, indent=2)
				with open(os.path.splitext(destination)[0] + ".txt", "w", encoding="utf-8") as file:
					file.write(f"{os.path.basename(destination)}\n{alt}\n")
			except Exception as error:
				errors.append(f"{os.path.basename(source)}: {error}")
			self.after(0, lambda value=index: self.progress.set(value / len(self.files)))
		self.after(0, self.finish, errors)

	def update_file_row(self, row, percent, saved_mb, resmush_ok):
		service = " · reSmush.it" if resmush_ok else ""
		self.cards[row]["metric"].configure(
			text=f"{percent:.1f}% compressi · {saved_mb:.2f} MB risparmiati{service}",
			fg="#86efac" if percent > 0 else "#fbbf24",
		)

	def finish(self, errors):
		self.start_button.configure(state="normal")
		self.status.set("Completato con errori" if errors else "Elaborazione completata")
		if errors:
			messagebox.showwarning("Risultato", "\n".join(errors))
		else:
			messagebox.showinfo("Fatto", "Immagini WebP e metadati SEO salvati.")


if __name__ == "__main__":
	ImageApp().mainloop()
