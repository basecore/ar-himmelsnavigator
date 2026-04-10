import urllib.request
import urllib.parse
import re
import ssl
import threading
import tkinter as tk
from tkinter import ttk, filedialog, scrolledtext
from datetime import datetime


# ==========================================
# NASA Horizons API Funktion
# ==========================================
def fetch_horizons(command, start, stop, step, name, log_callback):
    url = "https://ssd.jpl.nasa.gov/api/horizons.api"
    params = {
        "format": "text",
        "COMMAND": command,
        "CENTER": "'@10'",  # Zentrum: Sonne
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
        "OUT_UNITS": "'AU-D'",  # Distanz in AU, Zeit in Tagen
        "CSV_FORMAT": "'YES'"
    }

    query_string = urllib.parse.urlencode(params)
    full_url = f"{url}?{query_string}"

    log_callback(f"Lade Daten für {name} von NASA Horizons... (bis {stop})")

    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE

    try:
        req = urllib.request.Request(full_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, context=ctx) as response:
            text = response.read().decode('utf-8')
            match = re.search(r'\$\$SOE(.*?)\$\$EOE', text, re.DOTALL)

            if not match:
                # Automatischer Fallback: Suche in der API-Antwort nach dem maximal möglichen Datum
                err_match = re.search(r'No ephemeris for target "(.*?)" after A\.D\. (\d{4}-[A-Z]{3}-\d{2})', text)
                if err_match:
                    new_date_str = err_match.group(2)
                    try:
                        # Datum umwandeln in YYYY-MM-DD
                        new_date = datetime.strptime(new_date_str.title(), "%Y-%b-%d").strftime("%Y-%m-%d")
                        log_callback(f"  -> INFO: Die Mission von {name} endet offiziell am {new_date}.")
                        log_callback(f"  -> FALLBACK: Lade {name} erneut bis zum {new_date}...")

                        # Starte den Download für diesen Körper neu, mit dem korrigierten Datum
                        return fetch_horizons(command, start, new_date, step, name, log_callback)
                    except Exception as e:
                        log_callback(f"  -> Fehler beim Parsen des Datums: {e}")
                else:
                    log_callback(f"  -> FEHLER: Konnte keine Daten für {name} finden.")
                    # Zeige die letzten 250 Zeichen der Antwort zum Debuggen
                    log_callback(f"  -> API Antwort (Ende): {text[-250:].strip()}")
                return []

            lines = match.group(1).strip().split('\n')
            coords = []

            for line in lines:
                parts = [p.strip() for p in line.split(',')]
                if len(parts) >= 8:
                    date_str = parts[1].replace('A.D. ', '').replace('TDB', '').strip()

                    x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                    vx, vy, vz = float(parts[5]), float(parts[6]), float(parts[7])

                    # Geschwindigkeit berechnen (km/s)
                    velocity_kms = (vx ** 2 + vy ** 2 + vz ** 2) ** 0.5 * 1731.4568

                    try:
                        dt = datetime.strptime(date_str, "%Y-%b-%d %H:%M:%S.%f")
                    except ValueError:
                        dt = datetime.strptime(date_str, "%Y-%b-%d %H:%M:%S")

                    iso_date = dt.strftime("%Y-%m-%dT%H:%M:%S.000Z")

                    coords.append({
                        "date": iso_date, "x": x, "y": y, "z": z, "velocity": velocity_kms
                    })

            log_callback(f"  -> {len(coords)} Datenpunkte für {name} erfolgreich geladen.")
            return coords

    except Exception as e:
        log_callback(f"  -> Fehlschlag bei {name}: {e}")
        return []


