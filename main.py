import sys
import subprocess
import psutil
import os
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PySide6.QtWidgets import (QApplication, QPushButton, QVBoxLayout, QHBoxLayout,
                               QWidget, QMessageBox, QLabel, QGridLayout, QScrollArea,
                               QLineEdit, QDialog, QFormLayout, QDialogButtonBox,
                               QProgressBar, QGroupBox)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QCoreApplication, QSize, QThread, QObject, Signal

import ast

import settings
import settings_io
import library
import omdb_client


class FetchWorker(QObject):
    """Runs library enrichment off the UI thread. `data_types` is a set drawn
    from {"posters", "ratings", "watchtime", "episodes"} - one worker can do
    any combination, so "Fetch All" is just all four at once."""

    progress = Signal(int, int, str)   # done, total, message
    finished = Signal(dict)            # summary counts
    error = Signal(str)

    def __init__(self, data_types):
        super().__init__()
        self.data_types = set(data_types)
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        try:
            titles = list(library.scan_titles())
        except Exception as e:
            self.error.emit(f"Could not scan library: {e}")
            return

        total = len(titles)
        summary = {"processed": 0, "errors": 0}
        for key in self.data_types:
            summary[key] = 0

        for i, (category, title, title_path) in enumerate(titles, start=1):
            if self._stop:
                break
            self.progress.emit(i, total, f"{category} / {title}")
            try:
                info = omdb_client.lookup_title(title)
            except omdb_client.OMDbError as e:
                summary["errors"] += 1
                continue
            except Exception as e:
                summary["errors"] += 1
                continue

            if "posters" in self.data_types:
                try:
                    if library.download_poster(title, info):
                        summary["posters"] += 1
                except Exception:
                    pass
            if "ratings" in self.data_types:
                if library.get_rating(info) is not None:
                    summary["ratings"] += 1
            if "watchtime" in self.data_types:
                if library.total_watch_minutes(info, title_path) is not None:
                    summary["watchtime"] += 1
            if "episodes" in self.data_types:
                try:
                    if library.episode_audit(info, title_path) is not None:
                        summary["episodes"] += 1
                except Exception:
                    pass

            summary["processed"] += 1

        self.finished.emit(summary)


class SplashProgress:
    """A small Tkinter loading window with a progress bar, showing the
    current category and title as the media library is scanned."""

    def __init__(self, total):
        self.root = tk.Tk()
        self.root.title(settings.window_title)
        self.root.configure(bg="#3c3c3c")  # slight gray background
        self.root.geometry("460x150")
        self.root.resizable(False, False)

        icon_path = Path(settings.app_icon)
        if icon_path.exists():
            try:
                self.root.iconphoto(True, tk.PhotoImage(file=str(icon_path)))
            except tk.TclError:
                pass

        # Center the window on screen
        self.root.update_idletasks()
        w, h = 460, 150
        x = (self.root.winfo_screenwidth() - w) // 2
        y = (self.root.winfo_screenheight() - h) // 2
        self.root.geometry(f"{w}x{h}+{x}+{y}")

        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(
            "Splash.Horizontal.TProgressbar",
            troughcolor="#2a2a2a",
            background="#6ea0ff",
            bordercolor="#3c3c3c",
        )

        self.progress = ttk.Progressbar(
            self.root,
            style="Splash.Horizontal.TProgressbar",
            orient="horizontal",
            length=400,
            mode="determinate",
            maximum=max(1, total),
        )
        self.progress.pack(pady=(24, 16))

        self.category_label = tk.Label(
            self.root, text="", bg="#3c3c3c", fg="#e0e0e0",
            font=("Segoe UI", 11, "bold"),
        )
        self.category_label.pack()

        self.title_label = tk.Label(
            self.root, text="", bg="#3c3c3c", fg="#b0b0b0",
            font=("Segoe UI", 9),
        )
        self.title_label.pack(pady=(4, 0))

        self.root.update()

    def update(self, category, title):
        self.category_label.config(text=category)
        self.title_label.config(text=title)
        self.progress["value"] += 1
        self.root.update()

    def close(self):
        self.root.destroy()

