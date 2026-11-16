#!/usr/bin/env python3
"""NASA Horizons downloader for the AR Himmelsnavigator.

GUI mode:
    python Clipper_Downloader.py

Regenerate the complete coordinates.js:
    python Clipper_Downloader.py --regenerate-all --output coordinates.js

Update only the Europa Clipper entry:
    python Clipper_Downloader.py --update-clipper --output coordinates.js
"""

import argparse
import os
import re
import tempfile
import threading
import tkinter as tk
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from tkinter import ttk, filedialog, scrolledtext

HORIZONS_API = "https://ssd.jpl.nasa.gov/api/horizons.api"
CLIPPER_COMMAND = "'-159'"
DEFAULT_OUTPUT = "coordinates.js"

BODIES = [
    {"id": "'399'", "key": "Earth", "color": "#4169E1", "size": 6},
    {"id": "'499'", "key": "Mars", "color": "#FF4500", "size": 5},
    {"id": "'599'", "key": "Jupiter", "color": "#FFD700", "size": 12},
    {"id": "'502'", "key": "Europa", "color": "#FFFFFF", "size": 3},
    {"id": CLIPPER_COMMAND, "key": "Clipper", "color": "#64ffff", "size": 4},
]


def log(message):
    print(message, flush=True)


def fetch_horizons_vectors(command, start, stop, step, name, log_callback=log):
    params = {
        "format": "text",
        "COMMAND": command,
        "CENTER": "'@10'",
        "MAKE_EPHEM": "'YES'",
        "EPHEM_TYPE": "'VECTORS'",
        "START_TIME": f"'{start}'",
        "STOP_TIME": f"'{stop}'",
        "STEP_SIZE": f"'{step}'",
        "OUT_UNITS": "'AU-D'",
        "CSV_FORMAT": "'YES'",
    }
    full_url = f"{HORIZONS_API}?{urllib.parse.urlencode(params)}"
    log_callback(f"Lade {name} von NASA Horizons: {start} bis {stop}, Schritt {step}")

    last_error = None
    for attempt in range(1, 4):
        try:
            request = urllib.request.Request(
                full_url,
                headers={"User-Agent": "ar-himmelsnavigator/1.0"},
            )
            with urllib.request.urlopen(request, timeout=60) as response:
                text = response.read().decode("utf-8")

            match = re.search(r"\$\$SOE(.*?)\$\$EOE", text, re.DOTALL)
            if not match:
                error_match = re.search(
                    r"No ephemeris for target \"(.*?)\" after A\.D\. (\d{4}-[A-Z]{3}-\d{2})",
                    text,
                )
                if error_match:
                    mission_end = datetime.strptime(
                        error_match.group(2).title(), "%Y-%b-%d"
                    ).strftime("%Y-%m-%d")
                    log_callback(
                        f"Mission {name} endet laut Horizons am {mission_end}; "
                        "begrenze den Abruf entsprechend."
                    )
                    return fetch_horizons_vectors(
                        command, start, mission_end, step, name, log_callback
                    )

                raise ValueError(
                    "Keine Ephemeriden-Daten in der Horizons-Antwort gefunden. "
                    f"Antwortende: {text[-300:]}"
                )

            coordinates = []
            for line in match.group(1).strip().splitlines():
                parts = [part.strip() for part in line.split(",")]
                if len(parts) < 8:
                    continue

                date_text = parts[1].replace("A.D. ", "").replace("TDB", "").strip()
                try:
                    parsed_date = datetime.strptime(date_text, "%Y-%b-%d %H:%M:%S.%f")
                except ValueError:
                    parsed_date = datetime.strptime(date_text, "%Y-%b-%d %H:%M:%S")

                x, y, z = float(parts[2]), float(parts[3]), float(parts[4])
                vx, vy, vz = float(parts[5]), float(parts[6]), float(parts[7])
                velocity_kms = ((vx ** 2 + vy ** 2 + vz ** 2) ** 0.5) * 1731.4568

                coordinates.append({
                    "date": parsed_date.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
                    "x": x,
                    "y": y,
                    "z": z,
                    "velocity": velocity_kms,
                })

            if not coordinates:
                raise ValueError("Horizons lieferte keine verwertbaren Datenzeilen.")

            log_callback(f"{len(coordinates)} Datenpunkte für {name} geladen.")
            return coordinates

        except Exception as error:
            last_error = error
            log_callback(f"Versuch {attempt}/3 für {name} fehlgeschlagen: {error}")

    raise RuntimeError(f"Datenabruf für {name} endgültig fehlgeschlagen: {last_error}")


