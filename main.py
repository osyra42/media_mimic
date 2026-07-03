# --- Standard library ---
import ast
import datetime
import os
import subprocess
import sys
import webbrowser
from pathlib import Path

# --- Third party ---
import psutil
from PySide6.QtWidgets import (QApplication, QPushButton, QVBoxLayout, QHBoxLayout,
                               QWidget, QMessageBox, QLabel, QGridLayout, QScrollArea,
                               QLineEdit, QDialog, QFormLayout, QDialogButtonBox,
                               QProgressBar, QGroupBox, QCheckBox, QFrame)
from PySide6.QtGui import QPixmap, QIcon
from PySide6.QtCore import (Qt, QThread, QObject, Signal, QTimer,
                            QPropertyAnimation, QRect, QEasingCurve)

# --- Local (support modules live in core/; put it on sys.path first) ---
SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR / "core"))

import settings
import settings_io
import library
import omdb_client
from paths import project_path


def asset_path(relative):
    """Return an absolute Path for a project asset, resolved against the
    project root so it works regardless of the process's working directory."""
    return project_path(relative)


# --- Card geometry (kept uniform so the grid stays tidy) --------------------
# Layout: poster on the left, stats stacked on the right, description across
# the bottom. A trading card TURNED SIDEWAYS: landscape 7:5 (1.4), so wider
# than tall.
CARD_WIDTH = 322
CARD_HEIGHT = 230               # 322:230 == 7:5, a card on its side
CARD_SPACING = 16               # breathing room between cards in the grid

# Poster fills the left column at a true 2:3 shape.
POSTER_HEIGHT = 170
POSTER_WIDTH = POSTER_HEIGHT * 2 // 3   # == 113, true 2:3 poster

# Expanded (zoomed) detail panel size.
EXPANDED_WIDTH = 760
EXPANDED_HEIGHT = 460

# --- Theater theme -----------------------------------------------------------
# The whole app dresses like a playhouse: deep velvet-curtain reds and stage
# golds against a dim, warm near-black house.
CURTAIN_RED = "#7c1420"       # deep velvet curtain - primary accent
CURTAIN_RED_LIGHT = "#a01e2d"  # brighter red for hover/highlights
STAGE_GOLD = "#d4af37"        # brass/gold trim, ratings, headings
STAGE_GOLD_SOFT = "#e6c976"   # softer gold for secondary text
HOUSE_DARK = "#1a1012"        # dim warm house (card/panel background)
HOUSE_DARKER = "#120b0d"      # deeper backdrop
PLAYBILL_CREAM = "#f0e6d2"    # warm off-white body text
PLAYBILL_DIM = "#b9a99a"      # muted warm text for secondary info


def completeness_badge(has_data, media_type, audit):
    """Return (icon, color, tooltip) for the poster corner badge. Every card
    shows exactly one state, and the icon only claims what we can prove:
      ✗ no data · ● completeness unknown · ✔ verified complete · ⬆ upgrades."""
    if not has_data:
        return ("✗", "#c94a4a", "No data - not fetched yet")
    if audit:
        on_disk = audit.get("on_disk", 0)
        total = audit.get("imdb_total", 0)
        missing = audit.get("missing_count", 0)
        if audit.get("complete"):
            return ("✔", "#4caf50", f"Complete · {on_disk}/{total} episodes")
        if missing > 0:
            return ("⬆", STAGE_GOLD, f"{missing} more available · {on_disk}/{total} episodes")
    # Has metadata but no episode audit (movie, or episodes not fetched).
    # Assume complete: most titles are, and we don't want the badge to depend
    # on whether episode data was ever fetched. Gold ⬆ only shows when we have
    # episode data that actually proves something is missing.
    return ("✔", "#4caf50", "Data on file")


