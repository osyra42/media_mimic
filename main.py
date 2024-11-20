import sys
import subprocess
import psutil
import os
import time
from pathlib import Path
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QHBoxLayout, QWidget, QMessageBox, QLabel, QGridLayout, QScrollArea
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import Qt, QCoreApplication, QSize

import settings

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
        
        icon_path = Path(settings.app_icon)
        if icon_path.exists():
            self.setWindowIcon(QIcon(str(icon_path)))
        else:
            print(f"Icon not found at: {icon_path}")

        # Store category data
        self.categories = []

        # Create buttons for each title found
        self.create_buttons()

        # Connect the resize event
        self.resizeEvent = self.on_resize

    def create_buttons(self):
        if os.path.exists(self.directory_path) and os.path.isdir(self.directory_path):
            directories = [d for d in os.listdir(self.directory_path)
                        if os.path.isdir(os.path.join(self.directory_path, d))
                        and not d.startswith(tuple(settings.blacklisted_starting_characters))
                        and d not in settings.blacklisted_directories]

            for category in directories:
                print(f"LOOKN | In Category {category} . . .")
                time.sleep(0.15)

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
                series_titles = [
                    s for s in os.listdir(os.path.join(self.directory_path, category))
                    if os.path.isdir(os.path.join(self.directory_path, category, s))
                    and not s.startswith(tuple(settings.blacklisted_starting_characters))
                    and s not in settings.blacklisted_directories
                ]

                for title in series_titles:
                    print(f"FOUND | {title}")
                    time.sleep(0.005)

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
    app = QApplication(sys.argv)

    window = MediaMimicApp()
    window.show()

    sys.exit(app.exec())