class SettingsDialog(QDialog):
    """A modal showing every setting from settings.py as a text box. Saving
    writes the edited values back to the file, preserving comments."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumWidth(520)

        self.values = settings_io.load()
        self.fields = {}  # name -> (QLineEdit, original_value)

        outer = QVBoxLayout(self)

        # Scrollable form so many settings still fit on smaller screens.
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        form_host = QWidget()
        form = QFormLayout(form_host)

        for name, value in self.values.items():
            edit = QLineEdit(form_host)
            # Strings show their raw text; everything else shows its literal
            # (e.g. lists as ["a", "b"], numbers as 0.001) so it round-trips.
            edit.setText(value if isinstance(value, str) else repr(value))
            self.fields[name] = (edit, value)
            form.addRow(name, edit)

        scroll.setWidget(form_host)
        outer.addWidget(scroll)

        # --- Fetch Online Data section (not part of settings.py) ------------
        outer.addWidget(self._build_fetch_section())

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Save | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.save)
        buttons.rejected.connect(self.reject)
        outer.addWidget(buttons)

        # Thread state for the background fetch.
        self._thread = None
        self._worker = None
        self._fetch_buttons = []

    def _build_fetch_section(self):
        box = QGroupBox("Fetch Online Data (OMDb / IMDb)")
        v = QVBoxLayout(box)

        # One button per data type, plus Fetch All. Each maps to the set of
        # data_types passed to the worker.
        row = QHBoxLayout()
        specs = [
            ("Posters", {"posters"}),
            ("Ratings", {"ratings"}),
            ("Watch Time", {"watchtime"}),
            ("Episodes", {"episodes"}),
        ]
        self._fetch_buttons = []
        for label, types in specs:
            btn = QPushButton(label)
            btn.clicked.connect(lambda _=False, t=types: self.start_fetch(t))
            row.addWidget(btn)
            self._fetch_buttons.append(btn)
        v.addLayout(row)

        all_btn = QPushButton("Fetch All Data Types")
        all_btn.clicked.connect(
            lambda: self.start_fetch({"posters", "ratings", "watchtime", "episodes"})
        )
        v.addWidget(all_btn)
        self._fetch_buttons.append(all_btn)

        self.fetch_progress = QProgressBar()
        self.fetch_progress.setVisible(False)
        v.addWidget(self.fetch_progress)

        self.fetch_status = QLabel("")
        self.fetch_status.setWordWrap(True)
        v.addWidget(self.fetch_status)

        return box

    def start_fetch(self, data_types):
        if self._thread is not None:
            return  # a fetch is already running

        for btn in self._fetch_buttons:
            btn.setEnabled(False)
        self.fetch_progress.setVisible(True)
        self.fetch_progress.setRange(0, 0)  # indeterminate until first tick
        self.fetch_status.setText("Scanning library...")

        self._thread = QThread(self)
        self._worker = FetchWorker(data_types)
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_fetch_progress)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.error.connect(self._on_fetch_error)
        self._thread.start()

    def _on_fetch_progress(self, done, total, message):
        if total:
            self.fetch_progress.setRange(0, total)
            self.fetch_progress.setValue(done)
        self.fetch_status.setText(f"{done}/{total}  -  {message}")

    def _on_fetch_finished(self, summary):
        self._teardown_thread()
        parts = [f"Processed {summary.get('processed', 0)} titles"]
        for key in ("posters", "ratings", "watchtime", "episodes"):
            if key in summary:
                parts.append(f"{key}: {summary[key]}")
        if summary.get("errors"):
            parts.append(f"errors: {summary['errors']}")
        self.fetch_status.setText("Done. " + ", ".join(parts))
        self.fetch_progress.setVisible(False)

    def _on_fetch_error(self, message):
        self._teardown_thread()
        self.fetch_progress.setVisible(False)
        self.fetch_status.setText("")
        QMessageBox.critical(self, "Fetch failed", message)

    def _teardown_thread(self):
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
            self._thread = None
            self._worker = None
        for btn in self._fetch_buttons:
            btn.setEnabled(True)

    def save(self):
        new_values = {}
        for name, (edit, original) in self.fields.items():
            text = edit.text()
            if isinstance(original, str):
                new_values[name] = text  # keep strings as-is
            else:
                # Parse non-strings (lists, numbers, bools) as Python literals.
                try:
                    new_values[name] = ast.literal_eval(text)
                except (ValueError, SyntaxError):
                    QMessageBox.warning(
                        self, "Invalid value",
                        f"'{name}' is not a valid value:\n{text}",
                    )
                    return

        try:
            settings_io.save(new_values)
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Could not save settings:\n{e}")
            return

        QMessageBox.information(
            self, "Settings saved",
            "Settings were written to settings.py.\n"
            "Restart the app for all changes to take effect.",
        )
        self.accept()

    def closeEvent(self, event):
        # Never leave a running fetch thread orphaned when the modal closes.
        if self._worker is not None:
            self._worker.stop()
        self._teardown_thread()
        super().closeEvent(event)


class MediaMimicApp(QWidget):
    def __init__(self):
        super().__init__()

        # Set up the UI
        self.setWindowTitle(settings.window_title)

        # Define the directory path
        self.directory_path = settings.media_path

        # Current search text (lowercased); empty means "show everything"
        self.search_query = ""

        # Search bar - filters visible titles as you type
        self.search_bar = QLineEdit(self)
        self.search_bar.setPlaceholderText("Search titles...")
        self.search_bar.setClearButtonEnabled(True)
        self.search_bar.textChanged.connect(self.on_search_changed)
        # Make the search bar taller and larger-typed.
        self.search_bar.setStyleSheet("font-size: 18px; padding: 8px;")

        # Cog button next to the search bar - opens the settings modal.
        self.settings_button = QPushButton("⚙", self)  # gear glyph
        self.settings_button.setToolTip("Settings")
        self.settings_button.setFixedSize(44, 44)
        self.settings_button.setStyleSheet("font-size: 20px;")
        self.settings_button.clicked.connect(self.open_settings)

        # Row holding the search bar (stretching) and the cog on its right.
        self.search_row = QHBoxLayout()
        self.search_row.addWidget(self.search_bar)
        self.search_row.addWidget(self.settings_button)

        # Create a scroll area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)

        # Create a widget to hold the main layout
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        # Tighten the top so categories sit up near the search bar, and keep
        # content aligned to the top rather than vertically centered.
        self.main_layout.setContentsMargins(4, 0, 4, 4)
        self.main_layout.setSpacing(4)
        self.main_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll_area.setWidget(self.main_widget)

        # Set the layout to the main window
        layout = QVBoxLayout(self)
        layout.addLayout(self.search_row)
        layout.addWidget(self.scroll_area)
        self.setLayout(layout)

        # Store category data
        self.categories = []

        # Create buttons for each title found
        self.create_buttons()

        # Connect the resize event
        self.resizeEvent = self.on_resize

    def _is_visible_dir(self, base, name):
        return (os.path.isdir(os.path.join(base, name))
                and not name.startswith(tuple(settings.blacklisted_starting_characters))
                and name not in settings.blacklisted_directories)

    def create_buttons(self):
        if os.path.exists(self.directory_path) and os.path.isdir(self.directory_path):
            directories = [d for d in os.listdir(self.directory_path)
                           if self._is_visible_dir(self.directory_path, d)]

            # Count total titles up front so the progress bar is determinate
            total_titles = 0
            for category in directories:
                cat_path = os.path.join(self.directory_path, category)
                total_titles += sum(1 for s in os.listdir(cat_path)
                                    if self._is_visible_dir(cat_path, s))

            splash = SplashProgress(total_titles)

            for category in directories:
                # Create a header label for the category
                header_label = QLabel(category, self)
                header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
                header_label.setStyleSheet("font-size: 20px; font-weight: bold;")
                self.main_layout.addWidget(header_label)

                # Create a grid layout for this category, left-aligned so the
                # cards hug the left edge instead of stretching/centering.
                category_grid = QGridLayout()
                category_grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
                self.main_layout.addLayout(category_grid)

                buttons = []

                # Get the list of series titles within the category directory
                cat_path = os.path.join(self.directory_path, category)
                series_titles = [s for s in os.listdir(cat_path)
                                 if self._is_visible_dir(cat_path, s)]

                for title in series_titles:
                    splash.update(category, title)

                    # Create a button for each title
                    button = QPushButton(self)
                    button.clicked.connect(self.create_button_click_handler(title, category))

                    # Set the button size to 200 x 300
                    button.setFixedSize(200, 300)

                    # Set the button layout
                    button_layout = QVBoxLayout()

                    # Add the image to the button
                    image_path = os.path.join(settings.poster_path, f"{title}.jpg")

                    image_label = QLabel(self)
                    pixmap = QPixmap(str(image_path))

                    if pixmap.isNull():
                        default_image_path = settings.default_poster
                        pixmap = QPixmap(str(default_image_path))

                    if not pixmap.isNull():
                        image_label.setPixmap(pixmap.scaled(180, 270, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
                        image_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                        button_layout.addWidget(image_label)

                    # Add the text to the button
                    text_label = QLabel(title, self)
                    text_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                    button_layout.addWidget(text_label)

                    # Set the layout to the button
                    button.setLayout(button_layout)

                    # Remember the title on the button for search filtering
                    button.setProperty("title", title)

                    buttons.append(button)

                # Store category data (header + grid + its buttons) so the
                # search filter can show/hide titles and empty categories.
                self.categories.append((header_label, category_grid, buttons))

                # Add some spacing between categories
                self.main_layout.addSpacing(20)

            splash.close()

        # Initial layout adjustment
        self.adjust_grid_layout()

    def open_settings(self):
        dialog = SettingsDialog(self)
        dialog.exec()

    def on_search_changed(self, text):
        # Store the query lowercased and re-filter the grid.
        self.search_query = text.strip().lower()
        self.adjust_grid_layout()

    def create_button_click_handler(self, title, category):
        def button_click_handler():
            self.open_video(title, category)
        return button_click_handler

    def _matches_search(self, title):
        # Empty query matches everything; otherwise case-insensitive substring.
        if not self.search_query:
            return True
        return self.search_query in title.lower()

    def adjust_grid_layout(self):
        available_width = self.scroll_area.viewport().width()
        button_width = 200  # Width of each button
        spacing = 10  # Assuming 10px spacing between buttons
        num_columns = max(1, (available_width + spacing) // (button_width + spacing))

        for header_label, category_grid, buttons in self.categories:
            # Clear the grid layout (detach every button, keep it alive)
            for i in reversed(range(category_grid.count())):
                category_grid.itemAt(i).widget().setParent(None)

            # Place only the buttons whose title matches the search; hide the
            # rest. A category with no matches hides its header too.
            visible_index = 0
            for button in buttons:
                if self._matches_search(button.property("title")):
                    row = visible_index // num_columns
                    col = visible_index % num_columns
                    category_grid.addWidget(button, row, col)
                    button.show()
                    visible_index += 1
                else:
                    button.hide()

            header_label.setVisible(visible_index > 0)

    def on_resize(self, event):
        self.adjust_grid_layout()
        super().resizeEvent(event)

    def is_vlc_running(self):
        # Check if VLC is running
        for proc in psutil.process_iter(['pid', 'name']):
            if proc.info['name'] == 'vlc.exe':  # Adjust the name for different OS (e.g., 'vlc' on Unix-like systems)
                return True
        return False

    def open_video(self, title, category):
        print(f"DEBUG: open_video called with title={title}, category={category}")

        # Path to the video folder
        video_folder_path = f"directory:///{settings.media_path}{category}/{title}"
        print(f"DEBUG: Video folder path: {video_folder_path}")

        # Full path to the VLC executable
        vlc_path = r"C:/Program Files/VideoLAN/VLC/vlc.exe"

        # Check if VLC is running
        if not self.is_vlc_running():
            QMessageBox.warning(self, "VLC Not Found", "Please open VLC first.")
            return

        # Use subprocess to open the video folder in the existing VLC instance
        try:
            print(f"DEBUG: Attempting to open VLC with path: {video_folder_path}")
            subprocess.Popen([vlc_path, '--started-from-file', '--recursive', '--playlist-enqueue', str(video_folder_path)], shell=True)
            print(f"DEBUG: Subprocess command executed: {vlc_path} --started-from-file --recursive --playlist-enqueue {video_folder_path}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Failed to open video folder: {e}")
            print(f"DEBUG: Error occurred: {e}")

if __name__ == "__main__":
    # Under pythonw.exe (no console) sys.stdout/stderr are None, so any print()
    # would raise. Redirect them to a null sink so debug prints are harmless.
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")

    app = QApplication(sys.argv)

    # Set the application icon (taskbar + all windows). On Windows, an explicit
    # AppUserModelID is needed for the taskbar to pick up our icon rather than
    # python.exe's default one.
    icon_path = Path(settings.app_icon)
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))
        if sys.platform == "win32":
            try:
                import ctypes
                ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                    "mediamimic.app"
                )
            except Exception as e:
                print(f"Could not set AppUserModelID: {e}")
    else:
        print(f"Icon not found at: {icon_path}")

    window = MediaMimicApp()
    window.showMaximized()

    sys.exit(app.exec())