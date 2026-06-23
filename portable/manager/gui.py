from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk
from model_profiles import get_active_profile_id, list_profiles


if getattr(sys, "frozen", False):
    PORTABLE_ROOT = Path(sys.executable).resolve().parent
else:
    PORTABLE_ROOT = Path(__file__).resolve().parents[1]
LOG_FILE = PORTABLE_ROOT / "logs" / "server.log"


def find_python() -> str:
    runtime_python = PORTABLE_ROOT / "runtime" / "python.exe"
    if runtime_python.exists():
        return str(runtime_python)
    runtime_venv_python = PORTABLE_ROOT / "runtime" / "Scripts" / "python.exe"
    if runtime_venv_python.exists():
        return str(runtime_venv_python)
    return sys.executable


def find_server_script() -> Path | None:
    for candidate in (PORTABLE_ROOT / "hifiserver.py", PORTABLE_ROOT.parent / "hifiserver.py"):
        if candidate.exists():
            return candidate
    return None


def process_env() -> dict[str, str]:
    env = os.environ.copy()
    env["HIFISAMPLER_CONFIG"] = str(PORTABLE_ROOT / "config.yaml")
    env["HIFISAMPLER_DEFAULT_CONFIG"] = str(PORTABLE_ROOT / "config.default.yaml")
    return env


