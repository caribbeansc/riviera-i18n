"""Graphical patcher: pick your game, pick a language, click Build.

A thin Tkinter shell over the command line (``riviera.cli``): every button runs the same command you would type, so a player gets
the same result with a few clicks. Built into standalone Windows and macOS executables by ``.github/workflows/patcher.yml``;
``python gui.py`` from a checkout works the same.

In the frozen app the checkout's ``langs/`` ships inside the executable and the configuration, ``work/`` and ``build/`` live in
``~/Riviera-i18n``. Nothing from the game is ever bundled: the app always reads your own copy.

``python gui.py --selftest`` checks that everything the app needs is there (the packs, the data files of the Android build, hactool when
it is bundled) and exits without opening a window; ``--smoke`` builds the window hidden and quits (it needs a display). The release
workflow runs the first on every executable it builds.
"""

from __future__ import annotations

import contextlib
import importlib
import locale
import queue
import sys
import threading
from pathlib import Path

BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
sys.path.insert(0, str(BUNDLE_DIR))

SPANISH = (locale.getlocale()[0] or "").lower().startswith("es")


def tr(en: str, es: str) -> str:
    return es if SPANISH else en


# ----------------------------------------------------------- what to run ----
# The window only builds command lines; these are plain functions so they can be tested without a display.

def setup_argv(source: str, backup: str = "", keys: str = "", exefs: str = "", romfs: str = "") -> list[str]:
    """``setup`` arguments for a backup (``"backup"``) or for the folders an emulator extracted (``"folders"``)."""
    if source == "backup":
        return ["setup", "--xci", backup] + (["--keys", keys] if keys else [])
    return ["setup", "--exefs", exefs, "--romfs", romfs]


def switch_argv(action: str, code: str, folder: str = "") -> list[str]:
    argv = ["switch", action, code]
    if action == "install" and folder:
        argv += ["--to", folder]
    return argv


def android_argv(action: str, code: str, keep_license_check: bool = False, serial: str = "") -> list[str]:
    argv = ["android", action, code]
    if action == "build" and keep_license_check:
        argv.append("--keep-license-check")
    if action == "install" and serial:
        argv += ["--serial", serial]
    return argv


def selftest() -> int:
    """Everything the app needs, without a window. Returns 0 when it is all there."""
    problems = []
    from riviera import config, packs
    from riviera.switch import extract

    found = packs.discover(config.repo_root() / "langs")
    if not {"es", "en"} <= {p.code for p in found}:
        problems.append("the language packs are missing")
    elif len(next(p for p in found if p.code == "es").text()) < 10000:
        problems.append("the Spanish script is incomplete")
    try:
        for module in ("riviera.android.build", "riviera.android.licensecheck"):
            importlib.import_module(module)
        importlib.import_module("riviera.android.hooks").load()
    except Exception as e:                                           # a data file left out of the executable shows up here
        problems.append(f"the Android build cannot load: {e}")
    frozen = hasattr(sys, "_MEIPASS")
    if frozen and not extract.find_hactool():
        problems.append("hactool is not bundled")
    for p in problems:
        print("selftest:", p)
    print("selftest:", "FAILED" if problems else "ok", f"(frozen={frozen})")
    return 1 if problems else 0