def build_body_block(key, color, size, coordinates):
    entries = []
    for point in coordinates:
        entries.append(
            '      { date: new Date("' + point["date"] + '"), '
            + "x: " + format(point["x"], ".8f")
            + ", y: " + format(point["y"], ".8f")
            + ", z: " + format(point["z"], ".8f")
            + ", velocity: " + format(point["velocity"], ".4f")
            + " }"
        )

    return (
        "  '" + key + "': {\n"
        "    color: '" + color + "', size: " + str(size) + ",\n"
        "    coordinates: [\n"
        + ",\n".join(entries)
        + "\n    ]\n  },\n"
    )


def write_text_atomically(path, content):
    directory = os.path.dirname(os.path.abspath(path)) or "."
    descriptor, temporary_path = tempfile.mkstemp(
        dir=directory, prefix=".coordinates-", suffix=".js"
    )
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            file.write(content)
        os.replace(temporary_path, path)
    except Exception:
        if os.path.exists(temporary_path):
            os.unlink(temporary_path)
        raise


def regenerate_all(output, start, stop, step):
    js_output = "const bodies = {\n"
    js_output += (
        "  'Sun': { color: '#FFD700', size: 15, x: 0, y: 0, z: 0, velocity: 0 },\n"
    )

    for body in BODIES:
        data = fetch_horizons_vectors(
            body["id"], start, stop, step, body["key"]
        )
        js_output += build_body_block(
            body["key"], body["color"], body["size"], data
        )

    js_output = js_output.rstrip(",\n") + "\n};\n"

    for required in ("'Earth'", "'Mars'", "'Jupiter'", "'Europa'", "'Clipper'"):
        if required not in js_output:
            raise ValueError(f"Regenerierte coordinates.js enthält {required} nicht.")

    write_text_atomically(output, js_output)
    log(f"coordinates.js vollständig regeneriert: {output}")
    log(f"Zeitraum: {start} bis {stop}, Schrittweite: {step}")


def build_clipper_block(coordinates):
    return build_body_block("Clipper", "#64ffff", 4, coordinates)


def replace_clipper_in_coordinates_js(path, coordinates):
    with open(path, "r", encoding="utf-8") as file:
        content = file.read()

    clipper_block = build_clipper_block(coordinates)
    pattern = re.compile(r"(?ms)^  'Clipper':\s*\{.*?^  \},\s*$")

    if pattern.search(content):
        updated = pattern.sub(clipper_block.rstrip("\n") + "\n", content, count=1)
    else:
        closing = content.rstrip()
        if not closing.endswith("};"):
            raise ValueError(
                "coordinates.js hat ein unerwartetes Format; "
                "Clipper-Eintrag kann nicht sicher eingefügt werden."
            )
        updated = closing[:-2].rstrip() + "\n\n" + clipper_block + "};\n"

    if "'Clipper'" not in updated:
        raise ValueError("Clipper-Eintrag fehlt nach der Aktualisierung.")

    write_text_atomically(path, updated)


def update_clipper(output, days_back, days_ahead, step):
    now = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    start = (now - timedelta(days=days_back)).strftime("%Y-%m-%d")
    stop = (now + timedelta(days=days_ahead)).strftime("%Y-%m-%d")

    coordinates = fetch_horizons_vectors(
        CLIPPER_COMMAND, start, stop, step, "Europa Clipper"
    )
    replace_clipper_in_coordinates_js(output, coordinates)
    log(f"coordinates.js aktualisiert: {output}")
    log(f"Zeitraum: {start} bis {stop}, Schrittweite: {step}")


