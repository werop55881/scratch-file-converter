"""Desktop GUI for sb3conv: pick an .sb3, choose a target, convert, run the result."""

from __future__ import annotations

import os
import queue
import runpy
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from tkinter import filedialog, ttk
from typing import Any

from sb3conv.backends import available_languages, get_backend
from sb3conv.convert import ConversionResult, convert, default_output_dir
from sb3conv.errors import Sb3Error

POLL_MS = 50
ENTRY_KINDS = {".py": "python", ".html": "browser", ".htm": "browser", ".c": "native"}

LOG_COLORS = {
    "dark": {
        "bg": "#151515",
        "fg": "#d4d4d4",
        "stamp": "#7d7d7d",
        "error": "#ff7b72",
        "warn": "#e3b341",
        "select": "#2f6feb",
    },
    "light": {
        "bg": "#ffffff",
        "fg": "#242424",
        "stamp": "#8a8a8a",
        "error": "#c42b1c",
        "warn": "#9d5d00",
        "select": "#0f6cbd",
    },
}


def apply_theme(root: tk.Tk, mode: str) -> bool:
    """Load the Sun-Valley (Windows 11 style) theme; False when sv-ttk is missing."""
    try:
        import sv_ttk
    except ImportError:
        return False
    sv_ttk.set_theme(mode, root=root)
    return True


def _configure_styles(root: tk.Tk, dark: bool) -> None:
    style = ttk.Style(root)
    style.configure(".", font=("Segoe UI", 10))
    style.configure("TButton", padding=(14, 7))
    style.configure("Accent.TButton", padding=(22, 8), font=("Segoe UI", 10, "bold"))
    style.configure("Toolbutton", padding=(16, 8))
    style.configure("TEntry", padding=(6, 6))
    style.configure("Title.TLabel", font=("Segoe UI", 17, "bold"))
    style.configure("Subtitle.TLabel", font=("Segoe UI", 9))
    style.configure("Head.TLabel", font=("Segoe UI", 9, "bold"))
    style.configure("Status.TLabel", padding=(4, 5))
    hover = "#2d2d2d" if dark else "#e8e8e8"
    style.map(
        "Toolbutton",
        background=[
            ("selected", "#0067c0"),
            ("pressed", "#00538a"),
            ("active", hover),
        ],
        foreground=[("selected", "#ffffff")],
    )


@dataclass(frozen=True)
class RunPlan:
    """How to start a converted project."""

    kind: str  # "python" | "browser" | "native"
    entrypoint: Path
    output_dir: Path


def plan_run(result: ConversionResult) -> RunPlan:
    """Decide how to launch what a conversion produced."""
    entry = (result.output_dir / result.entrypoint).resolve()
    kind = ENTRY_KINDS.get(entry.suffix.lower())
    if kind is None:
        raise Sb3Error(f"cannot run {result.entrypoint!r}: no launcher for that file type")
    return RunPlan(kind=kind, entrypoint=entry, output_dir=result.output_dir.resolve())


def _python_command(entry: Path) -> list[str]:
    if getattr(sys, "frozen", False):
        return [sys.executable, "--run-project", str(entry)]
    return [sys.executable, "-m", "sb3conv.gui", "--run-project", str(entry)]


def launch(plan: RunPlan) -> str:
    """Start the converted project; return a line describing what happened."""
    if plan.kind == "browser":
        webbrowser.open(plan.entrypoint.as_uri())
        return f"opened {plan.entrypoint.name} in the browser"
    if plan.kind == "python":
        subprocess.Popen(_python_command(plan.entrypoint), cwd=plan.output_dir)
        return f"launched {plan.entrypoint.name}"
    from sb3conv.backends.c import build_executable, runtime_env

    executable = build_executable(plan.output_dir)
    subprocess.Popen([str(executable)], cwd=plan.output_dir, env=runtime_env())
    return f"built and launched {executable.name}"


def open_in_file_manager(path: Path) -> None:
    """Reveal a folder in Explorer/Finder/file manager."""
    if hasattr(os, "startfile"):
        os.startfile(str(path))  # type: ignore[attr-defined]
        return
    opener = "open" if sys.platform == "darwin" else "xdg-open"
    subprocess.Popen([opener, str(path)])