# ==========================================
# GUI Anwendung
# ==========================================
class HorizonsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NASA Horizons Data Downloader (Pro Version)")
        self.root.geometry("680x550")
        self.root.configure(padx=20, pady=20)

        self.start_var = tk.StringVar(value="2024-10-15")
        self.stop_var = tk.StringVar(value="2034-12-31")
        self.step_var = tk.StringVar(value="1 d")
        self.path_var = tk.StringVar(value="coordinates.js")

        self.setup_ui()

    def setup_ui(self):
        config_frame = ttk.LabelFrame(self.root, text="Einstellungen", padding=10)
        config_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(config_frame, text="Start-Datum:").grid(row=0, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.start_var, width=15).grid(row=0, column=1, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="End-Datum:").grid(row=0, column=2, sticky=tk.W, padx=(20, 0), pady=5)
        ttk.Entry(config_frame, textvariable=self.stop_var, width=15).grid(row=0, column=3, sticky=tk.W, pady=5)

        ttk.Label(config_frame, text="Schrittweite (Step):").grid(row=1, column=0, sticky=tk.W, pady=5)
        ttk.Entry(config_frame, textvariable=self.step_var, width=15).grid(row=1, column=1, sticky=tk.W, pady=5)

        save_frame = ttk.Frame(self.root)
        save_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(save_frame, text="Speicherort:").pack(side=tk.LEFT)
        ttk.Entry(save_frame, textvariable=self.path_var, width=45).pack(side=tk.LEFT, padx=10)
        ttk.Button(save_frame, text="Durchsuchen...", command=self.browse_file).pack(side=tk.LEFT)

        action_frame = ttk.Frame(self.root)
        action_frame.pack(fill=tk.X, pady=(0, 10))
        self.btn_start = ttk.Button(action_frame, text="🚀 Download Starten", command=self.start_download)
        self.btn_start.pack(side=tk.LEFT)

        self.progress = ttk.Progressbar(action_frame, orient=tk.HORIZONTAL, length=400, mode='determinate')
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        log_frame = ttk.LabelFrame(self.root, text="Log & Debugging", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.console = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, height=15, state='disabled', bg="#1e1e1e",
                                                 fg="#00ff00", font=("Consolas", 9))
        self.console.pack(fill=tk.BOTH, expand=True)

        self.log_message("System bereit. Einstellungen prüfen und Download starten.")

    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".js",
            filetypes=[("JavaScript Files", "*.js"), ("All Files", "*.*")],
            initialfile="coordinates.js",
            title="Speicherort auswählen"
        )
        if filename:
            self.path_var.set(filename)

    def log_message(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.console.config(state='normal')
        self.console.insert(tk.END, message + "\n")
        self.console.see(tk.END)
        self.console.config(state='disabled')

    def start_download(self):
        self.btn_start.config(state='disabled')
        self.progress['value'] = 0
        self.console.config(state='normal')
        self.console.delete('1.0', tk.END)
        self.console.config(state='disabled')

        self.log_message(f"=== STARTE NEUEN DOWNLOAD ===")
        self.log_message(f"Zeitraum: {self.start_var.get()} bis {self.stop_var.get()}")
        threading.Thread(target=self.download_worker, daemon=True).start()

    def download_worker(self):
        start = self.start_var.get()
        stop = self.stop_var.get()
        step = self.step_var.get()
        save_path = self.path_var.get()

        # Das Semikolon erzwingt Spacecraft!
        bodies_to_fetch = [
            {"id": "'399'", "key": "Earth", "color": "#4169E1", "size": 6},
            {"id": "'499'", "key": "Mars", "color": "#FF4500", "size": 5},
            {"id": "'599'", "key": "Jupiter", "color": "#FFD700", "size": 12},
            {"id": "'502'", "key": "Europa", "color": "#FFFFFF", "size": 3},
            # WICHTIG: -159 in einfachen Anführungszeichen, OHNE Semikolon!
            {"id": "'-159'", "key": "Clipper", "color": "#64ffff", "size": 4}
        ]

        self.progress['maximum'] = len(bodies_to_fetch)

        js_out = "const bodies = {\n"
        js_out += "  'Sun': { color: '#FFD700', size: 15, x: 0, y: 0, z: 0, velocity: 0 },\n"

        for idx, body in enumerate(bodies_to_fetch):
            data = fetch_horizons(body["id"], start, stop, step, body["key"], self.log_message)

            if data:
                js_out += f"  '{body['key']}': {{\n    color: '{body['color']}', size: {body['size']},\n    coordinates: [\n"
                lines = [
                    f"      {{ date: new Date(\"{c['date']}\"), x: {c['x']:.8f}, y: {c['y']:.8f}, z: {c['z']:.8f}, velocity: {c['velocity']:.4f} }}"
                    for c in data]
                js_out += ",\n".join(lines)
                js_out += "\n    ]\n  },\n"

            self.root.after(0, self.update_progress, idx + 1)

        js_out = js_out.rstrip(",\n") + "\n};\n"

        try:
            with open(save_path, "w", encoding="utf-8") as f:
                f.write(js_out)
            self.log_message(f"\nERFOLG: Datei wurde gespeichert unter:\n{save_path}")
        except Exception as e:
            self.log_message(f"\nFEHLER beim Speichern: {e}")

        self.root.after(0, lambda: self.btn_start.config(state='normal'))

    def update_progress(self, val):
        self.progress['value'] = val


if __name__ == "__main__":
    root = tk.Tk()
    app = HorizonsApp(root)
    root.mainloop()