def truncate(text, limit):
    """Trim `text` to `limit` chars, adding an ellipsis when cut."""
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def load_poster(title, target_w, target_h):
    """Return a QPixmap for a title's poster scaled to fit, falling back to the
    default poster. Never returns null unless both files are missing."""
    path = asset_path(settings.poster_path) / f"{title}.jpg"
    pixmap = QPixmap(str(path))
    if pixmap.isNull():
        pixmap = QPixmap(str(asset_path(settings.default_poster)))
    if pixmap.isNull():
        return pixmap
    return pixmap.scaled(
        target_w, target_h,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )


class FetchWorker(QObject):
    """Runs library enrichment off the UI thread. `data_types` is a set drawn
    from {"posters", "ratings", "watchtime", "episodes"} - one worker can do
    any combination, so "Fetch All" is just all four at once."""

    progress = Signal(int, int, str)   # done, total, message
    finished = Signal(dict)            # summary counts
    error = Signal(str)

    def __init__(self, data_types, force=False):
        super().__init__()
        self.data_types = set(data_types)
        self.force = force   # bypass cache / re-download even if present
        self._stop = False

    def stop(self):
        self._stop = True

    def run(self):
        # Top-level guard: any unexpected failure is reported to the UI as an
        # error signal instead of crashing the worker thread silently.
        try:
            self._run()
        except Exception as e:
            self.error.emit(f"Unexpected error during fetch:\n{e}")

    def _run(self):
        try:
            titles = list(library.scan_titles())
        except Exception as e:
            self.error.emit(f"Could not scan library: {e}")
            return

        total = len(titles)
        summary = {"processed": 0, "errors": 0}
        for key in self.data_types:
            summary[key] = 0

        # Track the last real error so we can tell the user WHAT went wrong
        # (e.g. an OMDb 401 / daily-limit) rather than a silent error count.
        last_error = None
        auth_failed = False

        for i, (category, title, title_path) in enumerate(titles, start=1):
            if self._stop:
                break
            self.progress.emit(i, total, f"{category} / {title}")
            try:
                # Hint the media type from the folder category so a show
                # doesn't match a same-named movie (and vice versa).
                info = omdb_client.lookup_title(title, kind=library.category_kind(category), force=self.force)
            except omdb_client.OMDbError as e:
                summary["errors"] += 1
                last_error = str(e)
                if "401" in last_error or "Unauthorized" in last_error or "limit" in last_error.lower():
                    auth_failed = True
                    # No point hammering a dead/limited key for every title.
                    self.error.emit(
                        "OMDb rejected the request (daily limit reached or key "
                        "invalid).\n\nThe free tier allows 1000 requests/day and "
                        "resets at midnight UTC. Try again after the reset."
                    )
                    return
                continue
            except Exception as e:
                summary["errors"] += 1
                last_error = str(e)
                continue

            if "posters" in self.data_types:
                try:
                    if library.download_poster(title, info, force=self.force):
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

        if last_error:
            summary["last_error"] = last_error
        self.finished.emit(summary)


class SplashOverlay(QWidget):
    """A gray loading overlay drawn on top of the main window while the media
    library is scanned. Being a child of the main window (not a separate
    top-level window) means the app has ONE taskbar identity, so the app icon
    is used everywhere - which a separate Tk/Qt splash window broke."""

    def __init__(self, parent, total):
        super().__init__(parent)
        # Warm dim "house" backdrop covering the whole parent.
        self.setObjectName("splash")
        self.setStyleSheet(f"QWidget#splash {{ background: {HOUSE_DARKER}; }}")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setAutoFillBackground(True)

        v = QVBoxLayout(self)
        v.setAlignment(Qt.AlignmentFlag.AlignCenter)
        v.setSpacing(12)

        heading = QLabel(settings.window_title)
        heading.setAlignment(Qt.AlignmentFlag.AlignCenter)
        heading.setStyleSheet(f"color: {STAGE_GOLD}; font-size: 24px; font-weight: bold;")
        v.addWidget(heading)

        self.progress = QProgressBar()
        self.progress.setFixedWidth(400)
        self.progress.setRange(0, max(1, total))
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        self.progress.setStyleSheet(
            f"QProgressBar {{ background: {HOUSE_DARK}; border: 1px solid {CURTAIN_RED};"
            f" border-radius: 4px; height: 14px; }}"
            f" QProgressBar::chunk {{ background: {CURTAIN_RED}; border-radius: 3px; }}"
        )
        v.addWidget(self.progress, alignment=Qt.AlignmentFlag.AlignCenter)

        self.category_label = QLabel("")
        self.category_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.category_label.setStyleSheet(f"color: {PLAYBILL_CREAM}; font-size: 14px; font-weight: bold;")
        v.addWidget(self.category_label)

        self.title_label = QLabel("")
        self.title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.title_label.setStyleSheet(f"color: {PLAYBILL_DIM}; font-size: 11px;")
        v.addWidget(self.title_label)

        self._count = 0
        self.resize(parent.size())
        self.show()
        self.raise_()

    def update(self, category, title):
        self.category_label.setText(category)
        self.title_label.setText(title)
        self._count += 1
        self.progress.setValue(self._count)
        # Keep the overlay covering the window and repaint during the loop.
        if self.parent():
            self.resize(self.parent().size())
        QApplication.processEvents()

    def close(self):
        self.hide()
        self.deleteLater()