def _run_project(args: list[str]) -> int:
    """``--run-project`` mode: play a converted Python project (used by the frozen app)."""
    import pygame  # noqa: F401 -- frozen builds must bundle pygame for generated games

    entry, *extra = args
    path = Path(entry).resolve()
    script_dir = str(path.parent)
    previous_cwd = Path.cwd()
    previous_argv = list(sys.argv)
    os.chdir(script_dir)
    sys.path.insert(0, script_dir)
    # the launcher (not the game) may be frozen; point the runtime at the real manifest
    manifest = path.parent / "sb3_manifest.json"
    if manifest.exists():
        extra = ["--manifest", str(manifest), *extra]
    sys.argv = [str(path), *extra]
    try:
        runpy.run_path(str(path), run_name="__main__")
    finally:
        if script_dir in sys.path:
            sys.path.remove(script_dir)
        os.chdir(previous_cwd)
        sys.argv = previous_argv
    return 0


class ConverterApp:
    """The window: input/output pickers, target choice, log, convert and run actions."""

    def __init__(
        self, root: tk.Tk, initial_input: str | None = None, initial_theme: str = "dark"
    ) -> None:
        self.root = root
        self._messages: queue.Queue[tuple[str, Any]] = queue.Queue()
        self._busy = False
        self._last_result: ConversionResult | None = None
        self._auto_output = ""

        self.input_var = tk.StringVar(value=initial_input or "")
        self.output_var = tk.StringVar()
        self.lang_var = tk.StringVar(value=get_backend(None).name)
        self.scale_var = tk.StringVar(value="2")
        self.fps_var = tk.StringVar(value="30")
        self.build_exe_var = tk.BooleanVar(value=True)

        self._dark = initial_theme != "light"
        apply_theme(root, "dark" if self._dark else "light")
        _configure_styles(root, dark=self._dark)

        self._build()
        self._apply_log_colors()
        self._refresh_default_output()
        self._refresh_buttons()
        self._attach_traces()
        root.after(POLL_MS, self._poll)

        self._log("pick a Scratch .sb3, choose a target, then press Convert")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = self.root
        root.title("Scratch Converter")
        root.geometry("860x620")
        root.minsize(760, 560)

        outer = ttk.Frame(root, padding=16)
        outer.pack(fill="both", expand=True)

        head = ttk.Frame(outer)
        head.pack(fill="x", pady=(0, 16))
        ttk.Label(head, text="Scratch Converter", style="Title.TLabel").pack(side="left")
        ttk.Label(
            head, text=".sb3  ->  Python / JavaScript / C", style="Subtitle.TLabel"
        ).pack(side="left", padx=(14, 0), pady=(8, 0))
        self.theme_btn = ttk.Button(
            head,
            text="Light" if self._dark else "Dark",
            style="Toolbutton",
            command=self._toggle_theme,
        )
        self.theme_btn.pack(side="right")

        ttk.Label(outer, text="PROJECT", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Scratch file (.sb3):", width=18, anchor="e").pack(side="left")
        ttk.Entry(row, textvariable=self.input_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(row, text="Browse...", command=self._browse_input).pack(side="left")

        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 14))
        ttk.Label(row, text="Output folder:", width=18, anchor="e").pack(side="left")
        ttk.Entry(row, textvariable=self.output_var).pack(
            side="left", fill="x", expand=True, padx=8
        )
        ttk.Button(row, text="Browse...", command=self._browse_output).pack(side="left")

        ttk.Label(outer, text="TARGET", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 14))
        for lang in available_languages():
            backend = get_backend(lang)
            ttk.Radiobutton(
                row,
                text=backend.label,
                value=lang,
                variable=self.lang_var,
                command=self._on_lang_changed,
                style="Toolbutton",
            ).pack(side="left", padx=(0, 4))

        ttk.Label(outer, text="OPTIONS", style="Head.TLabel").pack(anchor="w", pady=(0, 4))
        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 14))
        ttk.Label(row, text="Window scale:").pack(side="left")
        ttk.Spinbox(row, from_=1, to=8, textvariable=self.scale_var, width=5).pack(
            side="left", padx=(6, 18)
        )
        ttk.Label(row, text="FPS:").pack(side="left")
        ttk.Spinbox(row, from_=5, to=120, textvariable=self.fps_var, width=6).pack(
            side="left", padx=(6, 0)
        )
        ttk.Checkbutton(
            row,
            text="Build playable app (.exe / .html)",
            variable=self.build_exe_var,
        ).pack(side="right")

        row = ttk.Frame(outer)
        row.pack(fill="x", pady=(0, 12))
        self.convert_btn = ttk.Button(
            row, text="Convert", style="Accent.TButton", command=self._on_convert
        )
        self.convert_btn.pack(side="left")
        self.run_btn = ttk.Button(row, text="Run", command=self._on_run)
        self.run_btn.pack(side="left", padx=(8, 0))
        ttk.Button(
            row, text="Open output folder", command=self._on_open_folder
        ).pack(side="left", padx=(8, 0))

        ttk.Separator(outer).pack(fill="x", pady=(0, 8))
        log_frame = ttk.Frame(outer)
        log_frame.pack(fill="both", expand=True, pady=(0, 8))
        self.log = tk.Text(
            log_frame,
            height=12,
            wrap="word",
            state="disabled",
            font=("Consolas", 9),
            relief="flat",
            borderwidth=0,
            highlightthickness=0,
            padx=10,
            pady=8,
        )
        log_scroll = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_scroll.set)
        log_scroll.pack(side="right", fill="y")
        self.log.pack(side="left", fill="both", expand=True)

        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(
            outer, textvariable=self.status_var, anchor="w", style="Status.TLabel"
        ).pack(fill="x")

    def _attach_traces(self) -> None:
        self.input_var.trace_add("write", self._on_input_changed)
        self.output_var.trace_add("write", lambda *_: self._invalidate_run())
        self.scale_var.trace_add("write", lambda *_: self._invalidate_run())
        self.fps_var.trace_add("write", lambda *_: self._invalidate_run())

    def _log(self, text: str) -> None:
        stamp = datetime.now().strftime("%H:%M:%S")
        if text.startswith("error:"):
            tag: str | None = "error"
        elif text.startswith("warning:"):
            tag = "warn"
        else:
            tag = None
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] ", "stamp")
        self.log.insert("end", f"{text}\n", tag)
        self.log.see("end")
        self.log.configure(state="disabled")

    def _apply_log_colors(self) -> None:
        colors = LOG_COLORS["dark" if self._dark else "light"]
        self.log.configure(
            bg=colors["bg"],
            fg=colors["fg"],
            insertbackground=colors["fg"],
            selectbackground=colors["select"],
        )
        self.log.tag_configure("stamp", foreground=colors["stamp"])
        self.log.tag_configure("error", foreground=colors["error"])
        self.log.tag_configure("warn", foreground=colors["warn"])

    def _toggle_theme(self) -> None:
        mode = "light" if self._dark else "dark"
        if not apply_theme(self.root, mode):
            self._log("error: install sv-ttk for themes (pip install sv-ttk)")
            return
        self._dark = mode == "dark"
        _configure_styles(self.root, dark=self._dark)
        self._apply_log_colors()
        self.theme_btn.configure(text="Light" if self._dark else "Dark")

    # -------------------------------------------------------------- helpers
    def _current_default_output(self) -> str:
        raw = self.input_var.get().strip()
        if not raw:
            return ""
        backend_name = get_backend(self.lang_var.get()).name
        return str(default_output_dir(Path(raw), backend_name))

    def _refresh_default_output(self) -> None:
        current = self.output_var.get().strip()
        new_default = self._current_default_output()
        if not current or current == self._auto_output:
            self.output_var.set(new_default)
        self._auto_output = new_default

    def _invalidate_run(self) -> None:
        self._last_result = None
        self._refresh_buttons()

    def _refresh_buttons(self) -> None:
        self.convert_btn.configure(state="disabled" if self._busy else "normal")
        run_ok = not self._busy and self._last_result is not None
        self.run_btn.configure(state="normal" if run_ok else "disabled")

    def _start_work(self, status: str) -> None:
        self._busy = True
        self.status_var.set(status)
        self._refresh_buttons()

    def _fail(self, message: str) -> None:
        self._log(f"error: {message}")
        self.status_var.set("Error")

    # ------------------------------------------------------------- actions
    def _browse_input(self) -> None:
        chosen = filedialog.askopenfilename(
            title="Choose a Scratch project",
            filetypes=[("Scratch projects", "*.sb3"), ("All files", "*.*")],
        )
        if chosen:
            self.input_var.set(chosen)

    def _browse_output(self) -> None:
        chosen = filedialog.askdirectory(title="Choose the output folder")
        if chosen:
            self.output_var.set(chosen)

    def _on_input_changed(self, *_: object) -> None:
        self._refresh_default_output()
        self._invalidate_run()

    def _on_lang_changed(self) -> None:
        self._refresh_default_output()
        self._invalidate_run()

    def _on_convert(self) -> None:
        if self._busy:
            return
        raw = self.input_var.get().strip()
        if not raw:
            self._fail("choose a .sb3 file first")
            return
        input_path = Path(raw)
        if not input_path.is_file():
            self._fail(f"no such file: {raw}")
            return
        try:
            scale = int(self.scale_var.get())
            fps = int(self.fps_var.get())
        except ValueError:
            self._fail("scale and fps must be whole numbers")
            return
        if scale < 1 or fps < 1:
            self._fail("scale and fps must be positive")
            return
        output = self.output_var.get().strip() or None
        backend_name = get_backend(self.lang_var.get()).name
        build_exe = bool(self.build_exe_var.get())
        self._start_work("Converting...")
        self._log(f"converting {input_path.name} -> {backend_name}")
        threading.Thread(
            target=self._convert_worker,
            args=(input_path, output, backend_name, scale, fps, build_exe),
            daemon=True,
        ).start()

    def _convert_worker(
        self,
        input_path: Path,
        output: str | None,
        backend_name: str,
        scale: int,
        fps: int,
        build_exe: bool,
    ) -> None:
        try:
            result = convert(
                input_path,
                output,
                lang=backend_name,
                scale=scale,
                fps=fps,
                build_exe=build_exe,
                progress=lambda message: self._messages.put(("progress", message)),
            )
        except (Sb3Error, OSError) as exc:
            self._messages.put(("error", str(exc)))
        else:
            self._messages.put(("result", result))

    def _on_run(self) -> None:
        if self._busy or self._last_result is None:
            return
        try:
            plan = plan_run(self._last_result)
        except Sb3Error as exc:
            self._fail(str(exc))
            return
        self._start_work("Running...")
        threading.Thread(target=self._launch_worker, args=(plan,), daemon=True).start()

    def _launch_worker(self, plan: RunPlan) -> None:
        try:
            line = launch(plan)
        except (Sb3Error, OSError) as exc:
            self._messages.put(("error", str(exc)))
        else:
            self._messages.put(("launched", line))

    def _on_open_folder(self) -> None:
        raw = self.output_var.get().strip()
        if not raw:
            self._fail("no output folder yet")
            return
        path = Path(raw)
        if not path.is_dir():
            self._fail("output folder does not exist yet (convert first)")
            return
        try:
            open_in_file_manager(path)
        except OSError as exc:
            self._fail(f"could not open folder: {exc}")

    # --------------------------------------------------------------- poll
    def _poll(self) -> None:
        while True:
            try:
                kind, payload = self._messages.get_nowait()
            except queue.Empty:
                break
            self._handle_message(kind, payload)
        self.root.after(POLL_MS, self._poll)

    def _handle_message(self, kind: str, payload: Any) -> None:
        if kind == "result":
            result: ConversionResult = payload
            self._busy = False
            self._last_result = result
            for warning in result.warnings:
                self._log(f"warning: {warning}")
            self._log(f"done: {len(result.files)} files -> {result.output_dir}")
            if result.artifact is not None:
                self._log(f"app: {result.artifact}")
            self._log(f"entrypoint: {result.entrypoint}")
            if result.artifact is not None:
                self.status_var.set("Converted - app built")
            else:
                self.status_var.set("Converted - press Run")
            self._refresh_buttons()
        elif kind == "progress":
            self._log(str(payload))
            self.status_var.set(str(payload))
        elif kind == "launched":
            self._busy = False
            self._log(str(payload))
            self.status_var.set("Launched")
            self._refresh_buttons()
        elif kind == "error":
            self._busy = False
            self._log(f"error: {payload}")
            self.status_var.set("Error")
            self._refresh_buttons()


def main(argv: list[str] | None = None) -> int:
    """Entry point for ``sb3conv-gui``, ``sb3conv gui`` and ``python -m sb3conv.gui``.

    The regular CLI commands (convert/languages) are accepted too, so the
    frozen app can be scripted as well as clicked.
    """
    args = list(sys.argv[1:] if argv is None else argv)
    if args[:1] == ["--run-project"]:
        if len(args) < 2:
            print("usage: --run-project <main.py> [script args...]", file=sys.stderr)
            return 2
        return _run_project(args[1:])
    if args and args[0] in {"convert", "languages"}:
        from sb3conv.cli import main as cli_main

        return cli_main(args)
    theme = "dark"
    if args[:1] == ["--theme"]:
        if len(args) < 2 or args[1] not in {"dark", "light"}:
            print("usage: --theme dark|light", file=sys.stderr)
            return 2
        theme = args[1]
        args = args[2:]
    initial_input = args[0] if args else None
    try:
        root = tk.Tk()
    except tk.TclError as exc:
        print(f"error: cannot open a window ({exc})", file=sys.stderr)
        return 1
    ConverterApp(root, initial_input=initial_input, initial_theme=theme)
    root.mainloop()
    return 0