class LogSink:
    """A file-like ``stdout`` that feeds the log widget through a queue."""

    def __init__(self, q: queue.Queue):
        self.q, self._buf = q, ""

    def write(self, text: str) -> int:
        self._buf += text
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            self.q.put(line.replace("\r", ""))
        return len(text)

    def flush(self) -> None:
        pass

    def isatty(self) -> bool:
        return False


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()

    import tkinter as tk
    from tkinter import filedialog, messagebox, ttk

    from riviera import cli, config, packs

    class App:
        def __init__(self, root: tk.Tk):
            self.root = root
            root.title("Riviera Patcher")
            root.geometry("780x600")
            root.minsize(620, 480)
            self.q: queue.Queue = queue.Queue()
            self.busy = False

            frame = ttk.Frame(root, padding=10)
            frame.pack(fill="both", expand=True)
            tabs = ttk.Notebook(frame)
            tabs.pack(fill="x")
            self.switch_tab, self.android_tab = ttk.Frame(tabs, padding=8), ttk.Frame(tabs, padding=8)
            tabs.add(self.switch_tab, text="Switch")
            tabs.add(self.android_tab, text="Android")
            self.build_switch_tab()
            self.build_android_tab()

            self.log = tk.Text(frame, wrap="none", state="disabled", height=14, background="#111", foreground="#ddd")
            self.log.pack(fill="both", expand=True, pady=(8, 0))
            self.status = tk.StringVar(value=tr("Ready.", "Listo."))
            ttk.Label(frame, textvariable=self.status).pack(fill="x", pady=(6, 0))
            root.after(100, self.drain)
            self.load_state()

        # ------------------------------------------------------------ tabs --
        def row(self, parent, label, var, *buttons):
            r = ttk.Frame(parent)
            r.pack(fill="x", pady=2)
            ttk.Label(r, text=label, width=14).pack(side="left")
            ttk.Entry(r, textvariable=var).pack(side="left", fill="x", expand=True, padx=6)
            for text, command in buttons:
                ttk.Button(r, text=text, command=command).pack(side="left", padx=(4, 0))
            return r

        def build_switch_tab(self):
            t = self.switch_tab
            ttk.Label(t, foreground="#666", wraplength=720, text=tr(
                "Pick your own backup (.xci / .nsp, needs your prod.keys and hactool), or the exefs and romfs folders your emulator "
                "extracted (Extract Data). The mod takes the place of the game's English: run the game in English.",
                "Elige tu propia copia (.xci / .nsp: necesita tu prod.keys y hactool) o las carpetas exefs y romfs que extrajo tu "
                "emulador (Extract Data). El mod ocupa el lugar del inglés del juego: ejecuta el juego en inglés.")).pack(fill="x", pady=(0, 6))
            self.backup, self.keys, self.exefs, self.romfs = (tk.StringVar() for _ in range(4))
            self.row(t, tr("Backup:", "Copia:"), self.backup, ("…", lambda: self.pick_file(self.backup, [("Switch backup", "*.xci *.nsp")])))
            self.row(t, "prod.keys:", self.keys, ("…", lambda: self.pick_file(self.keys, [("Keys", "*.keys"), ("All", "*.*")])))
            self.row(t, "ExeFS:", self.exefs, ("…", lambda: self.pick_dir(self.exefs)))
            self.row(t, "RomFS:", self.romfs, ("…", lambda: self.pick_dir(self.romfs)))
            r = ttk.Frame(t)
            r.pack(fill="x", pady=(8, 0))
            ttk.Label(r, text=tr("Language:", "Idioma:")).pack(side="left")
            self.lang_switch = tk.StringVar()
            self.box_switch = ttk.Combobox(r, textvariable=self.lang_switch, state="readonly", width=24)
            self.box_switch.pack(side="left", padx=6)
            for text, command in ((tr("1 · Set up", "1 · Configurar"), self.job_setup),
                                  (tr("2 · Build the mod", "2 · Crear el mod"), self.job_switch_build),
                                  (tr("3 · Install in an emulator", "3 · Instalar en el emulador"), self.job_switch_install)):
                ttk.Button(r, text=text, command=lambda c=command: self.launch(c)).pack(side="left", padx=3)
            r2 = ttk.Frame(t)
            r2.pack(fill="x", pady=(6, 0))
            ttk.Button(r2, text=tr("Install in a folder…", "Instalar en una carpeta…"), command=lambda: self.launch(self.job_switch_folder)).pack(side="left")
            ttk.Button(r2, text=tr("ZIP for a console (Atmosphère)", "ZIP para consola (Atmosphère)"), command=lambda: self.launch(self.job_switch_zip)).pack(side="left", padx=6)

        def build_android_tab(self):
            t = self.android_tab
            ttk.Label(t, foreground="#666", wraplength=720, text=tr(
                "Needs the split APKs of your own copy of the app (see docs/ANDROID.md), your Switch dump (the Android app has no English) "
                "and the Android SDK build-tools and a JDK. Installing replaces the original app, which erases its saves.",
                "Necesita los APK divididos de tu propia copia de la app (mira docs/ANDROID.md), tu volcado de Switch (la app de Android "
                "no trae inglés), las build-tools del SDK de Android y un JDK. Instalar reemplaza la app original y borra sus partidas.")).pack(fill="x", pady=(0, 6))
            self.apk_dir = tk.StringVar()
            self.keep_check = tk.BooleanVar(value=False)
            self.row(t, tr("APK folder:", "Carpeta de APK:"), self.apk_dir, ("…", lambda: self.pick_dir(self.apk_dir)))
            r = ttk.Frame(t)
            r.pack(fill="x", pady=(8, 0))
            ttk.Label(r, text=tr("Language:", "Idioma:")).pack(side="left")
            self.lang_android = tk.StringVar()
            self.box_android = ttk.Combobox(r, textvariable=self.lang_android, state="readonly", width=24)
            self.box_android.pack(side="left", padx=6)
            ttk.Button(r, text=tr("Set up", "Configurar"), command=lambda: self.launch(self.job_android_setup)).pack(side="left", padx=3)
            ttk.Button(r, text=tr("Build the app", "Crear la app"), command=lambda: self.launch(self.job_android_build)).pack(side="left", padx=3)
            ttk.Button(r, text=tr("Install (adb)", "Instalar (adb)"), command=lambda: self.launch(self.job_android_install)).pack(side="left", padx=3)
            ttk.Checkbutton(t, variable=self.keep_check, text=tr(
                "Keep the Google Play licence check (the re-signed app will not start)",
                "Conservar la comprobación de licencia de Google Play (la app firmada de nuevo no arrancará)")).pack(anchor="w", pady=(8, 0))

        # ----------------------------------------------------------- state --
        def project(self):
            return config.load()

        def load_state(self):
            try:
                project = self.project()
                found = packs.discover(project.langs)
                self.packs_switch = [p for p in found if p.supports("switch")]
                self.packs_android = [p for p in found if p.supports("android")]
                self.box_switch["values"] = [f"{p.name} ({p.code})" for p in self.packs_switch]
                self.box_android["values"] = [f"{p.name} ({p.code})" for p in self.packs_android]
                if self.packs_switch:
                    self.box_switch.current(0)
                if self.packs_android:
                    self.box_android.current(0)
                if project.exefs:
                    self.exefs.set(str(project.exefs))
                if project.romfs:
                    self.romfs.set(str(project.romfs))
                if project.apk_dir:
                    self.apk_dir.set(str(project.apk_dir))
            except Exception as exc:                                  # never die on startup
                self.put_log(f"!! {exc}")

        def code(self, box, packs_list):
            i = box.current()
            return packs_list[i].code if i >= 0 else "es"

        def pick_file(self, var, types):
            path = filedialog.askopenfilename(filetypes=types)
            if path:
                var.set(path)

        def pick_dir(self, var):
            path = filedialog.askdirectory()
            if path:
                var.set(path)

        # ------------------------------------------------------------ jobs --
        def job_setup(self):
            if self.backup.get().strip():
                return self.run(setup_argv("backup", backup=self.backup.get().strip(), keys=self.keys.get().strip()))
            return self.run(setup_argv("folders", exefs=self.exefs.get().strip(), romfs=self.romfs.get().strip()))

        def job_switch_build(self):
            return self.run(switch_argv("build", self.code(self.box_switch, self.packs_switch)))

        def job_switch_install(self):
            return self.run(switch_argv("install", self.code(self.box_switch, self.packs_switch)))

        def job_switch_folder(self):
            folder = filedialog.askdirectory(title=tr("The mods folder of your emulator", "La carpeta de mods de tu emulador"))
            return self.run(switch_argv("install", self.code(self.box_switch, self.packs_switch), folder)) if folder else 0

        def job_switch_zip(self):
            return self.run(["switch", "package", self.code(self.box_switch, self.packs_switch)])

        def job_android_setup(self):
            return self.run(["setup", "--apk-dir", self.apk_dir.get().strip()])

        def job_android_build(self):
            return self.run(android_argv("build", self.code(self.box_android, self.packs_android), self.keep_check.get()))

        def job_android_install(self):
            return self.run(android_argv("install", self.code(self.box_android, self.packs_android)))

        def run(self, argv: list[str]) -> int:
            self.q.put("$ rpl " + " ".join(argv))
            with contextlib.redirect_stdout(LogSink(self.q)), contextlib.redirect_stderr(LogSink(self.q)):
                try:
                    return cli.main(argv)
                except SystemExit as e:
                    return int(e.code or 0)
                except Exception as exc:                              # the window never dies with a traceback
                    print(f"!! {exc}")
                    return 1

        def launch(self, job):
            if self.busy:
                return
            self.busy = True
            self.status.set(tr("Working… (the first build takes a while)", "Trabajando… (la primera vez tarda)"))

            def work():
                code = job()
                self.q.put(("done", code))

            threading.Thread(target=work, daemon=True).start()

        # ------------------------------------------------------------- log --
        def put_log(self, line: str):
            self.log.configure(state="normal")
            self.log.insert("end", line + "\n")
            self.log.see("end")
            self.log.configure(state="disabled")

        def drain(self):
            try:
                while True:
                    item = self.q.get_nowait()
                    if isinstance(item, tuple):
                        self.busy = False
                        ok = item[1] in (0, None)
                        self.status.set(tr("Done.", "Listo.") if ok else tr("Something went wrong: see the log.", "Algo salió mal: mira el registro."))
                        if not ok:
                            messagebox.showwarning("Riviera Patcher", tr("It did not work. The log says why.", "No funcionó. El registro dice por qué."))
                    else:
                        self.put_log(item)
            except queue.Empty:
                pass
            self.root.after(100, self.drain)

    root = tk.Tk()
    if "--smoke" in sys.argv:                                       # build every widget without showing the window, then quit
        root.withdraw()
        App(root)
        root.update()
        root.destroy()
        print("smoke: ok")
        return 0
    App(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