class DetailOverlay(QWidget):
    """A large, centered detail panel that zooms in from a card's position to
    show all data plus a Play button. Clicking the dimmed backdrop or Close
    zooms it back and removes it."""

    def __init__(self, parent, start_rect, data, on_play, on_refresh=None):
        super().__init__(parent)
        self._on_play = on_play
        self._on_refresh = on_refresh
        self.setGeometry(parent.rect())            # cover the whole window

        # Dim backdrop; clicking it closes. Scope to this widget so the style
        # does not cascade into the panel and its labels.
        self.setObjectName("detailBackdrop")
        self.setStyleSheet("QWidget#detailBackdrop { background: rgba(0, 0, 0, 160); }")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)

        # The panel that actually grows from the card to center. The selector
        # is scoped to QFrame so the border doesn't cascade to child labels.
        self.panel = QFrame(self)
        self.panel.setObjectName("detailPanel")
        self.panel.setStyleSheet(
            f"QFrame#detailPanel {{ background: {HOUSE_DARK};"
            f" border: 3px solid {data['accent']}; border-radius: 12px; }}"
        )
        self._build_panel_contents(data)

        # Target: centered EXPANDED_WIDTH x EXPANDED_HEIGHT.
        cx = (parent.width() - EXPANDED_WIDTH) // 2
        cy = (parent.height() - EXPANDED_HEIGHT) // 2
        self._end_rect = QRect(cx, max(20, cy), EXPANDED_WIDTH, EXPANDED_HEIGHT)
        self._start_rect = start_rect

        self.show()
        self.raise_()
        self._animate(start_rect, self._end_rect)

    def _build_panel_contents(self, data):
        lay = QVBoxLayout(self.panel)
        lay.setContentsMargins(20, 20, 20, 20)
        lay.setSpacing(12)

        # Header row: title (truncated) + Close button.
        header = QHBoxLayout()
        title = QLabel(truncate(data["title"], 60))
        title.setStyleSheet(
            f"color: {STAGE_GOLD}; font-size: 24px; font-weight: bold;"
            f" border-bottom: 4px solid {data['accent']};"
        )
        header.addWidget(title)
        header.addStretch()
        close_btn = QPushButton("✕")
        close_btn.setFixedSize(34, 34)
        close_btn.setStyleSheet(f"color: {PLAYBILL_DIM}; font-size: 16px; border: none;")
        close_btn.clicked.connect(self.close_zoom)
        header.addWidget(close_btn)
        lay.addLayout(header)

        # Body mirrors the compact card, scaled up: poster on the left
        # (vertically centered), a right column with the metadata, then the
        # description below it, then Play at the bottom.
        body = QHBoxLayout()
        body.setSpacing(24)

        poster = QLabel()
        poster.setFixedSize(240, 360)
        poster.setStyleSheet("background: #000; border-radius: 6px;")
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        pm = load_poster(data["poster_title"], 240, 360)
        if not pm.isNull():
            poster.setPixmap(pm)
        body.addWidget(poster, alignment=Qt.AlignmentFlag.AlignVCenter)

        info = data["info"]
        right = QVBoxLayout()
        right.setSpacing(8)
        right.setAlignment(Qt.AlignmentFlag.AlignTop)

        def stat(text, color=PLAYBILL_CREAM, size=14, bold=False):
            lbl = QLabel(text)
            weight = "bold" if bold else "normal"
            lbl.setStyleSheet(f"color: {color}; font-size: {size}px; font-weight: {weight};")
            lbl.setWordWrap(True)
            right.addWidget(lbl)

        rating = library.get_rating(info)
        stat(f"⭐ {rating}" if rating else "⭐ —", STAGE_GOLD, 18, True)
        stat(data["type_detail"] or "—")
        if info.get("Year"):
            stat(f"Year: {info['Year']}")
        if info.get("Rated") and info["Rated"] != "N/A":
            stat(f"Rated: {info['Rated']}")
        if data["watch"]:
            stat(f"⏱ {data['watch']}", STAGE_GOLD_SOFT)
        if info.get("Genre") and info["Genre"] != "N/A":
            stat(truncate(info["Genre"], 60), PLAYBILL_DIM, 12)
        if info.get("Actors") and info["Actors"] != "N/A":
            stat("Cast: " + truncate(info["Actors"], 70), PLAYBILL_DIM, 12)

        # Description directly below the metadata (same as the card).
        plot = info.get("Plot")
        desc = QLabel(truncate(plot, 400) if plot and plot != "N/A" else "No description available.")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {PLAYBILL_CREAM}; font-size: 13px; padding-top: 6px;")
        right.addWidget(desc)

        right.addStretch()

        # Big Play button, with a small refresh button tacked on the end to
        # re-fetch just this title's data into the cache.
        action_row = QHBoxLayout()
        action_row.setSpacing(8)
        play = QPushButton("▶  Play")
        play.setCursor(Qt.CursorShape.PointingHandCursor)
        play.setStyleSheet(
            f"QPushButton {{ background: {CURTAIN_RED}; color: {STAGE_GOLD}; font-size: 16px;"
            f" font-weight: bold; padding: 10px; border-radius: 8px; }}"
            f" QPushButton:hover {{ background: {CURTAIN_RED_LIGHT}; }}"
        )
        play.clicked.connect(self._play)
        action_row.addWidget(play)

        self.refresh_btn = QPushButton("⟳")
        self.refresh_btn.setToolTip("Re-fetch this title's data")
        self.refresh_btn.setFixedWidth(48)
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(
            f"QPushButton {{ background: {HOUSE_DARKER}; color: {STAGE_GOLD};"
            f" font-size: 18px; padding: 10px; border: 1px solid {CURTAIN_RED};"
            f" border-radius: 8px; }}"
            f" QPushButton:hover {{ background: {CURTAIN_RED}; }}"
        )
        self.refresh_btn.clicked.connect(self._refresh)
        action_row.addWidget(self.refresh_btn)
        right.addLayout(action_row)

        body.addLayout(right)
        lay.addLayout(body)

    def _animate(self, start, end):
        self.panel.setGeometry(start)
        self._anim = QPropertyAnimation(self.panel, b"geometry")
        self._anim.setDuration(220)
        self._anim.setStartValue(start)
        self._anim.setEndValue(end)
        self._anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._anim.start()

    def _play(self):
        if self._on_play:
            self._on_play()
        self.close_zoom()

    def _refresh(self):
        # Re-fetch this one title's data; the callback reports success/failure.
        if not self._on_refresh:
            return
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("…")
        QApplication.processEvents()
        ok = False
        try:
            ok = self._on_refresh()
        finally:
            self.refresh_btn.setText("✓" if ok else "⟳")
            self.refresh_btn.setEnabled(True)

    def close_zoom(self):
        # Zoom back toward the origin card, then remove.
        self._anim = QPropertyAnimation(self.panel, b"geometry")
        self._anim.setDuration(180)
        self._anim.setStartValue(self.panel.geometry())
        self._anim.setEndValue(self._start_rect)
        self._anim.setEasingCurve(QEasingCurve.Type.InCubic)
        self._anim.finished.connect(self._finish_close)
        self._anim.start()

    def _finish_close(self):
        self.hide()
        self.deleteLater()

    def mousePressEvent(self, event):
        # Click outside the panel closes it.
        if not self.panel.geometry().contains(event.pos()):
            self.close_zoom()

    def resizeEvent(self, event):
        self.setGeometry(self.parent().rect())
        super().resizeEvent(event)


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

        # --- Tools section (external links / helpers) ----------------------
        outer.addWidget(self._build_tools_section())

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

    def _build_tools_section(self):
        box = QGroupBox("Tools")
        v = QVBoxLayout(box)
        open_tool = QPushButton("Open Collection Tool in browser")
        open_tool.clicked.connect(self.open_collection_tool)
        v.addWidget(open_tool)
        return box

    def open_collection_tool(self):
        # Open the standalone web tool in the user's default browser.
        index = project_path("_collection_tool/index.html")
        if not index.exists():
            QMessageBox.warning(
                self, "Collection Tool not found",
                f"Could not find:\n{index}",
            )
            return
        webbrowser.open(index.as_uri())

    def _build_fetch_section(self):
        box = QGroupBox("Fetch Online Data (OMDb / IMDb)")
        v = QVBoxLayout(box)

        # Force checkbox: when ticked, re-fetch even if data is already cached
        # (bypass cache, overwrite posters).
        self.force_check = QCheckBox("Force re-fetch (ignore cache)")
        v.addWidget(self.force_check)

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

        # Countdown to the next OMDb free-tier reset (midnight UTC), so you
        # know when more data can be pulled after hitting the daily limit.
        self.reset_label = QLabel("")
        self.reset_label.setStyleSheet("color: #999999; font-size: 11px;")
        v.addWidget(self.reset_label)

        self._reset_timer = QTimer(self)
        self._reset_timer.setInterval(1000)
        self._reset_timer.timeout.connect(self._update_reset_countdown)
        self._reset_timer.start()
        self._update_reset_countdown()

        return box

    def _update_reset_countdown(self):
        # OMDb's free tier (1000 req/day) resets at 00:00 UTC.
        now = datetime.datetime.now(datetime.timezone.utc)
        tomorrow = (now + datetime.timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        remaining = tomorrow - now
        h, rem = divmod(int(remaining.total_seconds()), 3600)
        m, s = divmod(rem, 60)
        self.reset_label.setText(
            f"OMDb daily limit resets in {h:02d}:{m:02d}:{s:02d} (midnight UTC)"
        )

    def start_fetch(self, data_types):
        if self._thread is not None:
            return  # a fetch is already running

        for btn in self._fetch_buttons:
            btn.setEnabled(False)
        self.fetch_progress.setVisible(True)
        self.fetch_progress.setRange(0, 0)  # indeterminate until first tick
        self.fetch_status.setText("Scanning library...")

        self._thread = QThread(self)
        self._worker = FetchWorker(data_types, force=self.force_check.isChecked())
        self._worker.moveToThread(self._thread)
        self._thread.started.connect(self._worker.run)
        self._worker.progress.connect(self._on_fetch_progress)
        self._worker.finished.connect(self._on_fetch_finished)
        self._worker.error.connect(self._on_fetch_error)
        # Both worker signals mean "work is done" -> ask the thread to quit.
        # We must NOT call thread.wait() from inside a worker slot (that
        # deadlocks/crashes); instead let the thread's own finished signal
        # drive cleanup safely.
        self._worker.finished.connect(self._thread.quit)
        self._worker.error.connect(self._thread.quit)
        self._thread.finished.connect(self._cleanup_thread)
        self._thread.start()

    def _on_fetch_progress(self, done, total, message):
        if total:
            self.fetch_progress.setRange(0, total)
            self.fetch_progress.setValue(done)
        self.fetch_status.setText(f"{done}/{total}  -  {message}")

    def _on_fetch_finished(self, summary):
        parts = [f"Processed {summary.get('processed', 0)} titles"]
        for key in ("posters", "ratings", "watchtime", "episodes"):
            if key in summary:
                parts.append(f"{key}: {summary[key]}")
        if summary.get("errors"):
            parts.append(f"errors: {summary['errors']}")
        self.fetch_status.setText("Done. " + ", ".join(parts))
        self.fetch_progress.setVisible(False)
        # Surface the last error so a run that "finished" with failures still
        # explains what went wrong instead of quietly showing a count.
        if summary.get("last_error"):
            QMessageBox.warning(
                self, "Some titles could not be fetched",
                f"{summary['errors']} title(s) failed.\n\n"
                f"Last error:\n{summary['last_error']}",
            )

    def _on_fetch_error(self, message):
        self.fetch_progress.setVisible(False)
        self.fetch_status.setText("")
        QMessageBox.critical(self, "Fetch failed", message)

    def _cleanup_thread(self):
        # Runs on the thread's finished signal (main thread), when it is safe
        # to drop references and re-enable the buttons.
        if self._worker is not None:
            self._worker.deleteLater()
        if self._thread is not None:
            self._thread.deleteLater()
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
        # Here (not inside a worker slot) it IS safe to wait for the thread.
        if self._worker is not None:
            self._worker.stop()
        if self._thread is not None:
            self._thread.quit()
            self._thread.wait()
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
        self._cards = {}         # (title, category) -> card button, for zoom
        self._detail = None      # the currently-open expanded detail overlay

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

            splash = SplashOverlay(self, total_titles)

            for category in directories:
                # Create a header label for the category
                header_label = QLabel(category, self)
                header_label.setAlignment(Qt.AlignmentFlag.AlignLeft)
                header_label.setStyleSheet(
                    f"color: {STAGE_GOLD}; font-size: 20px; font-weight: bold;"
                    f" border-bottom: 2px solid {CURTAIN_RED}; padding-bottom: 3px;"
                )
                self.main_layout.addWidget(header_label)

                # Create a grid layout for this category, left-aligned so the
                # cards hug the left edge instead of stretching/centering.
                category_grid = QGridLayout()
                category_grid.setAlignment(Qt.AlignmentFlag.AlignLeft)
                category_grid.setSpacing(CARD_SPACING)
                self.main_layout.addLayout(category_grid)

                buttons = []

                # Get the list of series titles within the category directory
                cat_path = os.path.join(self.directory_path, category)
                series_titles = [s for s in os.listdir(cat_path)
                                 if self._is_visible_dir(cat_path, s)]

                for title in series_titles:
                    splash.update(category, title)
                    button = self._build_card(title, category)
                    buttons.append(button)
                    self._cards[(title, category)] = button

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

    def _card_info(self, title, category):
        """Gather the display data for a title in one place."""
        info = omdb_client.cached_info(title, kind=library.category_kind(category)) or {}
        media_type = (info.get("Type") or "").lower()
        title_path = os.path.join(self.directory_path, category, title)
        minutes = None
        audit = None
        if info:
            try:
                minutes = library.total_watch_minutes(info, title_path)
            except Exception:
                minutes = None
            try:
                # cached_only so building the grid never hits the network.
                audit = library.episode_audit(info, title_path, cached_only=True)
            except Exception:
                audit = None
        return info, media_type, minutes, audit

    def _type_detail(self, info, media_type):
        if media_type == "series":
            seasons = info.get("totalSeasons")
            return f"TV · {seasons} seasons" if seasons and seasons != "N/A" else "TV"
        if media_type == "movie":
            return f"Movie · {info.get('Runtime', '')}".strip(" ·")
        return info.get("Runtime", "") or ""

    def _build_card(self, title, category):
        """Build one card: poster on the left, stats on the right, a short
        description across the bottom. Fixed size; long text is truncated."""
        info, media_type, minutes, audit = self._card_info(title, category)
        rating = library.get_rating(info)

        # Cards with no fetched data stay near-black (curtain in the dark);
        # cards with data wear the velvet-red trim.
        has_data = bool(info)
        card_bg = HOUSE_DARK if has_data else HOUSE_DARKER
        card_border = CURTAIN_RED if has_data else "#000000"
        title_accent = CURTAIN_RED if has_data else "#000000"

        button = QPushButton(self)
        button.clicked.connect(lambda _=False, t=title, c=category: self.expand_card(t, c))
        button.setFixedSize(CARD_WIDTH, CARD_HEIGHT)
        button.setProperty("category", category)
        button.setProperty("title", title)  # for search filtering
        button.setCursor(Qt.CursorShape.PointingHandCursor)
        button.setStyleSheet(f"""
            QPushButton {{
                background: {card_bg};
                border: 1px solid {card_border};
                border-radius: 10px;
            }}
            QPushButton:hover {{ border: 2px solid {STAGE_GOLD}; }}
        """)

        # Poster on the left (vertically centered), a right column holding the
        # metadata and, below it, the description.
        row = QHBoxLayout(button)
        row.setContentsMargins(8, 8, 8, 8)
        row.setSpacing(10)

        poster = QLabel()
        poster.setFixedSize(POSTER_WIDTH, POSTER_HEIGHT)
        poster.setAlignment(Qt.AlignmentFlag.AlignCenter)
        poster.setStyleSheet("background: #000; border-radius: 4px;")
        pixmap = load_poster(title, POSTER_WIDTH, POSTER_HEIGHT)
        if not pixmap.isNull():
            poster.setPixmap(pixmap)

        # Status badge overlaid on the poster's lower-left corner: always shown
        # (✔ complete · ⬆ upgrades available · ✗ no data).
        icon, color, tip = completeness_badge(has_data, media_type, audit)
        badge_label = QLabel(icon, poster)
        badge_label.setToolTip(tip)
        badge_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        badge_label.setFixedSize(26, 26)
        badge_label.setStyleSheet(
            f"QLabel {{ color: {color}; font-size: 16px; font-weight: bold;"
            " background: rgba(0, 0, 0, 190); border-radius: 13px; }"
        )
        badge_label.move(4, POSTER_HEIGHT - 26 - 4)  # lower-left corner
        badge_label.raise_()

        # Center the poster vertically within the card's full height.
        row.addWidget(poster, alignment=Qt.AlignmentFlag.AlignVCenter)

        stats = QVBoxLayout()
        stats.setSpacing(4)
        stats.setAlignment(Qt.AlignmentFlag.AlignTop)

        title_label = QLabel(truncate(info.get("Title") or title, 34))
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color: {STAGE_GOLD}; font-size: 15px; font-weight: bold;"
            f" border-bottom: 3px solid {title_accent}; padding-bottom: 2px;"
        )
        stats.addWidget(title_label)

        star = QLabel(f"⭐ {rating}" if rating else "⭐ —")
        star.setStyleSheet(f"color: {STAGE_GOLD}; font-weight: bold; font-size: 14px;")
        stats.addWidget(star)

        year = QLabel(info.get("Year") or "—")
        year.setStyleSheet(f"color: {PLAYBILL_DIM}; font-size: 12px;")
        stats.addWidget(year)

        detail = QLabel(truncate(self._type_detail(info, media_type), 24) or "—")
        detail.setStyleSheet(f"color: {PLAYBILL_CREAM}; font-size: 12px;")
        stats.addWidget(detail)

        if minutes:
            watch = QLabel(f"⏱ {library.format_duration(minutes)}")
            watch.setStyleSheet(f"color: {STAGE_GOLD_SOFT}; font-size: 12px;")
            stats.addWidget(watch)

        genre = QLabel(truncate(info.get("Genre") or "", 26) or "—")
        genre.setStyleSheet(f"color: {PLAYBILL_DIM}; font-size: 11px;")
        stats.addWidget(genre)

        # Description sits below the metadata, so the poster stays centered.
        plot = info.get("Plot")
        desc = QLabel(truncate(plot, 130) if plot and plot != "N/A" else "")
        desc.setWordWrap(True)
        desc.setStyleSheet(f"color: {PLAYBILL_DIM}; font-size: 10px;")
        stats.addWidget(desc)

        stats.addStretch()
        row.addLayout(stats)

        return button

    def create_button_click_handler(self, title, category):
        def button_click_handler():
            self.open_video(title, category)
        return button_click_handler

    def expand_card(self, title, category):
        """Zoom the clicked card into a large centered detail panel."""
        if self._detail is not None:
            return  # one open at a time

        info, media_type, minutes, audit = self._card_info(title, category)
        card = self._cards.get((title, category))
        # Start rect = the card's geometry mapped into this window's coords.
        if card is not None:
            top_left = card.mapTo(self, card.rect().topLeft())
            start_rect = QRect(top_left, card.size())
        else:
            start_rect = QRect(self.width() // 2, self.height() // 2, 10, 10)

        data = {
            "title": info.get("Title") or title,
            "poster_title": title,
            "accent": CURTAIN_RED,
            "info": info,
            "type_detail": self._type_detail(info, media_type),
            "watch": library.format_duration(minutes) if minutes else None,
        }

        self._detail = DetailOverlay(
            self, start_rect, data,
            on_play=lambda: self.open_video(title, category),
            on_refresh=lambda: self._refresh_title(title, category),
        )
        # Clear our handle when the overlay is destroyed.
        self._detail.destroyed.connect(self._on_detail_closed)

    def _on_detail_closed(self):
        self._detail = None

    def _refresh_title(self, title, category):
        """Force-refetch a single title's data into the cache and rebuild its
        card in place. Returns True on success. Runs on the UI thread - it's
        one title, so the brief pause is acceptable."""
        try:
            omdb_client.lookup_title(
                title, kind=library.category_kind(category), force=True,
            )
        except Exception:
            return False

        # Rebuild the card so the new data (rating, completeness, etc.) shows.
        old = self._cards.get((title, category))
        if old is not None:
            new = self._build_card(title, category)
            self._cards[(title, category)] = new
            for i, (header, grid, buttons) in enumerate(self.categories):
                if old in buttons:
                    buttons[buttons.index(old)] = new
                    break
            old.setParent(None)
            old.deleteLater()
            self.adjust_grid_layout()
        return True

    def _matches_search(self, title):
        # Empty query matches everything; otherwise case-insensitive substring.
        if not self.search_query:
            return True
        return self.search_query in title.lower()

    def adjust_grid_layout(self):
        available_width = self.scroll_area.viewport().width()
        num_columns = max(1, (available_width + CARD_SPACING) // (CARD_WIDTH + CARD_SPACING))

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

    # The AppUserModelID MUST be set BEFORE the QApplication / any window is
    # created, or Windows keeps grouping us under python(w).exe and shows its
    # (broken) icon on the taskbar.
    if sys.platform == "win32":
        try:
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "mediamimic.app"
            )
        except Exception as e:
            print(f"Could not set AppUserModelID: {e}")

    app = QApplication(sys.argv)

    # Prefer a .ico on Windows (most reliable for the taskbar), fall back to
    # the configured PNG.
    ico = asset_path("assets/icon.ico")
    icon_path = ico if (sys.platform == "win32" and ico.exists()) else asset_path(settings.app_icon)
    app_icon = QIcon(str(icon_path)) if icon_path.exists() else None
    if app_icon is not None:
        app.setWindowIcon(app_icon)
    else:
        print(f"Icon not found at: {icon_path}")

    window = MediaMimicApp()
    # Also set the icon on the window itself so the taskbar entry for this
    # specific window uses it (not just the app-level default).
    if app_icon is not None:
        window.setWindowIcon(app_icon)
    # Show the (single, correctly-iconed) window first, then scan the library
    # behind an in-window overlay. No second top-level window is ever created.
    window.showMaximized()
    app.processEvents()
    window.create_buttons()

    sys.exit(app.exec())