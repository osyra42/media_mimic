import sys
import subprocess
import psutil
import os
import time
import tkinter as tk
from tkinter import ttk
from pathlib import Path
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, QLabel, QGridLayout, QScrollArea
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QCoreApplication, QSize

import settings


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

class MediaMimicApp(QWidget):
    def __init__(self):
        super().__init__()

        # Set up the UI
        self.setWindowTitle(settings.window_title)

        # Define the directory path
        self.directory_path = settings.media_path

        # Create a scroll area
        self.scroll_area = QScrollArea(self)
        self.scroll_area.setWidgetResizable(True)

        # Create a widget to hold the main layout
        self.main_widget = QWidget()
        self.main_layout = QVBoxLayout(self.main_widget)
        self.scroll_area.setWidget(self.main_widget)

        # Set the layout to the main window
        layout = QVBoxLayout(self)
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
                header_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
                header_label.setStyleSheet("font-size: 20px; font-weight: bold;")
                self.main_layout.addWidget(header_label)

                # Create a grid layout for this category
                category_grid = QGridLayout()
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

                    buttons.append(button)

                # Store category data
                self.categories.append((category_grid, buttons))

                # Add some spacing between categories
                self.main_layout.addSpacing(20)

            splash.close()

        # Initial layout adjustment
        self.adjust_grid_layout()

    def create_button_click_handler(self, title, category):
        def button_click_handler():
            self.open_video(title, category)
        return button_click_handler

    def adjust_grid_layout(self):
        available_width = self.scroll_area.viewport().width()
        button_width = 200  # Width of each button
        spacing = 10  # Assuming 10px spacing between buttons
        num_columns = max(1, (available_width + spacing) // (button_width + spacing))

        for category_grid, buttons in self.categories:
            # Clear the grid layout
            for i in reversed(range(category_grid.count())):
                category_grid.itemAt(i).widget().setParent(None)

            # Add buttons to the grid layout
            for i, button in enumerate(buttons):
                row = i // num_columns
                col = i % num_columns
                category_grid.addWidget(button, row, col)

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