class HifisamplerManager(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.python = find_python()
        self.task_running = False
        self.server_process: subprocess.Popen[str] | None = None
        self.server_thread: threading.Thread | None = None
        self.output_queue: queue.Queue[object] = queue.Queue()

        ctk.set_appearance_mode("light")
        ctk.set_default_color_theme("blue")

        self.title("Hifisampler Manager")
        self.geometry("940x660")
        self.minsize(860, 560)

        self.status_var = tk.StringVar(value="Ready")
        self.server_var = tk.StringVar(value="Server: stopped")
        self.openutau_var = tk.StringVar()
        self.model_var = tk.StringVar(value="")
        self.profile_name_to_id: dict[str, str] = {}

        self._build_ui()
        self.refresh_model_profiles()
        self._poll_output()

    def _build_ui(self) -> None:
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)

        header = ctk.CTkFrame(self, fg_color="transparent")
        header.grid(row=0, column=0, sticky="ew", padx=20, pady=(18, 8))
        header.grid_columnconfigure(0, weight=1)

        title = ctk.CTkLabel(header, text="Hifisampler Manager", font=ctk.CTkFont(size=26, weight="bold"))
        title.grid(row=0, column=0, sticky="w")
        server_label = ctk.CTkLabel(header, textvariable=self.server_var, font=ctk.CTkFont(size=13))
        server_label.grid(row=0, column=1, sticky="e")

        actions = ctk.CTkFrame(self, corner_radius=8)
        actions.grid(row=1, column=0, sticky="ew", padx=20, pady=8)
        for column in range(4):
            actions.grid_columnconfigure(column, weight=1)

        self.prepare_button = ctk.CTkButton(actions, text="Prepare Portable", command=self.prepare_portable)
        self.check_button = ctk.CTkButton(actions, text="Check Environment", command=self.check_environment)
        self.start_button = ctk.CTkButton(actions, text="Start Server", command=self.start_server)
        self.stop_button = ctk.CTkButton(actions, text="Stop Server", command=self.stop_server, state=tk.DISABLED)
        self.install_button = ctk.CTkButton(actions, text="Install to OpenUTAU", command=self.install_openutau)
        self.open_logs_button = ctk.CTkButton(actions, text="Open Logs Folder", command=self.open_logs_folder)
        self.open_log_button = ctk.CTkButton(actions, text="Open Server Log", command=self.open_server_log)
        self.clear_button = ctk.CTkButton(actions, text="Clear Output", command=self.clear_output)
        self.apply_model_button = ctk.CTkButton(actions, text="Apply Model", command=self.apply_model_profile)

        self.prepare_button.grid(row=0, column=0, sticky="ew", padx=8, pady=(10, 6))
        self.check_button.grid(row=0, column=1, sticky="ew", padx=8, pady=(10, 6))
        self.start_button.grid(row=0, column=2, sticky="ew", padx=8, pady=(10, 6))
        self.stop_button.grid(row=0, column=3, sticky="ew", padx=8, pady=(10, 6))

        model_label = ctk.CTkLabel(actions, text="Model", anchor="w")
        model_label.grid(row=1, column=0, sticky="ew", padx=8, pady=6)
        self.model_menu = ctk.CTkOptionMenu(actions, variable=self.model_var, values=["No profiles found"])
        self.model_menu.grid(row=1, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        self.apply_model_button.grid(row=1, column=3, sticky="ew", padx=8, pady=6)

        self.install_button.grid(row=2, column=0, sticky="ew", padx=8, pady=6)
        self.openutau_entry = ctk.CTkEntry(actions, textvariable=self.openutau_var, placeholder_text="OpenUTAU folder")
        self.openutau_entry.grid(row=2, column=1, columnspan=2, sticky="ew", padx=8, pady=6)
        self.browse_button = ctk.CTkButton(actions, text="Browse", command=self.browse_openutau)
        self.browse_button.grid(row=2, column=3, sticky="ew", padx=8, pady=6)

        self.open_logs_button.grid(row=3, column=0, sticky="ew", padx=8, pady=(6, 10))
        self.open_log_button.grid(row=3, column=1, sticky="ew", padx=8, pady=(6, 10))
        self.clear_button.grid(row=3, column=2, sticky="ew", padx=8, pady=(6, 10))

        output_panel = ctk.CTkFrame(self, corner_radius=8)
        output_panel.grid(row=2, column=0, sticky="nsew", padx=20, pady=8)
        output_panel.grid_rowconfigure(1, weight=1)
        output_panel.grid_columnconfigure(0, weight=1)

        output_label = ctk.CTkLabel(output_panel, text="Output", font=ctk.CTkFont(size=14, weight="bold"))
        output_label.grid(row=0, column=0, sticky="w", padx=12, pady=(10, 4))
        self.output = ctk.CTkTextbox(output_panel, wrap="none", font=("Consolas", 11))
        self.output.grid(row=1, column=0, sticky="nsew", padx=12, pady=(4, 12))

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.grid(row=3, column=0, sticky="ew", padx=20, pady=(4, 14))
        footer.grid_columnconfigure(0, weight=1)
        status = ctk.CTkLabel(footer, textvariable=self.status_var, anchor="w")
        status.grid(row=0, column=0, sticky="ew")

    def append_output(self, text: str) -> None:
        self.output.insert(tk.END, text)
        self.output.see(tk.END)

    def append_line(self, text: str) -> None:
        self.append_output(text.rstrip() + "\n")

    def clear_output(self) -> None:
        self.output.delete("1.0", tk.END)

    def set_task_buttons(self, enabled: bool) -> None:
        state = tk.NORMAL if enabled else tk.DISABLED
        self.prepare_button.configure(state=state)
        self.check_button.configure(state=state)
        self.install_button.configure(state=state)
        self.browse_button.configure(state=state)
        self.apply_model_button.configure(state=state)

    def run_task(self, script_name: str, args: list[str] | None = None, after=None) -> None:
        if self.task_running:
            messagebox.showinfo("Task Running", "A task is already running.")
            return

        script = PORTABLE_ROOT / "manager" / script_name
        if not script.exists():
            messagebox.showerror("Missing File", f"Missing manager script:\n{script}")
            return

        self.task_running = True
        self.set_task_buttons(False)
        self.status_var.set(f"Running {script_name}...")
        self.append_line(f"> {script_name}")

        thread = threading.Thread(
            target=self._task_worker,
            args=([self.python, str(script), *(args or [])], after),
            daemon=True,
        )
        thread.start()

    def _task_worker(self, command: list[str], after) -> None:
        exit_code = 1
        try:
            process = subprocess.Popen(
                command,
                cwd=PORTABLE_ROOT,
                env=process_env(),
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
            if process.stdout:
                for line in process.stdout:
                    self.output_queue.put(line)
            exit_code = process.wait()
        except Exception as exc:
            self.output_queue.put(f"ERROR: {exc}\n")
        self.output_queue.put(("TASK_DONE", exit_code, after))

    def _poll_output(self) -> None:
        while True:
            try:
                item = self.output_queue.get_nowait()
            except queue.Empty:
                break
            if isinstance(item, tuple) and item[0] == "TASK_DONE":
                self._finish_task(item[1], item[2])
            elif isinstance(item, tuple) and item[0] == "SERVER_DONE":
                self._server_finished(item[1])
            else:
                self.append_output(str(item))
        self.after(100, self._poll_output)

    def _finish_task(self, exit_code: int, after) -> None:
        self.task_running = False
        self.set_task_buttons(True)
        self.status_var.set("Ready" if exit_code == 0 else f"Task failed with exit code {exit_code}")
        self.append_line(f"> Task finished with exit code {exit_code}")
        if after:
            after(exit_code)

    def prepare_portable(self) -> None:
        self.run_task("prepare_portable.py", after=lambda _exit_code: self.refresh_model_profiles())

    def check_environment(self) -> None:
        self.run_task("check_environment.py")

    def refresh_model_profiles(self) -> None:
        try:
            profiles = list_profiles()
            self.profile_name_to_id = {profile.name: profile.profile_id for profile in profiles}
            names = list(self.profile_name_to_id)
            if not names:
                self.model_menu.configure(values=["No profiles found"])
                self.model_var.set("No profiles found")
                self.apply_model_button.configure(state=tk.DISABLED)
                return

            self.model_menu.configure(values=names)
            active_profile_id = get_active_profile_id()
            active_name = next((profile.name for profile in profiles if profile.profile_id == active_profile_id), names[0])
            self.model_var.set(active_name)
            self.apply_model_button.configure(state=tk.NORMAL)
        except Exception as exc:
            self.model_menu.configure(values=["Profile error"])
            self.model_var.set("Profile error")
            self.apply_model_button.configure(state=tk.DISABLED)
            self.append_line(f"ERROR: failed to load model profiles: {exc}")

    def apply_model_profile(self) -> None:
        profile_name = self.model_var.get()
        profile_id = self.profile_name_to_id.get(profile_name)
        if not profile_id:
            messagebox.showerror("Model Profile", "Select a valid model profile.")
            return
        if self.server_process is not None:
            messagebox.showinfo("Restart Required", "The model change will apply after you restart the server.")
        self.run_task("model_profiles.py", ["--apply", profile_id], after=lambda _exit_code: self.refresh_model_profiles())

    def browse_openutau(self) -> None:
        folder = filedialog.askdirectory(title="Select OpenUTAU Folder")
        if folder:
            self.openutau_var.set(folder)

    def install_openutau(self) -> None:
        path = self.openutau_var.get().strip().strip('"')
        if not path:
            self.browse_openutau()
            path = self.openutau_var.get().strip().strip('"')
        if path:
            self.run_task("install_openutau.py", [path])

    def start_server(self) -> None:
        if self.server_process is not None:
            messagebox.showinfo("Server Running", "The server is already running.")
            return

        server = find_server_script()
        if server is None:
            messagebox.showerror("Missing File", "hifiserver.py was not found.")
            return

        self.append_line("> Preparing portable folder before server start")
        self.run_task("prepare_portable.py", after=lambda exit_code: self._start_server_after_prepare(exit_code, server))

    def _start_server_after_prepare(self, exit_code: int, server: Path) -> None:
        if exit_code != 0:
            self.append_line(f"> Server start canceled. Preparation failed with exit code {exit_code}")
            return

        LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        self.append_line(f"> Starting server: {server}")
        self.status_var.set("Starting server...")
        self.server_var.set("Server: starting")
        self.start_button.configure(state=tk.DISABLED)
        self.stop_button.configure(state=tk.NORMAL)

        self.server_thread = threading.Thread(target=self._server_worker, args=(server,), daemon=True)
        self.server_thread.start()

    def _server_worker(self, server: Path) -> None:
        exit_code = 1
        try:
            with LOG_FILE.open("a", encoding="utf-8") as log:
                self.server_process = subprocess.Popen(
                    [self.python, str(server)],
                    cwd=PORTABLE_ROOT,
                    env=process_env(),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.STDOUT,
                    text=True,
                    encoding="utf-8",
                    errors="replace",
                )
                if self.server_process.stdout:
                    for line in self.server_process.stdout:
                        log.write(line)
                        log.flush()
                        self.output_queue.put(line)
                exit_code = self.server_process.wait()
        except Exception as exc:
            self.output_queue.put(f"ERROR: {exc}\n")
        self.output_queue.put(("SERVER_DONE", exit_code))

    def stop_server(self) -> None:
        if self.server_process is None:
            return
        self.append_line("> Stopping server")
        self.server_process.terminate()
        try:
            self.server_process.wait(timeout=3)
        except subprocess.TimeoutExpired:
            self.server_process.kill()

    def _server_finished(self, exit_code: int) -> None:
        self.server_process = None
        self.start_button.configure(state=tk.NORMAL)
        self.stop_button.configure(state=tk.DISABLED)
        self.server_var.set("Server: stopped")
        self.status_var.set("Server stopped" if exit_code == 0 else f"Server stopped with exit code {exit_code}")
        self.append_line(f"> Server stopped with exit code {exit_code}")

    def open_logs_folder(self) -> None:
        path = PORTABLE_ROOT / "logs"
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def open_server_log(self) -> None:
        if not LOG_FILE.exists():
            messagebox.showinfo("Log Missing", "server.log does not exist yet.")
            return
        os.startfile(LOG_FILE)

    def destroy(self) -> None:
        if self.server_process is not None:
            answer = messagebox.askyesno("Server Running", "The hifisampler server is still running. Stop it and exit?")
            if not answer:
                return
            self.stop_server()
        super().destroy()


def main() -> int:
    app = HifisamplerManager()
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