class HorizonsApp:
    def __init__(self, root):
        self.root = root
        self.root.title("NASA Horizons Data Downloader (Pro Version)")
        self.root.geometry("680x550")
        self.root.configure(padx=20, pady=20)

        self.start_var = tk.StringVar(value="2024-10-15")
        self.stop_var = tk.StringVar(value="2034-12-31")
        self.step_var = tk.StringVar(value="1 d")
        self.path_var = tk.StringVar(value=DEFAULT_OUTPUT)
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
        ttk.Button(action_frame, text="🚀 Download Starten", command=self.start_download).pack(side=tk.LEFT)
        self.progress = ttk.Progressbar(action_frame, orient=tk.HORIZONTAL, length=400, mode="determinate")
        self.progress.pack(side=tk.RIGHT, fill=tk.X, expand=True, padx=(10, 0))

        log_frame = ttk.LabelFrame(self.root, text="Log & Debugging", padding=10)
        log_frame.pack(fill=tk.BOTH, expand=True)
        self.console = scrolledtext.ScrolledText(
            log_frame, wrap=tk.WORD, height=15, state="disabled", bg="#1e1e1e",
            fg="#00ff00", font=("Consolas", 9),
        )
        self.console.pack(fill=tk.BOTH, expand=True)
        self.log_message("System bereit. Einstellungen prüfen und Download starten.")

    def browse_file(self):
        filename = filedialog.asksaveasfilename(
            defaultextension=".js",
            filetypes=[("JavaScript Files", "*.js"), ("All Files", "*.*")],
            initialfile=DEFAULT_OUTPUT,
            title="Speicherort auswählen",
        )
        if filename:
            self.path_var.set(filename)

    def log_message(self, message):
        self.root.after(0, self._append_log, message)

    def _append_log(self, message):
        self.console.config(state="normal")
        self.console.insert(tk.END, message + "\n")
        self.console.see(tk.END)
        self.console.config(state="disabled")

    def start_download(self):
        threading.Thread(target=self.download_worker, daemon=True).start()

    def download_worker(self):
        self.progress["maximum"] = len(BODIES)
        js_output = "const bodies = {\n"
        js_output += (
            "  'Sun': { color: '#FFD700', size: 15, x: 0, y: 0, z: 0, velocity: 0 },\n"
        )

        for index, body in enumerate(BODIES):
            data = fetch_horizons_vectors(
                body["id"], self.start_var.get(), self.stop_var.get(),
                self.step_var.get(), body["key"], self.log_message,
            )
            if data:
                js_output += build_body_block(
                    body["key"], body["color"], body["size"], data
                )
            self.root.after(0, self.update_progress, index + 1)

        js_output = js_output.rstrip(",\n") + "\n};\n"
        write_text_atomically(self.path_var.get(), js_output)
        self.log_message(f"ERFOLG: Datei gespeichert unter {self.path_var.get()}")
        self.root.after(0, lambda: self.progress.config(value=0))

    def update_progress(self, value):
        self.progress["value"] = value


def parse_arguments():
    parser = argparse.ArgumentParser(
        description="Erzeugt oder aktualisiert coordinates.js über JPL Horizons."
    )
    parser.add_argument(
        "--regenerate-all",
        action="store_true",
        help="Regeneriert die komplette coordinates.js für alle unterstützten Körper.",
    )
    parser.add_argument(
        "--update-clipper",
        action="store_true",
        help="Aktualisiert nur den Clipper-Eintrag in coordinates.js.",
    )
    parser.add_argument("--output", default=DEFAULT_OUTPUT, help="Pfad zur coordinates.js.")
    parser.add_argument("--start", default="2024-10-15", help="Startdatum für --regenerate-all.")
    parser.add_argument("--stop", default="2034-12-31", help="Enddatum für --regenerate-all.")
    parser.add_argument("--step", default="1 d", help="Horizons-Schrittweite.")
    parser.add_argument("--days-back", type=int, default=1, help="Tage vor heute für --update-clipper.")
    parser.add_argument("--days-ahead", type=int, default=400, help="Tage nach heute für --update-clipper.")
    return parser.parse_args()


def main():
    arguments = parse_arguments()

    if arguments.regenerate_all:
        regenerate_all(arguments.output, arguments.start, arguments.stop, arguments.step)
        return

    if arguments.update_clipper:
        update_clipper(
            arguments.output, arguments.days_back, arguments.days_ahead, arguments.step
        )
        return

    root = tk.Tk()
    HorizonsApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
