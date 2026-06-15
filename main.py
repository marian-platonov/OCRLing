import colorsys
import math
import os
import sys
import warnings
from datetime import datetime
# ── PyInstaller --noconsole guard ────────────────────────────────────────────
# In a windowed build sys.stdout and sys.stderr are None.  Any library that
# writes to them during import (e.g. loguru) would raise
# AttributeError.  Replace them with a null sink immediately; setup_logging()
# will later upgrade these sinks to loguru-backed streams.
if getattr(sys, "frozen", False):
    if sys.stdout is None:
        sys.stdout = open(os.devnull, "w")
    if sys.stderr is None:
        sys.stderr = open(os.devnull, "w")


os.chdir(os.path.dirname(os.path.abspath(__file__)))

import subprocess
import time
import threading
import tkinter as tk
from tkinter import messagebox, filedialog
from tkinter.filedialog import asksaveasfile
import customtkinter
from pathlib import Path

import pyperclip
import pystray
from PIL import Image, ImageTk, ImageGrab, ImageEnhance
from loguru import logger

import configparser
import webbrowser
from datetime import date
from langdetect import detect
from langcodes import *
# pip install language_data
import pytesseract as pt
import googletrans
import json
import base64
import win32clipboard

import io
from mistralai import Mistral

#pip install "mistralai<2"
# https://docs.mistral.ai/capabilities/document/#ocr-with-image
from googletrans import Translator
import asyncio
import pyautogui

sys.path.insert(0, "..")
from CTkScrollableDropdown import *
from scripts.Tooltip import Tooltip, CTkInput, CreateToolTip


# ── Loguru-backed stream ─────────────────────────────────────────────────────
class _LoguruStream:
    """Forwards write() calls to the loguru logger, one log entry per line.

    Used to replace sys.stdout / sys.stderr in windowed PyInstaller builds so
    that all third-party library output is captured in the rotating log file
    instead of being lost or crashing the process.
    """

    def __init__(self, level: str = "DEBUG"):
        self._level = level
        self._buf = ""

    def write(self, msg: str):
        if not msg:
            return
        self._buf += msg
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            if line.strip():
                logger.opt(depth=1).log(self._level, line)

    def flush(self):
        if self._buf.strip():
            logger.opt(depth=1).log(self._level, self._buf.rstrip())
            self._buf = ""

    def isatty(self):
        return False

    def fileno(self):
        raise io.UnsupportedOperation("no fileno")


warnings.filterwarnings("ignore", message=".*pin_memory.*", category=UserWarning)


class CreateToolTip(object):
    """
    create a tooltip for a given widget
    """

    def __init__(self, widget, text='widget info'):
        self.waittime = 500  # miliseconds
        self.wraplength = 580  # pixels
        self.widget = widget
        self.text = text
        self.widget.bind("<Enter>", self.enter)
        self.widget.bind("<Leave>", self.leave)
        self.widget.bind("<ButtonPress>", self.leave)
        self.id = None
        self.tw = None

    def enter(self, event=None):
        self.schedule()

    def leave(self, event=None):
        self.unschedule()
        self.hidetip()

    def schedule(self):
        self.unschedule()
        self.id = self.widget.after(self.waittime, self.showtip)

    def unschedule(self):
        id = self.id
        self.id = None
        if id:
            self.widget.after_cancel(id)

    def showtip(self, event=None):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")
        x += self.widget.winfo_rootx() + 25
        y += self.widget.winfo_rooty() + 20
        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                         background="#ffffff", relief='solid', borderwidth=1,
                         wraplength=self.wraplength)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()


class OCRLingApp:
    def __init__(self):
        # Initialize variables
        self.win = None
        self.settings_page = None
        self.ocr_window = None
        self.root = None
        self.icon = None
        self.application_version = 'v1.0.1'
        self.icon_app_title = "OCRLing"
        self.captured_image = None
        self.image_zoom_state = False  # False = fit to screen, True = original size
        self.is_dragging = False
        self.drag_start_x = 0
        self.drag_start_y = 0
        self.image_offset_x = 0
        self.image_offset_y = 0
        self.canvas_for_image = None
        self.original_canvas_size = (800, 400)  # Store original canvas size
        self._is_exiting = False
        self._exit_lock = threading.Lock()

        # Setup logging
        self.setup_logging()

        # Ensure default images exist
        self.ensure_default_images()

        # Color picker specific variables
        self.desktop_color_picker = None
        self.color_picker_overlay = None
        self.is_picking_color = False
        self.current_color = (0, 0, 0)
        self.updating_from_wheel = False
        self.updating_from_fields = False
        self.image_dimension = 200
        self.target_dimension = 20
        self.target_x = self.image_dimension // 2
        self.target_y = self.image_dimension // 2
        self.color_wheel_image = None
        self.target_image = None
        self.color_canvas = None
        self.current_alpha = 255  # Default alpha value (fully opaque)

        # Setup CustomTkinter theme
        customtkinter.set_appearance_mode("Dark")
        customtkinter.set_default_color_theme("dark-blue")

        # Grab Language List From GoogleTrans
        self.languages = googletrans.LANGUAGES

        # Convert to string
        self.mydict_in_str = json.dumps(self.languages)

        # Safely load it into a dictionary
        self.languages_dict = json.loads(self.mydict_in_str)

        # Title-case the values
        self.languages_dict_title = {key: value.title() for key, value in self.languages_dict.items()}

        # Convert to list
        self.language_list = list(self.languages.values())

        self.common_languages = self.get_common_languages()  # Cache this

        # Convert to list and capitalize
        self.language_list_capitalize = [name.capitalize() for name in self.language_list]

        # Create hidden root for tkinter operations
        self.root = customtkinter.CTk()
        self.root.withdraw()  # Hide immediately
        self.root.iconbitmap("./images/app_logo.ico")

        # Setup system tray
        self.setup_system_tray()

        # Initialize instance variables
        self.initial_tesseract_exe_path = ""
        self.OCR_engines = ["Tesseract OCR", "Mistral OCR"]
        self.default_ocr_used = self.OCR_engines[0]
        self.default_ocr_used_value = self.OCR_engines[0]
        self.initial_mistral_ocr_key = ""

        # Initialize tkinter variables
        self.tesseract_exe_text = tk.StringVar()
        self.combobox_var = customtkinter.StringVar()
        self.mistral_api_key_text = tk.StringVar()

        # Initialize global variables as instance variables
        self.tesseract_exe_path = ""
        self.mistral_ocr_key = ""

        # Initialize configuration
        self.config = configparser.ConfigParser()
        self.setup_settings()

        # UI element references
        self.default_ocr_combobox = None
        self.mistral_api_key_entry = None
        self.mistral_api_key_label = None
        self.mistral_get_api_key_button = None
        self.test_mistral_connection_button = None
        self.tesseract_exe_file = None
        self.default_tesseract_exe_label = None
        self.tesseract_browse_button = None
        self.tesseract_get_installer_button = None
        self.ocr_engine_frame = None

        # Images
        self.refresh_image = None
        self.redo_image = None
        self.api_image = None
        self.download_file_image = None
        self.add_file_image = None
        self.check_image = None

        self.restore_image = customtkinter.CTkImage(
            light_image=Image.open("./images/white_restore.png"),
            dark_image=Image.open("./images/white_restore.png"),
            size=(20, 20))

        self.export_image = customtkinter.CTkImage(
            light_image=Image.open("./images/export.png"),
            dark_image=Image.open("./images/export.png"),
            size=(20, 20))

        self.translate_image = customtkinter.CTkImage(
            light_image=Image.open("./images/translate.png"),
            dark_image=Image.open("./images/translate.png"),
            size=(20, 20))

        self.clear_image = customtkinter.CTkImage(
            light_image=Image.open("./images/erase.png"),
            dark_image=Image.open("./images/erase.png"),
            size=(20, 20))

        self.ocr_image = customtkinter.CTkImage(
            light_image=Image.open("./images/ocr_image.png"),
            dark_image=Image.open("./images/ocr_image.png"),
            size=(20, 20))

        self.check_image = customtkinter.CTkImage(
            light_image=Image.open("./images/check.png"),
            dark_image=Image.open("./images/check.png"),
            size=(20, 20))

    # Optimize language list creation
    def get_language_list_capitalize(self):
        """Cache this expensive operation"""
        if not hasattr(self, '_cached_language_list'):
            self._cached_language_list = [lang.title() for lang in self.language_list]
        return self._cached_language_list

    def settings_config_write_file(self):
        """Write configuration to settings file"""
        try:
            with open('./settings/settings.ini', 'w') as configfile:
                self.config.write(configfile)
        except FileNotFoundError as e:
            error_text = f"{type(e).__name__} -> {str(e)}"
            messagebox.showerror("Error", error_text)
        except Exception as e:
            error_text = f"{type(e).__name__} -> {str(e)}"
            messagebox.showerror("Error", error_text)

    def setup_settings(self):
        """Initialize settings directory and configuration file"""
        # Create settings folder in root
        settings_path = "./settings"
        if not os.path.exists(settings_path):
            try:
                os.makedirs(settings_path, exist_ok=True)
            except OSError as e:
                error_text = f"{type(e).__name__} -> {str(e)}"
                messagebox.showerror("Error", error_text)
                return

        settings_config_path = "./settings/settings.ini"

        # Create ./settings/settings.ini if it does not exist
        if not os.path.isfile(settings_config_path):
            self.config['paths'] = {'tesseract_exe_path': self.initial_tesseract_exe_path}
            self.config['defaultOCR'] = {'used_ocr': self.default_ocr_used}
            self.config['apikey'] = {'mistral_ai_api_key': self.initial_mistral_ocr_key}
            self.settings_config_write_file()

        # Read existing settings
        self.load_settings()

    def load_settings(self):
        """Load settings from the configuration file"""
        try:
            self.config.read('./settings/settings.ini')

            self.tesseract_exe_path = self.config.get('paths', 'tesseract_exe_path')
            self.tesseract_exe_text.set(str(self.tesseract_exe_path))

            self.default_ocr_used_value = self.config.get('defaultOCR', 'used_ocr')
            self.combobox_var.set(self.default_ocr_used_value)

            self.mistral_ocr_key = self.config.get('apikey', 'mistral_ai_api_key')
            self.mistral_api_key_text.set(self.mistral_ocr_key)

        except configparser.NoSectionError:
            # Handle missing sections by recreating them
            self.create_missing_sections()
            self.settings_config_write_file()
            self.reset_settings_to_default()

        except Exception as e:
            error_text = f"{type(e).__name__} -> {str(e)}"
            messagebox.showerror("Error", error_text)

    def create_missing_sections(self):
        """Create missing configuration sections"""
        if not self.config.has_section('paths'):
            self.config.add_section('paths')
            self.config.set('paths', 'tesseract_exe_path', self.initial_tesseract_exe_path)

        if not self.config.has_section('defaultOCR'):
            self.config.add_section('defaultOCR')
            self.config.set('defaultOCR', 'used_ocr', self.default_ocr_used)

        if not self.config.has_section('apikey'):
            self.config.add_section('apikey')
            self.config.set('apikey', 'mistral_ai_api_key', self.initial_mistral_ocr_key)

    def reset_settings_to_default(self):
        """Reset all settings to their default values"""
        # Ensure all sections exist
        self.create_missing_sections()

        # Set default values
        self.config.set('paths', 'tesseract_exe_path', self.initial_tesseract_exe_path)
        self.config.set('defaultOCR', 'used_ocr', self.OCR_engines[0])
        self.config.set('apikey', 'mistral_ai_api_key', self.initial_mistral_ocr_key)

        # Save the config file
        self.settings_config_write_file()

        # Update instance variables
        self.tesseract_exe_path = self.initial_tesseract_exe_path
        self.default_ocr_used_value = self.OCR_engines[0]
        self.mistral_ocr_key = self.initial_mistral_ocr_key

        # Update UI elements (assuming they exist when this method is called)
        self.update_ui_elements()

    def update_ui_elements(self):
        """Update UI elements with current settings"""
        # Update tesseract exe file entry
        if hasattr(self, 'tesseract_exe_file'):
            self.tesseract_exe_file.configure(state=tk.NORMAL)
            self.tesseract_exe_file.delete(0, tk.END)
            self.tesseract_exe_file.insert(0, self.initial_tesseract_exe_path)
            self.tesseract_exe_file.configure(state=tk.DISABLED)

        # Update OCR combobox
        if hasattr(self, 'default_ocr_combobox'):
            self.default_ocr_combobox.set(self.OCR_engines[0])

        # Update Mistral API key entry
        if hasattr(self, 'mistral_api_key_entry'):
            self.mistral_api_key_entry.delete(0, tk.END)
            self.mistral_api_key_entry.insert(0, self.initial_mistral_ocr_key)

        self._update_ocr_section_visibility()

    def save_current_settings(self):
        """Save current settings to configuration file"""
        self.create_missing_sections()

        # Get current values from UI or instance variables
        self.config.set('paths', 'tesseract_exe_path', self.tesseract_exe_path)
        self.config.set('defaultOCR', 'used_ocr', self.default_ocr_used_value)
        self.config.set('apikey', 'mistral_ai_api_key', self.mistral_ocr_key)

        self.settings_config_write_file()

    def setup_logging(self):
        """Setup logging configuration"""
        logs_path = "./logs"
        if not os.path.exists(logs_path):
            os.makedirs(logs_path, exist_ok=True)

        logger.add(
            os.path.join(logs_path, "application.log"),
            format="{time} | {process} | {level} | {file} | {module}:{function}:{line} | {message}",
            level="DEBUG",
            colorize=True,
            catch=True,
            backtrace=True,
            serialize=False,
            diagnose=True,
            rotation="daily",
            retention="1 month"
        )

        # In a windowed PyInstaller build the null-stream installed at module
        # level is now replaced by a loguru-backed stream, so every subsequent
        # print() or warning from third-party libraries (PyTorch, …)
        # lands in the rotating log file rather than being silently discarded.
        if getattr(sys, "frozen", False):
            sys.stdout = _LoguruStream("INFO")
            sys.stderr = _LoguruStream("WARNING")

        logger.info("Application started")

    def setup_system_tray(self):
        """Smart system tray setup with platform detection"""
        try:
            icon_image = self.create_default_icon()

            # Create action mapping for cleaner handling
            self.action_map = {
                "select_area": self.area_sel,
                "select_image": self.open_image_file,
                "qr_barcode_reader": self.go_to_qr_barcode_reader,
                "desktop_color_picker": self.go_to_desktop_color_picker,
                "settings": self.go_to_settings,
                "about": self.go_to_about,
                "help": self.go_to_help,
            }

            # Detect platform and adjust accordingly
            platform = sys.platform.lower()

            if platform.startswith('win'):
                menu_items = [
                    ("🔲 Select area", "select_area"),
                    ("🖼️ Select image", "select_image"),
                    ("📷 QR & Barcode Reader", "qr_barcode_reader"),
                    ("🎨 Desktop Color Picker", "desktop_color_picker"),
                    ("⚙️ Settings", "settings"),
                    ("ℹ️ About", "about"),
                    ("❓ Help", "help"),
                    ("❌ Exit", "exit")
                ]
            else:
                menu_items = [
                    ("Select area", "select_area"),
                    ("Select image", "select_image"),
                    ("QR & Barcode Reader", "qr_barcode_reader"),
                    ("Desktop Color picker", "desktop_color_picker"),
                    ("Settings", "settings"),
                    ("About", "about"),
                    ("Help", "help"),
                    ("Exit", "exit")
                ]

            # Create menu items - SIMPLIFIED VERSION
            menu_items_list = []

            # Create regular menu items (except exit)
            for item_text, item_action in menu_items:
                if item_action == "exit":
                    # Handle exit separately
                    continue
                else:
                    # Create simple menu item with proper lambda capture
                    def make_action(action=item_action):
                        return lambda icon, item: self.tray_action(icon, action)

                    menu_items_list.append(pystray.MenuItem(item_text, make_action(item_action)))

            # Add exit item last
            menu_items_list.append(
                pystray.MenuItem("❌ Exit" if platform.startswith('win') else "Exit", self.exit_application))

            menu = pystray.Menu(*menu_items_list)

            self.icon = pystray.Icon(
                name="OCRLing",
                icon=icon_image,
                title=self.icon_app_title,
                menu=menu
            )

        except Exception as e:
            logger.error(f"Smart system tray setup failed: {e}")
            # Fallback to simple menu
            self.setup_simple_system_tray()

    def setup_simple_system_tray(self):
        """Simplified system tray setup as fallback"""
        try:
            icon_image = self.create_default_icon()

            # Simple menu without submenus
            menu = pystray.Menu(
                pystray.MenuItem("Select area", lambda: self.tray_action(None, "select_area")),
                pystray.MenuItem("Select image", lambda: self.tray_action(None, "select_image")),
                pystray.MenuItem("QR & Barcode Reader", lambda: self.tray_action(None, "qr_barcode_reader")),
                pystray.MenuItem("Desktop Color Picker", lambda: self.tray_action(None, "desktop_color_picker")),
                pystray.MenuItem("Settings", lambda: self.tray_action(None, "settings")),
                pystray.MenuItem("About", lambda: self.tray_action(None, "about")),
                pystray.MenuItem("Help", lambda: self.tray_action(None, "help")),
                pystray.MenuItem("Exit", self.exit_application)
            )

            self.icon = pystray.Icon(
                name="OCRLing",
                icon=icon_image,
                title=self.icon_app_title,
                menu=menu
            )

        except Exception as e:
            logger.error(f"Even simple system tray setup failed: {e}")

    def _create_scrollable_window_frame(self, window):
        """Wrap *window*'s content area in a vertically-scrollable canvas + scrollbar.

        Returns
        -------
        inner_frame : customtkinter.CTkFrame
            Place all content widgets here.
        canvas : tk.Canvas
            The underlying scroll canvas.  Callers that embed a sub-canvas
            with its own MouseWheel handler (e.g. an image-zoom canvas) can
            temporarily pause window scrolling via canvas.unbind_all.
        scroll_fn : callable
            The MouseWheel callback.  Callers can rebind it after a sub-canvas
            consumes the event.
        """
        bg = "#212121"

        # Outer holder fills the whole window
        outer = tk.Frame(window, bg=bg)
        outer.pack(fill="both", expand=True)

        # Vertical scrollbar on the right edge
        vsb = customtkinter.CTkScrollbar(outer, orientation="vertical")
        vsb.pack(side="right", fill="y")

        # Guard vsb.set against TclError: a window being destroyed may still
        # have pending <Configure> events that fire on the destroyed CTkScrollbar.
        def _safe_yscroll(lo, hi):
            try:
                vsb.set(lo, hi)
            except tk.TclError:
                pass

        # The scrollable canvas
        canvas = tk.Canvas(
            outer,
            yscrollcommand=_safe_yscroll,
            bg=bg,
            highlightthickness=0,
            borderwidth=0,
        )
        canvas.pack(side="left", fill="both", expand=True)
        vsb.configure(command=canvas.yview)

        # Inner CTkFrame lives inside the canvas window
        inner = customtkinter.CTkFrame(canvas, fg_color="transparent")
        win_id = canvas.create_window((0, 0), window=inner, anchor="nw")

        # Sync inner-frame dimensions to the canvas on every layout change.
        #
        # Width  – always forced to match the canvas width (horizontal fill).
        #
        # Height – set to max(canvas_height, content_height):
        #   • content shorter than canvas → inner fills the full visible area
        #     so widgets with expand=True (e.g. the help textbox) stretch to
        #     fill the window instead of shrinking to their minimum.
        #   • content taller than canvas  → inner overflows the canvas and the
        #     scrollbar becomes active.
        def _sync_dimensions(event=None):
            try:
                if not canvas.winfo_exists():
                    return
                cw = canvas.winfo_width()
                ch = canvas.winfo_height()
                content_h = inner.winfo_reqheight()
                if cw > 1:
                    canvas.itemconfig(win_id, width=cw)
                if ch > 1:
                    canvas.itemconfig(win_id, height=max(ch, content_h))
                bbox = canvas.bbox("all")
                if bbox:
                    canvas.configure(scrollregion=bbox)
            except tk.TclError:
                pass

        canvas.bind("<Configure>", _sync_dimensions)
        inner.bind("<Configure>", _sync_dimensions)

        # CTkToplevel completes its internal rendering asynchronously, so the
        # first <Configure> can arrive before the canvas has real dimensions.
        # Poll every 20 ms until both width and height are known.
        def _init_dimensions(attempt=0):
            try:
                if not canvas.winfo_exists():
                    return
                if canvas.winfo_width() > 1 and canvas.winfo_height() > 1:
                    _sync_dimensions()
                elif attempt < 15:                  # give up after ~300 ms
                    canvas.after(20, lambda: _init_dimensions(attempt + 1))
            except tk.TclError:
                pass

        canvas.after(20, _init_dimensions)

        # MouseWheel callback for window-level vertical scrolling.
        # Guard: only scroll when content actually overflows the visible area.
        def _scroll(event):
            try:
                bbox = canvas.bbox("all")
                if bbox and canvas.winfo_height() < bbox[3]:
                    canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except tk.TclError:
                pass

        # Activate scrolling while cursor is inside the window; deactivate on leave
        window.bind("<Enter>", lambda e: canvas.bind_all("<MouseWheel>", _scroll))
        window.bind("<Leave>", lambda e: canvas.unbind_all("<MouseWheel>"))

        return inner, canvas, _scroll

    def ensure_default_images(self):
        """Ensure default image files exist or create placeholders"""
        image_files = [
            "./images/copy.png",
            "./images/erase.png",
            "./images/save.png",
            "./images/refresh.png",
            "./images/add_file.png",
            "./images/help.png"
        ]

        # Create images directory if it doesn't exist
        os.makedirs("./images", exist_ok=True)

        for image_file in image_files:
            if not os.path.exists(image_file):
                try:
                    # Create a simple colored square as placeholder
                    size = (20, 20)
                    color = (100, 100, 200)  # Blue color

                    if "copy" in image_file:
                        color = (0, 150, 0)  # Green
                    elif "erase" in image_file:
                        color = (200, 0, 0)  # Red
                    elif "save" in image_file:
                        color = (0, 100, 200)  # Blue
                    elif "refresh" in image_file:
                        color = (200, 100, 0)  # Orange
                    elif "add_file" in image_file:
                        color = (100, 0, 200)  # Purple
                    elif "help" in image_file:
                        color = (200, 200, 0)  # Yellow

                    img = Image.new('RGB', size, color)
                    img.save(image_file)
                    logger.info(f"Created placeholder image: {image_file}")
                except Exception as e:
                    logger.warning(f"Failed to create placeholder {image_file}: {e}")

    def create_default_icon(self):
        """Create a default icon if icon file doesn't exist"""
        try:
            if os.path.exists("./images/app_logo.ico"):
                return Image.open("./images/app_logo.ico")
            else:
                return Image.new('RGB', (64, 64), color='blue')
        except Exception as e:
            # logger.warning(f"Could not load icon, using default: {e}")
            return Image.new('RGB', (64, 64), color='blue')

    def tray_action(self, icon, action):
        """Handle tray menu actions using action identifiers"""
        logger.info(f"Tray action selected: {action}")

        try:
            if action in self.action_map:
                self.action_map[action]()
            else:
                logger.warning(f"Unknown action: {action}")
        except Exception as e:
            error_text = f"{type(e).__name__} -> {str(e)}"
            logger.error(error_text)
            self.root.after(0, lambda: messagebox.showerror("Error", error_text))

    def area_sel(self):
        x1 = y1 = x2 = y2 = 0
        roi_image = None

        @logger.catch(level="DEBUG")
        def on_mouse_down(event):
            nonlocal x1, y1
            x1, y1 = event.x, event.y
            canvas.create_rectangle(x1, y1, x1, y1, dash=(2, 2), fill='', outline='cyan', tag='roi')
            # Add a 'tcross' cursor
            canvas.configure(cursor="tcross")

        @logger.catch(level="DEBUG")
        def on_mouse_move(event):
            nonlocal roi_image
            x2, y2 = event.x, event.y
            # calculate the width and height for the cropping box
            width = abs(x2 - x1)
            height = abs(y2 - y1)

            # remove old overlay image, text
            canvas.delete('roi-image')
            canvas.delete('dimensions')

            # get the image of the selected region
            roi_image = image.crop((min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            canvas.image = ImageTk.PhotoImage(roi_image)
            canvas.create_image(min(x1, x2), min(y1, y2), image=canvas.image, tag='roi-image', anchor='nw')
            canvas.coords('roi', (min(x1, x2), min(y1, y2), max(x1, x2), max(y1, y2)))
            mid_x = x1 + (x2 - x1) / 2
            mid_y = y1 + (y2 - y1) / 2
            canvas.create_text(mid_x, mid_y, font=('Helvetica', 14), text=f'{width} x {height}', fill='green',
                               tags='dimensions')

            # make sure the select rectangle is on top of the overlay image
            canvas.lift('roi')

        # hide the root window
        self.root.withdraw()
        # grab the full-screen as a select region background
        try:
            image = ImageGrab.grab()
        except Exception as e:
            logger.error(f"Failed to capture screen: {e}")
            return

        BRIGHTNESS_FACTOR = 0.6
        # darken the capture image
        bgimage = ImageEnhance.Brightness(image).enhance(BRIGHTNESS_FACTOR)

        # create a full-screen window to perform the select region action
        # global win
        win = customtkinter.CTkToplevel(master=self.root)
        win.title(f"OCRLing {self.application_version} - Select Area")
        # make a window full-screen
        win.state('zoomed')
        win.attributes('-fullscreen', True)
        MIN_WIDTH, MIN_HEIGHT = 1280, 960
        win.minsize(MIN_WIDTH, MIN_HEIGHT)
        # win.overrideredirect(1)
        canvas = tk.Canvas(win, highlightthickness=0)
        canvas.pack(fill='both', expand=1)
        self.tkimage = ImageTk.PhotoImage(bgimage)
        canvas.create_image(0, 0, image=self.tkimage, anchor='nw', tag='images')
        # bind the mouse events for selecting region
        win.bind('<ButtonPress-1>', on_mouse_down)
        win.bind('<B1-Motion>', on_mouse_move)
        win.bind('<ButtonRelease-1>', lambda e: win.destroy())
        # use an Esc key to abort the capture
        win.bind('<Escape>', lambda e: win.destroy())
        # make the capture window modal
        win.focus_force()
        win.grab_set()
        win.wait_window(win)
        # root.deiconify()  # restore root window
        # show the capture image
        if roi_image:
            self.captured_image = roi_image
            self.store_temp_image(roi_image)
            self.open_ocr_window()
            logger.info(f"Area captured successfully with dimensions: {roi_image.size}")
        else:
            logger.warning("No area was selected")

    def open_image_file(self):
        """Open image file dialog"""
        try:
            file_path = filedialog.askopenfilename(
                title=f"OCRLing {self.application_version} - Select Image",
                filetypes=[
                    ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tiff"),
                    ("All files", "*.*")
                ]
            )
            if file_path:
                self.captured_image = Image.open(file_path)
                self.store_temp_image(self.captured_image)
                self.open_ocr_window()
                logger.info(f"Image loaded: {file_path}")
        except Exception as e:
            error_text = f"Open image error: {type(e).__name__} -> {str(e)}"
            logger.error(error_text)
            self.root.after(0, lambda: messagebox.showerror("Error", error_text))

    def store_temp_image(self, image):
        """Store the captured image temporarily"""
        try:
            temp_path = "temp_ocr_image.png"
            image.save(temp_path)

            # Get the full real path (resolves symlinks too)
            full_path = os.path.realpath(temp_path)
            logger.info(f"Temporary image saved: {full_path}")

        except Exception as e:
            logger.error(f"Failed to save temporary image: {e}")

    def open_ocr_window(self):
        """Open the main OCR processing window with scrollable canvas"""
        try:
            # Close the existing OCR window if open
            if self.ocr_window is not None:
                self.ocr_window.destroy()

            # Create OCR window
            self.ocr_window = customtkinter.CTkToplevel(self.root)
            self.ocr_window.title(f"OCRLing {self.application_version} - OCR Results")
            self.ocr_window.geometry("1400x900")
            self.ocr_window.minsize(800, 600)

            # Set icon with error handling
            try:
                if os.path.exists("./images/app_logo.ico"):
                    self.ocr_window.after(201, lambda: self.ocr_window.iconbitmap("./images/app_logo.ico"))
                else:
                    logger.warning("Icon file not found: ./images/app_logo.ico")
            except Exception as icon_error:
                logger.error(f"Icon loading error: {icon_error}")

            # Scrollable main frame so all UI elements remain reachable
            # even when the window is resized small or the image is large.
            main_frame, _, __ = self._create_scrollable_window_frame(self.ocr_window)

            # Image display section
            self.setup_image_display(main_frame)

            # OCR processing section
            self.setup_ocr_interface(main_frame)

            # Handle window close
            self.ocr_window.protocol("WM_DELETE_WINDOW", self.close_ocr_window)

            logger.info("OCR window opened successfully")

        except Exception as e:
            error_text = f"OCR window error: {type(e).__name__} -> {str(e)}"
            logger.error(error_text)
            self.root.after(0, lambda: messagebox.showerror("Error", error_text))

    @logger.catch
    def setup_image_display(self, parent):
        """Setup the image display area"""
        # Image frame
        image_frame = customtkinter.CTkFrame(parent)
        image_frame.pack(fill="x", padx=20, pady=(20, 10))

        # Image title
        image_title = customtkinter.CTkLabel(
            image_frame,
            text="Captured Image (Click to zoom, Hold and drag to explore details)",
            font=customtkinter.CTkFont(size=16, weight="bold")
        )
        image_title.pack(pady=(15, 5))

        # Image display
        if self.captured_image:
            self.display_image_in_frame(image_frame)

    @logger.catch
    def create_image_context_menu(self, parent_widget):
        """Create right-click context menu for image with icons"""
        # Load icon images (if you have them)
        try:
            copy_icon = tk.PhotoImage(file="./images/copy.png")
            save_icon = tk.PhotoImage(file="./images/save.png")

            # Create context menu
            self.image_context_menu = tk.Menu(parent_widget, tearoff=0)
            self.image_context_menu.add_command(
                label="Copy Image to Clipboard",
                image=copy_icon,
                compound="left",  # Icon on the left of text
                command=self.copy_image_to_clipboard
            )
            self.image_context_menu.add_separator()
            self.image_context_menu.add_command(
                label="Save Image As...",
                image=save_icon,
                compound="left",
                command=self.save_image_as
            )

            # Store references to prevent garbage collection
            self.copy_icon = copy_icon
            self.save_icon = save_icon

        except Exception as e:
            # Fallback to emoji icons if image files don't exist
            self.image_context_menu = tk.Menu(parent_widget, tearoff=0)
            self.image_context_menu.add_command(
                label="📋 Copy Image to Clipboard",
                command=self.copy_image_to_clipboard
            )
            self.image_context_menu.add_separator()
            self.image_context_menu.add_command(
                label="💾 Save Image As...",
                command=self.save_image_as
            )

    def show_image_context_menu(self, event):
        """Show context menu on right-click"""
        try:
            self.image_context_menu.tk_popup(event.x_root, event.y_root)
        except Exception as e:
            logger.error(f"Failed to show context menu: {e}")
        finally:
            self.image_context_menu.grab_release()

    def copy_image_to_clipboard(self):
        """Copy the captured image to clipboard"""
        try:
            if not self.captured_image:
                messagebox.showwarning("Warning", "No image to copy!")
                return

            # Convert PIL image to clipboard format
            output = io.BytesIO()
            self.captured_image.save(output, format='BMP')
            data = output.getvalue()[14:]  # Remove BMP header for clipboard
            output.close()

            # Clear clipboard and set new data
            self.ocr_window.clipboard_clear()

            # For Windows - use win32clipboard if available
            try:
                import win32clipboard
                win32clipboard.OpenClipboard()
                win32clipboard.EmptyClipboard()
                win32clipboard.SetClipboardData(win32clipboard.CF_DIB, data)
                win32clipboard.CloseClipboard()
                messagebox.showinfo("Success", "Image copied to clipboard!")
                logger.info("Image copied to clipboard using win32clipboard")
            except ImportError:
                # Fallback method using tkinter (may not work on all systems)
                try:
                    # Save as temporary PNG for clipboard
                    temp_path = "temp_clipboard.png"
                    self.captured_image.save(temp_path, format='PNG')

                    # Try to copy file path (basic fallback)
                    self.ocr_window.clipboard_append(temp_path)
                    messagebox.showinfo("Info",
                                        "Image path copied to clipboard.\nNote: Install 'pywin32' for direct image clipboard support.")
                    logger.info("Image path copied to clipboard (fallback method)")
                except Exception as fallback_error:
                    logger.error(f"Clipboard fallback failed: {fallback_error}")
                    messagebox.showerror("Error",
                                         "Failed to copy image to clipboard.\nTry installing 'pywin32' package.")

        except Exception as e:
            error_msg = f"Failed to copy image: {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)

    def save_image_as(self):
        """Save the captured image with user-selected filename"""
        try:
            if not self.captured_image:
                messagebox.showwarning("Warning", "No image to save!")
                return

            # Define file types
            file_types = [
                ("PNG files", "*.png"),
                ("JPEG files", "*.jpg;*.jpeg"),
                ("BMP files", "*.bmp"),
                ("TIFF files", "*.tiff;*.tif"),
                ("All files", "*.*")
            ]

            # Open save dialog
            filename = filedialog.asksaveasfilename(
                title="Save Image As",
                defaultextension=".png",
                filetypes=file_types,
                parent=self.ocr_window
            )

            if filename:
                # Determine format from extension
                file_extension = filename.lower().split('.')[-1]
                format_mapping = {
                    'png': 'PNG',
                    'jpg': 'JPEG',
                    'jpeg': 'JPEG',
                    'bmp': 'BMP',
                    'tiff': 'TIFF',
                    'tif': 'TIFF'
                }

                save_format = format_mapping.get(file_extension, 'PNG')

                # Save the image
                if save_format == 'JPEG':
                    # Convert RGBA to RGB for JPEG (if needed)
                    if self.captured_image.mode in ('RGBA', 'LA'):
                        rgb_image = Image.new('RGB', self.captured_image.size, (255, 255, 255))
                        rgb_image.paste(self.captured_image, mask=self.captured_image.split()[
                            -1] if self.captured_image.mode == 'RGBA' else None)
                        rgb_image.save(filename, format=save_format, quality=95)
                    else:
                        self.captured_image.save(filename, format=save_format, quality=95)
                else:
                    self.captured_image.save(filename, format=save_format)

                messagebox.showinfo("Success", f"Image saved successfully!\n{filename}")
                logger.info(f"Image saved as: {filename}")

        except Exception as e:
            error_msg = f"Failed to save image: {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)

    def display_image_in_frame(self, parent):
        """Display the captured image in the frame with pan support and context menu"""
        try:
            # Clean up existing widgets
            if hasattr(self, 'image_label') and self.image_label:
                self.image_label.destroy()
            if hasattr(self, 'canvas_for_image') and self.canvas_for_image:
                self.canvas_for_image.destroy()
            if hasattr(self, 'return_button') and self.return_button:
                self.return_button.destroy()

            # Calculate display size for fit-to-screen
            display_image = self.captured_image.copy()
            max_width, max_height = 800, 400

            if not self.image_zoom_state:  # Fit to screen mode
                if display_image.width > max_width or display_image.height > max_height:
                    display_image.thumbnail((max_width, max_height), Image.Resampling.LANCZOS)

                # Convert to PhotoImage
                self.photo = ImageTk.PhotoImage(display_image)

                # Create clickable image label for fit-to-screen mode
                self.image_label = tk.Label(
                    parent,
                    image=self.photo,
                    cursor="hand2",
                    bg=parent._fg_color[1] if hasattr(parent, '_fg_color') else 'gray'
                )
                self.image_label.pack(pady=10)
                self.image_label.bind("<Button-1>", self.toggle_image_zoom)

                # Add right-click context menu
                self.create_image_context_menu(self.image_label)
                self.image_label.bind("<Button-3>", self.show_image_context_menu)  # Right-click

            else:  # Zoomed mode with pan support
                # Add return button when in zoom mode
                self.return_button = customtkinter.CTkButton(
                    parent,
                    text="Return to Fit Screen",
                    command=self.return_to_fit_mode,
                    image=self.restore_image,
                    width=150,
                    height=30
                )
                self.return_button.pack(pady=(5, 10))

                # Use original image size
                self.photo = ImageTk.PhotoImage(display_image)

                # Store original canvas size
                self.original_canvas_size = (max_width, max_height)

                # Create canvas for panning support
                canvas_width = max_width
                canvas_height = max_height

                self.canvas_for_image = tk.Canvas(
                    parent,
                    width=canvas_width,
                    height=canvas_height,
                    cursor="hand2",
                    bg=parent._fg_color[1] if hasattr(parent, '_fg_color') else 'gray',
                    highlightthickness=1,
                    highlightcolor="cyan"
                )
                self.canvas_for_image.pack(pady=10)

                # Center the image initially
                center_x = (canvas_width - display_image.width) // 2
                center_y = (canvas_height - display_image.height) // 2
                self.image_offset_x = center_x
                self.image_offset_y = center_y

                # Create image on canvas
                self.canvas_image_id = self.canvas_for_image.create_image(
                    self.image_offset_x,
                    self.image_offset_y,
                    image=self.photo,
                    anchor="nw"
                )

                # Bind mouse events for panning and context menu
                self.canvas_for_image.bind("<Button-1>", self.on_image_click)
                self.canvas_for_image.bind("<B1-Motion>", self.on_image_drag)
                self.canvas_for_image.bind("<ButtonRelease-1>", self.on_image_release)

                # Add right-click context menu for canvas
                self.create_image_context_menu(self.canvas_for_image)
                self.canvas_for_image.bind("<Button-3>", self.show_image_context_menu)  # Right-click

            # Image info
            info_text = f"Size: {self.captured_image.width} x {self.captured_image.height} pixels"
            if not self.image_zoom_state:
                info_text += f" (Displayed: {display_image.width} x {display_image.height})"
            else:
                info_text += " (Full size - Hold and drag to explore, Right-click for options)"

            if hasattr(self, 'image_info_label') and self.image_info_label:
                self.image_info_label.destroy()

            self.image_info_label = customtkinter.CTkLabel(parent, text=info_text)
            self.image_info_label.pack(pady=(0, 15))

        except Exception as e:
            logger.error(f"Failed to display image: {e}")

    def on_image_click(self, event):
        """Handle mouse click on image (start of potential drag)"""
        self.is_dragging = False
        self.drag_start_x = event.x
        self.drag_start_y = event.y

        # Use cross cursor for Windows compatibility
        try:
            self.canvas_for_image.configure(cursor="fleur")  # 4-way arrow cursor
        except:
            self.canvas_for_image.configure(cursor="hand2")  # Fallback

    def on_image_drag(self, event):
        """Handle mouse drag on image (pan the image to explore details)"""
        if not self.is_dragging:
            self.is_dragging = True

        # Calculate drag distance
        dx = event.x - self.drag_start_x
        dy = event.y - self.drag_start_y

        # Update image position with full freedom to explore
        new_x = self.image_offset_x + dx
        new_y = self.image_offset_y + dy

        # Get canvas and image dimensions
        canvas_width = self.canvas_for_image.winfo_width()
        canvas_height = self.canvas_for_image.winfo_height()
        image_width = self.photo.width()
        image_height = self.photo.height()

        # Allow full exploration - more generous bounds
        # User can drag to see any part of the image
        max_offset_x = canvas_width
        min_offset_x = -image_width
        max_offset_y = canvas_height
        min_offset_y = -image_height

        new_x = max(min_offset_x, min(max_offset_x, new_x))
        new_y = max(min_offset_y, min(max_offset_y, new_y))

        # Update canvas image position
        self.canvas_for_image.coords(self.canvas_image_id, new_x, new_y)

        # Update stored offsets
        self.image_offset_x = new_x
        self.image_offset_y = new_y

        # Update drag start position for smooth dragging
        self.drag_start_x = event.x
        self.drag_start_y = event.y

        # Optional: Show coordinates for debugging
        # print(f"Image position: ({new_x}, {new_y})")

    def on_image_release(self, event):
        """Handle mouse release - just reset cursor"""
        self.canvas_for_image.configure(cursor="hand2")

        if self.is_dragging:
            logger.info("Drag exploration completed - staying in zoom mode")

        self.is_dragging = False

    def return_to_fit_mode(self, event=None):
        """Return to fit-to-screen mode"""
        self.image_zoom_state = False
        self.image_offset_x = 0
        self.image_offset_y = 0

        # Refresh the image display
        if hasattr(self, 'canvas_for_image') and self.canvas_for_image:
            parent = self.canvas_for_image.master
            self.display_image_in_frame(parent)

        logger.info("Returned to fit-to-screen mode")

    def toggle_image_zoom(self, event):
        """Toggle to zoom mode for exploration"""
        if not self.image_zoom_state:
            self.image_zoom_state = True

            # Refresh the image display
            if hasattr(self, 'image_label') and self.image_label:
                parent = self.image_label.master
                self.display_image_in_frame(parent)

            logger.info("Image zoom toggled: Exploration mode enabled")

    def center_image_in_canvas(self):
        """Center the image in the canvas (utility function)"""
        if self.image_zoom_state and hasattr(self, 'canvas_for_image') and self.canvas_for_image:
            canvas_width, canvas_height = self.original_canvas_size
            image_width = self.photo.width()
            image_height = self.photo.height()

            center_x = (canvas_width - image_width) // 2
            center_y = (canvas_height - image_height) // 2

            self.image_offset_x = center_x
            self.image_offset_y = center_y
            self.canvas_for_image.coords(self.canvas_image_id, center_x, center_y)
            logger.info("Image centered in canvas")

    def setup_ocr_interface(self, parent):
        """Setup the OCR processing interface - OPTIMIZED VERSION"""
        # Main OCR frame
        start_time = time.time()
        ocr_frame = customtkinter.CTkFrame(parent, bg_color="#212121", fg_color="#212121")
        ocr_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Main content frame with three columns
        content_frame = customtkinter.CTkFrame(ocr_frame)
        content_frame.pack(fill="both", expand=True, padx=20, pady=(0, 20))

        # Configure grid weights
        content_frame.grid_columnconfigure((0, 2), weight=1)
        content_frame.grid_columnconfigure(1, weight=0)
        content_frame.grid_rowconfigure(0, weight=1)

        # Setup columns with basic functionality
        self.setup_extracted_text_column(content_frame)
        self.setup_control_buttons_column(content_frame)
        self.setup_translated_text_column(content_frame)

        # Add lazy autocomplete
        self.setup_lazy_autocomplete()
        logger.info(f"Interface setup took: {time.time() - start_time:.2f} seconds")

    def setup_lazy_autocomplete(self):
        """Setup autocomplete that loads on first interaction"""

        def add_source_autocomplete_on_click(event=None):
            """Add autocomplete to source language on first click"""
            if not hasattr(self, '_source_autocomplete_added'):
                try:
                    self.source_dropdown = CTkScrollableDropdown(
                        self.source_language,
                        values=self.language_list_capitalize,
                        justify="left",
                        button_color="transparent",
                        command=lambda e: self.source_language.set(e),
                        autocomplete=True,
                        height=200
                    )
                    self.source_language.configure(values=self.language_list_capitalize)
                    self._source_autocomplete_added = True
                    logger.info("✓ Source autocomplete loaded on demand")
                except Exception as e:
                    logger.error(f"Error adding source autocomplete: {e}")

        def add_target_autocomplete_on_click(event=None):
            """Add autocomplete to target language on first click"""
            if not hasattr(self, '_target_autocomplete_added'):
                try:
                    self.target_dropdown = CTkScrollableDropdown(
                        self.target_language,
                        values=self.language_list_capitalize,
                        justify="left",
                        button_color="transparent",
                        command=lambda e: self.target_language.set(e),
                        autocomplete=True,
                        height=200
                    )
                    self.target_language.configure(values=self.language_list_capitalize)
                    self._target_autocomplete_added = True
                    logger.info("✓ Target autocomplete loaded on demand")
                except Exception as e:
                    logger.error(f"Error adding target autocomplete: {e}")

        # Bind events to trigger autocomplete loading
        if hasattr(self, 'source_language'):
            self.source_language.bind("<Button-1>", add_source_autocomplete_on_click, add=True)
            self.source_language.bind("<FocusIn>", add_source_autocomplete_on_click, add=True)

        if hasattr(self, 'target_language'):
            self.target_language.bind("<Button-1>", add_target_autocomplete_on_click, add=True)
            self.target_language.bind("<FocusIn>", add_target_autocomplete_on_click, add=True)

    def setup_frame_structure(self, parent):
        """Create the basic frame structure quickly"""
        # Left frame
        self.left_frame = customtkinter.CTkFrame(parent)
        self.left_frame.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        self.left_frame.grid_rowconfigure(1, weight=1)
        self.left_frame.grid_columnconfigure(0, weight=1)

        # Middle frame
        self.middle_frame = customtkinter.CTkFrame(parent, fg_color="#212121", bg_color="#212121")
        self.middle_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=20)

        # Right frame
        self.right_frame = customtkinter.CTkFrame(parent)
        self.right_frame.grid(row=0, column=2, sticky="nsew", padx=(10, 20), pady=20)

    # HELPER METHODS
    def get_common_languages(self):
        """Return a smaller list of common languages for faster initial loading"""
        common_langs = [
            "English", "Spanish", "French", "German", "Italian",
            "Portuguese", "Chinese", "Japanese", "Korean", "Arabic",
            "Russian", "Hindi", "Dutch", "Swedish", "Norwegian"
        ]
        return common_langs

    def check_lang(self):
        """Optimized language detection with better error handling"""
        try:
            # Check if text box is empty
            if self.extracted_text.compare("end-1c", "==", "1.0"):
                self.detected_lang_label.configure(
                    text="⚠️ Enter text to detect language",
                    text_color="#FF4444"
                )
                return

            # Get text content
            text_content = self.extracted_text.get("1.0", "end-1c").strip()

            # Check if a text is substantial enough for detection
            if len(text_content) < 10:
                self.detected_lang_label.configure(
                    text="⚠️ Need more text (at least 10 characters) for accurate detection",
                    text_color="#FF6B35"
                )
                return

            # Perform language detection
            code = detect(text_content)
            detected_lang = Language.make(language=code).display_name().title()

            # Update source language if detected language is in the list
            current_values = self.source_language.cget("values")
            if detected_lang in current_values:
                self.source_language.set(detected_lang)
            else:
                # Add detected language to combobox if not present
                new_values = list(current_values) + [detected_lang]
                self.source_language.configure(values=new_values)
                self.source_language.set(detected_lang)

            self.detected_lang_label.configure(
                text=f"Detected: {detected_lang}",
                text_color="#4CAF50"
            )

        except Exception as e:
            self.detected_lang_label.configure(
                text="❌ Detection failed",
                text_color="#FF4444"
            )
            print(f"Language detection error: {e}")

    def add_full_language_support(self, combobox):
        """Optional method to add full language list and scrollable dropdown later"""
        try:
            # Update combobox with full language list
            if hasattr(self, 'language_list_capitalize'):
                combobox.configure(values=self.language_list_capitalize)

                # Add scrollable dropdown if CTkScrollableDropdown is available
                CTkScrollableDropdown(
                    combobox,
                    values=self.language_list_capitalize,
                    justify="left",
                    button_color="transparent",
                    command=lambda e: combobox.set(e),
                    autocomplete=False  # Keep disabled for performance
                )
        except Exception as e:
            print(f"Error adding full language support: {e}")

    # Additional optimization - cache language list
    def get_cached_language_list(self):
        """Cache the capitalized language list to avoid recreating it"""
        if not hasattr(self, '_cached_lang_list'):
            self._cached_lang_list = [lang.title() for lang in self.language_list] if hasattr(self,
                                                                                              'language_list') else []
        return self._cached_lang_list

    def load_menu_icons(self):
        """Load PNG icons with fallback to emoji if loading fails"""
        if not hasattr(self, 'menu_icons'):
            self.menu_icons = {}

        icon_configs = {
            'select_all': {'file': 'select_all.png', 'fallback': '📄', 'size': (20, 20)},
            'copy': {'file': 'copy.png', 'fallback': '📋', 'size': (20, 20)},
            'cut': {'file': 'cut.png', 'fallback': '✂️', 'size': (20, 20)},
            'undo': {'file': 'undo.png', 'fallback': '↩️', 'size': (20, 20)},
            'save': {'file': 'save.png', 'fallback': '💾', 'size': (20, 20)},
            'paste': {'file': 'paste.png', 'fallback': '📋', 'size': (20, 20)}
        }

        # Define possible icon directories
        icon_directories = [
            'images/',
            os.path.join(os.path.dirname(__file__), 'icons'),
        ]

        for icon_name, config in icon_configs.items():
            icon_loaded = False

            # Try to load from each directory
            for icon_dir in icon_directories:
                icon_path = os.path.join(icon_dir, config['file'])

                if os.path.exists(icon_path):
                    try:
                        # Load and resize the image
                        image = Image.open(icon_path)
                        image = image.resize(config['size'], Image.Resampling.LANCZOS)

                        # Convert to PhotoImage
                        photo = ImageTk.PhotoImage(image)

                        self.menu_icons[icon_name] = {
                            'image': photo,
                            'label': config['file'].replace('.png', '').replace('_', ' ').title(),
                            'has_icon': True
                        }

                        icon_loaded = True
                        logger.info(f"Loaded icon: {icon_name} from {icon_path}")
                        break

                    except Exception as e:
                        logger.warning(f"Failed to load icon {icon_path}: {e}")
                        continue

            # Use fallback if icon couldn't be loaded
            if not icon_loaded:
                self.menu_icons[icon_name] = {
                    'image': None,
                    'label': f"{config['fallback']} {config['file'].replace('.png', '').replace('_', ' ').title()}",
                    'has_icon': False
                }
                logger.info(f"Using fallback for icon: {icon_name}")

    def get_menu_config(self, icon_name):
        """Get menu configuration (image and label) for an icon"""
        if not hasattr(self, 'menu_icons'):
            self.load_menu_icons()

        if icon_name in self.menu_icons:
            config = self.menu_icons[icon_name]
            if config['has_icon']:
                return {'image': config['image'], 'label': config['label'], 'compound': 'left'}
            else:
                return {'label': config['label']}
        else:
            # Ultimate fallback
            return {'label': icon_name.replace('_', ' ').title()}

    def create_textbox_context_menu(self, textbox_widget):
        """Create right-click context menu for textbox with PNG icons and fallbacks"""
        # Load icons if not already loaded
        if not hasattr(self, 'menu_icons'):
            self.load_menu_icons()

        # Create context menu
        context_menu = tk.Menu(textbox_widget, tearoff=0)

        # Select All
        select_all_config = self.get_menu_config('select_all')
        context_menu.add_command(
            command=lambda: self.textbox_select_all(textbox_widget),
            **select_all_config
        )

        context_menu.add_separator()

        # Copy
        copy_config = self.get_menu_config('copy')
        context_menu.add_command(
            command=lambda: self.textbox_copy(textbox_widget),
            **copy_config
        )

        # Cut
        cut_config = self.get_menu_config('cut')
        context_menu.add_command(
            command=lambda: self.textbox_cut(textbox_widget),
            **cut_config
        )

        # Paste (optional - you might want to add this)
        paste_config = self.get_menu_config('paste')
        context_menu.add_command(
            command=lambda: self.textbox_paste(textbox_widget),
            **paste_config
        )

        context_menu.add_separator()

        # Undo
        undo_config = self.get_menu_config('undo')
        context_menu.add_command(
            command=lambda: self.textbox_undo(textbox_widget),
            **undo_config
        )

        context_menu.add_separator()

        # Save
        save_config = self.get_menu_config('save')
        context_menu.add_command(
            command=lambda: self.save_text_to_file(textbox_widget),
            **save_config
        )

        return context_menu

    def show_textbox_context_menu(self, event, context_menu):
        """Show context menu on right-click with proper state management"""
        try:
            # Update menu state based on text selection and content
            textbox = event.widget

            # Check if there's selected text
            has_selection = False
            try:
                if textbox.selection_get():
                    has_selection = True
            except tk.TclError:
                has_selection = False

            # Check if textbox has any content
            has_content = len(textbox.get(1.0, tk.END).strip()) > 0

            # Check clipboard for paste functionality
            has_clipboard = False
            try:
                clipboard_content = textbox.clipboard_get()
                has_clipboard = bool(clipboard_content)
            except tk.TclError:
                has_clipboard = False

            # Get menu labels (they might have icons or emoji fallbacks)
            copy_label = self.menu_icons.get('copy', {}).get('label', '📋 Copy')
            cut_label = self.menu_icons.get('cut', {}).get('label', '✂️ Cut')
            select_all_label = self.menu_icons.get('select_all', {}).get('label', '📄 Select All')
            save_label = self.menu_icons.get('save', {}).get('label', '💾 Save Text to File')
            paste_label = self.menu_icons.get('paste', {}).get('label', '📋 Paste')

            # Enable/disable menu items based on context
            try:
                context_menu.entryconfig(copy_label, state="normal" if has_selection else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(cut_label, state="normal" if has_selection else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(select_all_label, state="normal" if has_content else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(save_label, state="normal" if has_content else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(paste_label, state="normal" if has_clipboard else "disabled")
            except tk.TclError:
                pass

            # Show menu
            context_menu.tk_popup(event.x_root, event.y_root)

        except Exception as e:
            logger.error(f"Failed to show textbox context menu: {e}")
        finally:
            context_menu.grab_release()

    def textbox_paste(self, textbox):
        """Paste text from clipboard"""
        try:
            clipboard_content = textbox.clipboard_get()
            if clipboard_content:
                # Insert at current cursor position
                textbox.insert(tk.INSERT, clipboard_content)
                messagebox.showinfo("Paste", "Text pasted from clipboard!")
                logger.info("Text pasted from clipboard")
            else:
                messagebox.showwarning("Paste", "Clipboard is empty!")
        except tk.TclError:
            messagebox.showwarning("Paste", "Clipboard is empty!")
        except Exception as e:
            logger.error(f"Failed to paste text: {e}")
            messagebox.showerror("Error", f"Failed to paste text: {str(e)}")

    def textbox_select_all(self, textbox):
        """Select all text in textbox"""
        try:
            textbox.tag_add("sel", "1.0", "end")
            textbox.mark_set("insert", "1.0")
            textbox.see("insert")
            logger.info("Selected all text in textbox")
        except Exception as e:
            logger.error(f"Failed to select all text: {e}")

    def textbox_copy(self, textbox):
        """Copy selected text to clipboard"""
        try:
            selected_text = textbox.selection_get()
            if selected_text:
                textbox.clipboard_clear()
                textbox.clipboard_append(selected_text)
                messagebox.showinfo("Copy", "Text copied to clipboard!")
                logger.info("Text copied to clipboard")
            else:
                messagebox.showwarning("Copy", "No text selected!")
        except tk.TclError:
            messagebox.showwarning("Copy", "No text selected!")
        except Exception as e:
            logger.error(f"Failed to copy text: {e}")
            messagebox.showerror("Error", f"Failed to copy text: {str(e)}")

    def textbox_cut(self, textbox):
        """Cut selected text to clipboard"""
        try:
            selected_text = textbox.selection_get()
            if selected_text:
                textbox.clipboard_clear()
                textbox.clipboard_append(selected_text)
                textbox.delete("sel.first", "sel.last")
                messagebox.showinfo("Cut", "Text cut to clipboard!")
                logger.info("Text cut to clipboard")
            else:
                messagebox.showwarning("Cut", "No text selected!")
        except tk.TclError:
            messagebox.showwarning("Cut", "No text selected!")
        except Exception as e:
            logger.error(f"Failed to cut text: {e}")
            messagebox.showerror("Error", f"Failed to cut text: {str(e)}")

    def textbox_undo(self, textbox):
        """Undo last action in textbox"""
        try:
            textbox.edit_undo()
            logger.info("Undo action performed")
        except tk.TclError:
            messagebox.showinfo("Undo", "Nothing to undo!")
        except Exception as e:
            logger.error(f"Failed to undo: {e}")
            messagebox.showerror("Error", f"Failed to undo: {str(e)}")

    def save_text_to_file(self, textbox):
        """Save textbox content to file"""
        try:
            # Get text content
            text_content = textbox.get(1.0, tk.END).strip()

            if not text_content:
                messagebox.showwarning("Save", "No text to save!")
                return

            # Define file types
            file_types = [
                ("Text files", "*.txt"),
                ("Log files", "*.log"),
                ("Rich Text Format", "*.rtf"),
                ("All files", "*.*")
            ]

            # Open save dialog
            filename = filedialog.asksaveasfilename(
                title="Save Text As",
                defaultextension=".txt",
                filetypes=file_types,
                parent=self.ocr_window
            )

            if filename:
                # Save the text
                with open(filename, 'w', encoding='utf-8') as file:
                    file.write(text_content)

                messagebox.showinfo("Success", f"Text saved successfully!\n{filename}")
                logger.info(f"Text saved to: {filename}")

        except Exception as e:
            error_msg = f"Failed to save text: {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)

    # Modified setup_extracted_text_column method
    def setup_extracted_text_column(self, parent):
        """Setup the left column with extracted text - OPTIMIZED"""
        left_frame = customtkinter.CTkFrame(parent)
        left_frame.grid(row=0, column=0, sticky="nsew", padx=(20, 10), pady=20)
        left_frame.grid_rowconfigure(1, weight=1)
        left_frame.grid_columnconfigure(0, weight=1)

        # Extracted text label
        extracted_label = customtkinter.CTkLabel(
            left_frame,
            text="Extracted Text",
            font=customtkinter.CTkFont(size=14, weight="bold")
        )
        extracted_label.grid(row=0, column=0, pady=(15, 5), sticky="ew")

        # Extracted text box
        self.extracted_text = customtkinter.CTkTextbox(
            left_frame,
            font=customtkinter.CTkFont(size=12),
            undo=True,
            height=470
        )
        self.extracted_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")

        # Context menu (lightweight)
        self.extracted_text_menu = self.create_textbox_context_menu(self.extracted_text)
        self.extracted_text.bind("<Button-3>", lambda e: self.show_textbox_context_menu(e, self.extracted_text_menu))

        # OPTIMIZED Bottom section - single frame instead of nested frames
        bottom_frame = customtkinter.CTkFrame(left_frame, fg_color="#292929", bg_color="#292929")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))

        # Configure grid for 2x3 layout
        bottom_frame.grid_columnconfigure((0, 1), weight=1)

        # Source language label
        source_lang_label = customtkinter.CTkLabel(bottom_frame, text="Source Language:")
        source_lang_label.grid(row=0, column=0, pady=(10, 5), padx=(0, 10))

        # CRITICAL OPTIMIZATION: Use a smaller initial language list
        common_languages = [
            "English", "Spanish", "French", "German", "Italian", "Portuguese",
            "Chinese", "Japanese", "Korean", "Arabic", "Russian", "Hindi", "Romanian"
        ]

        self.source_language = customtkinter.CTkComboBox(
            bottom_frame,
            values=common_languages,  # Start with common languages only
            width=300
        )
        self.source_language.grid(row=1, column=0, padx=(0, 10))

        # Export button
        export_extracted_btn = customtkinter.CTkButton(
            bottom_frame,
            text="Export Text",
            width=120,
            height=35,
            image=self.export_image,
            command=self.export_extracted_text
        )
        export_extracted_btn.grid(row=2, column=0, pady=(10, 15), padx=(0, 10))

        # Check language button
        self.check_language_button = customtkinter.CTkButton(
            bottom_frame,
            text="Check Language",
            image=self.check_image,
            command=self.check_lang,
            height=35,
            width=120
        )
        self.check_language_button.grid(row=1, column=1, padx=(0, 10))

        # Detected language label
        self.detected_lang_label = customtkinter.CTkLabel(
            bottom_frame,
            text="Detected: Not analyzed",
            font=customtkinter.CTkFont(size=11),
            text_color="gray"
        )
        self.detected_lang_label.grid(row=2, column=1, pady=(10, 15))

        # OPTIONAL: Add full language list later (only if you need the scrollable dropdown)
        # Uncomment the next line if you want the full scrollable dropdown
        left_frame.after(500, lambda: self.add_full_language_support(self.source_language))

    def setup_control_buttons_column(self, parent):
        """Setup the middle column with control buttons"""
        middle_frame = customtkinter.CTkFrame(parent, fg_color="#212121", bg_color="#212121")
        middle_frame.grid(row=0, column=1, sticky="ns", padx=5, pady=20)

        # Add some spacing from top
        spacer = customtkinter.CTkLabel(middle_frame, text="")
        spacer.pack(pady=100)

        # Process OCR button
        process_btn = customtkinter.CTkButton(
            middle_frame,
            text="Process OCR",
            width=120,
            height=40,
            image=self.ocr_image,
            command=self.process_ocr
        )
        process_btn.pack(pady=10)

        # Translate button
        translate_btn = customtkinter.CTkButton(
            middle_frame,
            text="Translate",
            width=120,
            height=40,
            image=self.translate_image,
            command=self.translate_text
        )
        translate_btn.pack(pady=10)

        # Clear button
        clear_btn = customtkinter.CTkButton(
            middle_frame,
            text="Clear",
            width=120,
            height=40,
            image=self.clear_image,
            command=self.clear_text_boxes
        )
        clear_btn.pack(pady=10)

    def create_translated_textbox_context_menu(self, textbox_widget):
        """Create right-click context menu for translated textbox with limited options"""
        # Load icons if not already loaded
        if not hasattr(self, 'menu_icons'):
            self.load_menu_icons()

        # Create context menu
        context_menu = tk.Menu(textbox_widget, tearoff=0)

        # Select All
        select_all_config = self.get_menu_config('select_all')
        context_menu.add_command(
            command=lambda: self.textbox_select_all(textbox_widget),
            **select_all_config
        )

        context_menu.add_separator()

        # Copy
        copy_config = self.get_menu_config('copy')
        context_menu.add_command(
            command=lambda: self.textbox_copy(textbox_widget),
            **copy_config
        )

        context_menu.add_separator()

        # Save
        save_config = self.get_menu_config('save')
        context_menu.add_command(
            command=lambda: self.save_text_to_file(textbox_widget),
            **save_config
        )

        return context_menu

    def show_translated_textbox_context_menu(self, event, context_menu):
        """Show context menu on right-click for translated textbox with proper state management"""
        try:
            # Update menu state based on text selection and content
            textbox = event.widget

            # Check if there's selected text
            has_selection = False
            try:
                if textbox.selection_get():
                    has_selection = True
            except tk.TclError:
                has_selection = False

            # Check if textbox has any content
            has_content = len(textbox.get(1.0, tk.END).strip()) > 0

            # Get menu labels (they might have icons or emoji fallbacks)
            copy_label = self.menu_icons.get('copy', {}).get('label', '📋 Copy')
            select_all_label = self.menu_icons.get('select_all', {}).get('label', '📄 Select All')
            save_label = self.menu_icons.get('save', {}).get('label', '💾 Save Text to File')

            # Enable/disable menu items based on context
            try:
                context_menu.entryconfig(copy_label, state="normal" if has_selection else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(select_all_label, state="normal" if has_content else "disabled")
            except tk.TclError:
                pass

            try:
                context_menu.entryconfig(save_label, state="normal" if has_content else "disabled")
            except tk.TclError:
                pass

            # Show menu
            context_menu.tk_popup(event.x_root, event.y_root)

        except Exception as e:
            logger.error(f"Failed to show translated textbox context menu: {e}")
        finally:
            context_menu.grab_release()

    def setup_translated_text_column(self, parent):
        """Setup the right column with translated text - OPTIMIZED"""
        right_frame = customtkinter.CTkFrame(parent)
        right_frame.grid(row=0, column=2, sticky="nsew", padx=(10, 20), pady=20)
        right_frame.grid_rowconfigure(1, weight=1)   # textbox row expands vertically
        right_frame.grid_columnconfigure(0, weight=1)

        # Translated text label
        translated_label = customtkinter.CTkLabel(
            right_frame,
            text="Translated Text",
            font=customtkinter.CTkFont(size=14, weight="bold")
        )
        translated_label.grid(row=0, column=0, pady=(15, 5), sticky="ew")

        # Translated text box
        self.translated_text = customtkinter.CTkTextbox(
            right_frame,
            font=customtkinter.CTkFont(size=12),
            state="disabled",
            height=470
        )
        self.translated_text.grid(row=1, column=0, padx=15, pady=(0, 15), sticky="nsew")

        # Context menu
        self.translated_text_menu = self.create_translated_textbox_context_menu(self.translated_text)
        self.translated_text.bind("<Button-3>",
                                  lambda e: self.show_translated_textbox_context_menu(e, self.translated_text_menu))

        # Bottom section – target language + export (fixed height, row 2)
        bottom_frame = customtkinter.CTkFrame(right_frame, fg_color="#292929", bg_color="#292929")
        bottom_frame.grid(row=2, column=0, sticky="ew", padx=15, pady=(0, 15))
        bottom_frame.grid_columnconfigure((0, 1), weight=1)

        # Target language label + combobox
        target_lang_label = customtkinter.CTkLabel(bottom_frame, text="Target Language:")
        target_lang_label.grid(row=0, column=0, pady=(10, 5), padx=(0, 10))

        common_languages = [
            "English", "Spanish", "French", "German", "Italian", "Portuguese",
            "Chinese", "Japanese", "Korean", "Arabic", "Russian", "Hindi", "Romanian"
        ]

        self.target_language = customtkinter.CTkComboBox(
            bottom_frame,
            values=common_languages,
            width=300
        )
        self.target_language.grid(row=1, column=0, padx=(0, 10))

        # Export button
        export_translated_btn = customtkinter.CTkButton(
            bottom_frame,
            text="Export Text",
            width=150,
            height=40,
            image=self.export_image,
            command=self.export_translated_text
        )
        export_translated_btn.grid(row=2, column=0, pady=(10, 15), padx=(0, 10))

        # OPTIONAL: Add full language list later
        right_frame.after(500, lambda: self.add_full_language_support(self.target_language))

    # ──────────────────────────────────────────────────────────────────────
    # Loading overlay  (animated GIF shown while OCR runs in a thread)
    # ──────────────────────────────────────────────────────────────────────

    def _show_loading_overlay(self):
        """Cover the OCR window with an animated loading GIF."""
        self._hide_loading_overlay()          # remove any stale overlay first

        if not self.ocr_window or not self.ocr_window.winfo_exists():
            return

        # Full-window overlay placed on top of every other widget
        self._loading_overlay = tk.Frame(self.ocr_window, bg="#1a1a1a", cursor="watch")
        self._loading_overlay.place(x=0, y=0, relwidth=1.0, relheight=1.0)
        self._loading_overlay.lift()

        # Initialise animation state
        self._loading_frames = []
        self._loading_frame_idx = 0
        self._loading_anim_id = None
        self._loading_gif_label = None
        self._gif_duration = 50

        gif_path = "./images/loaded.gif"
        try:
            if os.path.exists(gif_path):
                gif = Image.open(gif_path)
                self._gif_duration = max(30, gif.info.get("duration", 50))

                frames = []
                try:
                    while True:
                        frames.append(ImageTk.PhotoImage(gif.copy().convert("RGBA")))
                        gif.seek(gif.tell() + 1)
                except EOFError:
                    pass

                if frames:
                    self._loading_frames = frames
                    self._loading_gif_label = tk.Label(
                        self._loading_overlay,
                        bg="#1a1a1a",
                        bd=0,
                        highlightthickness=0,
                    )
                    self._loading_gif_label.place(relx=0.5, rely=0.42, anchor="center")
                    self._animate_loading_gif()
        except Exception as exc:
            logger.warning(f"Could not load loading GIF: {exc}")

        # Status label below the GIF
        customtkinter.CTkLabel(
            self._loading_overlay,
            text="Processing OCR, please wait…",
            font=customtkinter.CTkFont(size=16, weight="bold"),
            text_color="#ffffff",
            bg_color="#1a1a1a",
        ).place(relx=0.5, rely=0.58, anchor="center")

        self.ocr_window.update_idletasks()

    def _animate_loading_gif(self):
        """Advance to the next GIF frame and schedule the next call."""
        if not self._loading_frames or self._loading_gif_label is None:
            return
        try:
            self._loading_frame_idx = (self._loading_frame_idx + 1) % len(self._loading_frames)
            self._loading_gif_label.configure(
                image=self._loading_frames[self._loading_frame_idx]
            )
            self._loading_anim_id = self.ocr_window.after(
                self._gif_duration, self._animate_loading_gif
            )
        except Exception:
            pass

    def _hide_loading_overlay(self):
        """Cancel the GIF animation and destroy the overlay frame."""
        if getattr(self, "_loading_anim_id", None):
            try:
                self.ocr_window.after_cancel(self._loading_anim_id)
            except Exception:
                pass
            self._loading_anim_id = None

        if getattr(self, "_loading_overlay", None):
            try:
                self._loading_overlay.destroy()
            except Exception:
                pass
            self._loading_overlay = None

        self._loading_frames = []
        self._loading_gif_label = None

    def process_ocr(self):
        """Process OCR on the captured image with comprehensive error handling"""
        try:
            # Validate that we have an image to process
            if not hasattr(self, 'captured_image') or self.captured_image is None:
                error_msg = "No image captured. Please capture an image first."
                logger.error(error_msg)
                messagebox.showerror("Error", error_msg)
                return

            # Load current settings
            self.load_settings()

            # Validate OCR method selection
            if not self.default_ocr_used_value:
                error_msg = "No OCR method selected. Please select an OCR method in Settings."
                logger.error(error_msg)
                messagebox.showerror("Error", error_msg)
                return

            logger.info(f"Processing OCR with method: {self.default_ocr_used_value}")

            # Resolve the OCR method
            ocr_methods = {
                "Tesseract OCR": self._process_tesseract_ocr,
                "Mistral OCR":   self._process_mistral_ocr,
            }
            ocr_fn = ocr_methods.get(self.default_ocr_used_value)
            if ocr_fn is None:
                error_msg = f"Unknown OCR method: {self.default_ocr_used_value}"
                logger.error(error_msg)
                messagebox.showerror("Error", error_msg)
                return

            # Show the loading overlay, then run OCR in a daemon thread so the
            # main thread stays free to animate the GIF.
            self._show_loading_overlay()

            def _worker():
                try:
                    ocr_fn()
                except Exception as exc:
                    err = str(exc)
                    self._schedule_gui_update(
                        lambda: messagebox.showerror("OCR Error", err)
                    )
                finally:
                    self._schedule_gui_update(self._hide_loading_overlay)

            threading.Thread(target=_worker, daemon=True).start()

        except Exception as e:
            error_text = f"OCR processing failed: {type(e).__name__} -> {str(e)}"
            logger.error(error_text)
            messagebox.showerror("Error", error_text)
            self._hide_loading_overlay()

    def _process_tesseract_ocr(self):
        """Process OCR using Tesseract with robust error handling"""
        try:
            # Validate Tesseract path
            if not self.tesseract_exe_path or not os.path.exists(self.tesseract_exe_path):
                error_msg = "Tesseract executable not found. Please set the correct path in Settings."
                logger.error(error_msg)
                messagebox.showerror(
                    title="Tesseract Path Error",
                    message=f"{error_msg}\n\nCurrent path: {self.tesseract_exe_path or 'Not set'}"
                )
                return

            # Set Tesseract command path
            pt.pytesseract.tesseract_cmd = self.tesseract_exe_path
            logger.info(f"Using Tesseract at: {pt.pytesseract.tesseract_cmd}")

            # Validate image before processing
            if self.captured_image.mode not in ['RGB', 'L', 'RGBA']:
                logger.warning(f"Converting image from {self.captured_image.mode} to RGB")
                self.captured_image = self.captured_image.convert('RGB')

            # Process OCR with progress indication
            logger.info("Starting Tesseract OCR processing...")
            img_text = pt.image_to_string(self.captured_image)

            # Format and display results
            self._display_ocr_results(img_text, "Tesseract OCR")
            logger.info("Tesseract OCR processing completed successfully")

        except pt.TesseractNotFoundError:
            error_msg = "Tesseract executable not found or not accessible."
            logger.error(error_msg)
            messagebox.showerror(
                title="Tesseract Not Found",
                message=f"{error_msg}\n\nPlease install Tesseract or update the path in Settings.\nCurrent path: {self.tesseract_exe_path}"
            )
        except pt.TesseractError as te:
            error_msg = f"Tesseract processing error: {str(te)}"
            logger.error(error_msg)
            messagebox.showerror(
                title="Tesseract Processing Error",
                message=f"{error_msg}\n\nThis might be due to an unsupported image format or corrupted image."
            )
        except OSError as oe:
            error_msg = f"System error accessing Tesseract: {str(oe)}"
            logger.error(error_msg)
            messagebox.showerror(
                title="System Error",
                message=f"{error_msg}\n\nPlease check file permissions and Tesseract installation."
            )
        except Exception as e:
            error_msg = f"Unexpected Tesseract error: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Tesseract Error", error_msg)

    def _encode_image_to_base64(self, image):
        """Encode PIL Image to base64 string"""
        try:
            # Convert PIL Image to bytes
            img_buffer = io.BytesIO()

            # Ensure image is in RGB format for JPEG encoding
            if image.mode in ['RGBA', 'P']:
                # Convert RGBA or palette images to RGB
                rgb_image = image.convert('RGB')
            else:
                rgb_image = image

            # Save as JPEG to buffer
            rgb_image.save(img_buffer, format='JPEG', quality=95)
            img_buffer.seek(0)

            # Encode to base64
            base64_string = base64.b64encode(img_buffer.getvalue()).decode('utf-8')
            logger.info(f"Image encoded to base64 successfully (size: {len(base64_string)} chars)")

            return base64_string

        except Exception as e:
            error_msg = f"Failed to encode image to base64: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            raise Exception(error_msg)

    def _display_api_error(self, error_type, error_details, user_message):
        """Display API error in both text widget and messagebox"""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        error_header = f"""OCR Results - Mistral OCR
Failed: {timestamp}
Image dimensions: {self.captured_image.width}x{self.captured_image.height}
Error Type: {error_type}

{'-' * 100}

{error_details}

{user_message}
"""

        # Display in text widget
        self.extracted_text.delete("1.0", tk.END)
        self.extracted_text.insert(tk.END, error_header)

        # Show messagebox
        messagebox.showerror(error_type, user_message)

    def test_mistral_connection(self):
        """Test Mistral API connection with actual API call"""
        try:
            is_valid, message = self._validate_mistral_setup()
            if not is_valid:
                messagebox.showerror("Setup Error", message)
                return False

            logger.info("Testing Mistral API connection...")

            # Try to initialize client
            try:
                client = Mistral(api_key=self.mistral_ocr_key.strip())
            except Exception as e:
                error_msg = f"Failed to initialize Mistral client: {str(e)}"
                logger.error(error_msg)
                messagebox.showerror("Client Initialization Error", error_msg)
                return False

            # Test API with a minimal request to validate the key
            try:
                # Create a small test image (1x1 pixel) to minimize API usage
                import io
                from PIL import Image

                # Create minimal test image
                test_image = Image.new('RGB', (1, 1), color='white')
                img_buffer = io.BytesIO()
                test_image.save(img_buffer, format='JPEG')
                img_buffer.seek(0)
                test_base64 = base64.b64encode(img_buffer.getvalue()).decode('utf-8')

                logger.info("Sending test request to Mistral API...")

                # Make test API call
                test_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document={
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{test_base64}"
                    }
                )

                # If we get here, the API key is valid
                logger.info("Mistral API connection test successful")
                messagebox.showinfo(
                    "Connection Test Successful",
                    "✅ Mistral API connection is working!\n\nYour API key is valid and the service is accessible."
                )
                return True

            except Exception as api_error:
                error_str = str(api_error).lower()

                if "unauthorized" in error_str or "api key" in error_str or "401" in error_str:
                    error_msg = "❌ Invalid API Key\n\nThe provided API key is not valid. Please check your Mistral AI API key in Settings."
                    logger.error(f"API key validation failed: {api_error}")
                    messagebox.showerror("Invalid API Key", error_msg)
                elif "quota" in error_str or "limit" in error_str or "429" in error_str:
                    error_msg = "⚠️ API Quota Exceeded\n\nYour API quota has been exceeded. The API key is valid but you've reached your usage limits."
                    logger.warning(f"API quota exceeded during test: {api_error}")
                    messagebox.showwarning("Quota Exceeded", error_msg)
                    return True  # Key is valid, just over quota
                elif "forbidden" in error_str or "403" in error_str:
                    error_msg = "❌ Access Forbidden\n\nThe API key is valid but doesn't have permission to access OCR services."
                    logger.error(f"API access forbidden: {api_error}")
                    messagebox.showerror("Access Forbidden", error_msg)
                elif "timeout" in error_str:
                    error_msg = "⏱️ Connection Timeout\n\nThe connection to Mistral API timed out. Please check your internet connection and try again."
                    logger.error(f"API timeout during test: {api_error}")
                    messagebox.showerror("Connection Timeout", error_msg)
                elif "network" in error_str or "connection" in error_str:
                    error_msg = "🌐 Network Error\n\nCannot connect to Mistral API. Please check your internet connection."
                    logger.error(f"Network error during test: {api_error}")
                    messagebox.showerror("Network Error", error_msg)
                else:
                    error_msg = f"❌ API Test Failed\n\nUnexpected error: {str(api_error)}"
                    logger.error(f"Unexpected API error during test: {api_error}")
                    messagebox.showerror("API Test Failed", error_msg)

                return False

        except ImportError:
            error_msg = "❌ Missing Dependency\n\nMistral AI library not installed.\n\nPlease install it using:\npip install mistralai"
            logger.error(error_msg)
            messagebox.showerror("Missing Dependency", error_msg)
            return False
        except Exception as e:
            error_msg = f"❌ Connection test failed: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Connection Test Failed", error_msg)
            return False

    def _process_mistral_ocr(self):
        """Process OCR using Mistral AI with comprehensive error handling"""
        try:
            # Validate API key
            if not self.mistral_ocr_key or self.mistral_ocr_key.strip() == "":
                error_msg = "Mistral AI API key not set. Please configure your API key in Settings."
                logger.error(error_msg)
                messagebox.showerror("API Key Missing", error_msg)
                return

            # Validate image
            if not hasattr(self, 'captured_image') or self.captured_image is None:
                error_msg = "No image available for processing."
                logger.error(error_msg)
                messagebox.showerror("Image Error", error_msg)
                return

            logger.info("Starting Mistral OCR processing...")

            # Encode image to base64
            try:
                base64_image = self._encode_image_to_base64(self.captured_image)
                if not base64_image:
                    raise Exception("Failed to encode image")
            except Exception as e:
                error_msg = f"Image encoding failed: {str(e)}"
                logger.error(error_msg)
                messagebox.showerror("Image Encoding Error", error_msg)
                return

            # Initialize Mistral client
            try:
                client = Mistral(api_key=self.mistral_ocr_key.strip())
                logger.info("Mistral client initialized successfully")
            except Exception as e:
                error_msg = f"Failed to initialize Mistral client: {str(e)}"
                logger.error(error_msg)
                messagebox.showerror("API Client Error", error_msg)
                return

            # Process OCR with Mistral
            try:
                logger.info("Sending request to Mistral OCR API...")

                ocr_response = client.ocr.process(
                    model="mistral-ocr-latest",
                    document={
                        "type": "image_url",
                        "image_url": f"data:image/jpeg;base64,{base64_image}"
                    }
                )

                # Extract text from response
                if hasattr(ocr_response, 'pages') and len(ocr_response.pages) > 0:
                    if hasattr(ocr_response.pages[0], 'markdown'):
                        img_text = ocr_response.pages[0].markdown
                    elif hasattr(ocr_response.pages[0], 'text'):
                        img_text = ocr_response.pages[0].text
                    else:
                        # Fallback: try to extract any text content
                        img_text = str(ocr_response.pages[0])
                else:
                    img_text = "No text detected in the image"

                # Format and display results
                self._display_ocr_results(img_text, "Mistral OCR")
                logger.info("Mistral OCR processing completed successfully")

            except Exception as api_error:
                # Handle specific API errors with cleaner code
                error_str = str(api_error).lower()
                logger.error(f"Mistral API Error: {api_error}")

                if "unauthorized" in error_str or "api key" in error_str or "401" in error_str:
                    self._display_api_error(
                        "Authentication Error",
                        f"API Authentication Error: {api_error}",
                        "Invalid API key. Please check your Mistral AI API key in Settings."
                    )
                elif "quota" in error_str or "limit" in error_str or "429" in error_str:
                    self._display_api_error(
                        "Quota Exceeded",
                        f"API Quota Error: {api_error}",
                        "API quota exceeded. Please check your Mistral AI account limits."
                    )
                elif "timeout" in error_str:
                    self._display_api_error(
                        "Timeout Error",
                        f"API Timeout Error: {api_error}",
                        "Request timeout. Please try again or check your internet connection."
                    )
                elif "network" in error_str or "connection" in error_str:
                    self._display_api_error(
                        "Network Error",
                        f"Network Error: {api_error}",
                        "Network connection error. Please check your internet connection."
                    )
                elif "forbidden" in error_str or "403" in error_str:
                    self._display_api_error(
                        "Access Forbidden",
                        f"API Access Error: {api_error}",
                        "Access forbidden. Your API key may not have OCR permissions."
                    )
                else:
                    self._display_api_error(
                        "API Error",
                        f"Mistral API Error: {api_error}",
                        f"Unexpected API error occurred. Please try again."
                    )

                return

        except ImportError:
            error_msg = "Mistral AI library not installed. Please install it using: pip install mistralai"
            logger.error(error_msg)
            messagebox.showerror("Missing Dependency", error_msg)
        except Exception as e:
            error_msg = f"Unexpected Mistral OCR error: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Mistral OCR Error", error_msg)

    def _validate_mistral_setup(self):
        """Enhanced validation of Mistral OCR setup and dependencies"""
        try:
            # Check if mistralai library is available
            try:
                from mistralai import Mistral
            except ImportError:
                return False, "Mistral AI library not installed. Install with: pip install mistralai"

            # Check API key
            if not self.mistral_ocr_key or self.mistral_ocr_key.strip() == "":
                return False, "Mistral AI API key not configured"

            # Validate API key format (basic checks)
            api_key = self.mistral_ocr_key.strip()

            if len(api_key) < 10:
                return False, "API key appears to be invalid (too short)"

            # Check for common API key patterns (Mistral keys typically start with specific prefixes)
            if not (api_key.startswith('api_') or api_key.startswith('sk-') or len(api_key) > 20):
                logger.warning("API key format might be unusual")

            return True, "Mistral OCR setup is valid"

        except Exception as e:
            return False, f"Setup validation error: {str(e)}"

    def _display_ocr_results(self, extracted_text, ocr_method, extra_info=None):
        """Display OCR results in the text widget with metadata.

        extra_info  – optional dict of {label: value} lines inserted between the
                      image dimensions line and the separator.  Used to surface
                      the active engine settings.
        """
        try:
            # Create comprehensive result display
            timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            extra_lines = ""
            if extra_info:
                extra_lines = "".join(f"{k}: {v}\n" for k, v in extra_info.items())

            result_header = (
                f"OCR Results - {ocr_method}\n"
                f"Processed: {timestamp}\n"
                f"Image dimensions: {self.captured_image.width}x{self.captured_image.height}\n"
                f"{extra_lines}"
                f"Characters extracted: {len(extracted_text)}\n"
                f"\n{'-' * 100}\n\n"
            )

            full_ocr_text = result_header + extracted_text

            # Clear and insert new text
            self.extracted_text.delete("1.0", tk.END)
            self.extracted_text.insert(tk.END, full_ocr_text)

            # Log success
            char_count = len(extracted_text.strip())
            logger.info(f"OCR completed: {char_count} characters extracted using {ocr_method}")

            # Show success notification for very short results (might indicate issues)
            if char_count == 0:
                messagebox.showwarning(
                    "OCR Complete",
                    "OCR processing completed, but no text was extracted.\nThis might indicate an image with no text or poor image quality."
                )
            elif char_count < 5:
                messagebox.showinfo(
                    "OCR Complete",
                    f"OCR processing completed with minimal text extracted ({char_count} characters).\nPlease verify the image quality."
                )

        except Exception as e:
            error_msg = f"Error displaying OCR results: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Display Error", error_msg)

    def translate_text(self):
        """Translate the extracted text"""
        try:
            # Get the text from the GUI widget first
            source_text = self.extracted_text.get("1.0", tk.END).strip()

            if not source_text:
                messagebox.showwarning("Warning", "No text to translate")
                return

            # Check text length before translation (optional prevention)
            if len(source_text) > 54411:  # Adjust this limit as needed
                response = messagebox.askyesno(
                    "Text Too Long",
                    f"The extracted text is very long ({len(source_text)} characters). The Google Translate API limit is 54411 characters. "
                    "This might cause translation to fail.\nDo you want to continue anyway?"
                )
                if not response:
                    return

            # Show loading message
            self.translated_text.configure(state="normal")
            self.translated_text.delete("1.0", tk.END)
            self.translated_text.insert("1.0", "Translating... Please wait.")
            self.translated_text.configure(state="disabled")

            # Disable translate button during translation
            if hasattr(self, 'translate_button'):
                self.translate_button.configure(state="disabled", text="Translating...")

            # Run the async translation in a separate thread
            thread = threading.Thread(target=self._run_async_translation, daemon=True)
            thread.start()

        except Exception as e:
            error_text = f"Translation error: {e}"
            logger.error(error_text)
            messagebox.showerror("Error", error_text)
            self._reset_translate_button()

    def _run_async_translation(self):
        """Run the async translation in a separate thread"""
        try:
            # Run the async function
            asyncio.run(self._translate_async())
        except Exception as error:
            # Capture the error in a variable that won't go out of scope
            error_message = str(error)
            # Schedule the error handling in the main thread
            self._schedule_gui_update(lambda: self._handle_translation_error(error_message))

    async def _translate_async(self):
        """Perform the actual async translation"""
        try:
            # Get the text from the GUI widget
            source_text = self.extracted_text.get("1.0", tk.END).strip()

            # Get selected languages
            source_lang = self.source_language.get()
            target_lang = self.target_language.get()

            # Validate language selections
            if not source_lang or source_lang == "Select Language":
                self._schedule_gui_update(lambda: self._show_language_selection_error("source"))
                return

            if not target_lang or target_lang == "Select Language":
                self._schedule_gui_update(lambda: self._show_language_selection_error("target"))
                return

            if source_lang == target_lang:
                self._schedule_gui_update(lambda: self._show_same_language_error())
                return

            # Initialize the language keys with default values
            from_language_key = None
            to_language_key = None

            # Get Languages From Dictionary Keys
            for key, value in self.languages_dict_title.items():
                if value == source_lang:
                    from_language_key = key

            for key, value in self.languages_dict_title.items():
                if value == target_lang:
                    to_language_key = key

            # Validate that the language keys were found
            if not from_language_key:
                self._schedule_gui_update(lambda: self._show_invalid_language_error("source", source_lang))
                return

            if not to_language_key:
                self._schedule_gui_update(lambda: self._show_invalid_language_error("target", target_lang))
                return

            # Async translation
            async with Translator() as translator:
                # Await the translation
                translated_words = await translator.translate(
                    text=source_text,
                    src=from_language_key,
                    dest=to_language_key
                )

                # Schedule the GUI update in the main thread
                translated_text = translated_words.text
                self._schedule_gui_update(lambda: self._update_translation_result(translated_text))

        except Exception as error:
            # Capture the error message to avoid scope issues
            error_message = str(error)
            # Schedule error handling in the main thread
            self._schedule_gui_update(lambda: self._handle_translation_error(error_message))

    def _schedule_gui_update(self, callback):
        """Schedule a GUI update on the main thread"""
        # Option 1: If your class inherits from tk.Tk or tk.Frame
        if hasattr(self, 'after'):
            self.after(0, callback)
        # Option 2: If you have a reference to the root window
        elif hasattr(self, 'root') and hasattr(self.root, 'after'):
            self.root.after(0, callback)
        # Option 3: If you have a reference to any tkinter widget
        elif hasattr(self, 'extracted_text') and hasattr(self.extracted_text, 'after'):
            self.extracted_text.after(0, callback)
        else:
            # Fallback: try to find a tkinter widget attribute
            for attr_name in dir(self):
                attr = getattr(self, attr_name)
                if hasattr(attr, 'after') and callable(getattr(attr, 'after')):
                    attr.after(0, callback)
                    break
            else:
                # If no tkinter widget found, call directly (not thread-safe!)
                callback()

    def _update_translation_result(self, translated_text):
        """Update the GUI with translation result (runs in main thread)"""
        try:
            # Output the translated text to the screen
            self.translated_text.configure(state="normal")
            self.translated_text.delete("1.0", tk.END)
            self.translated_text.insert("1.0", translated_text)
            self.translated_text.configure(state="disabled")

            logger.info("Translation completed")

        except Exception as e:
            logger.error(f"Error updating translation result: {e}")
        finally:
            self._reset_translate_button()

    def _show_language_selection_error(self, language_type):
        """Show error when user hasn't selected a language"""
        if language_type == "source":
            message = "Please select a Source Language from the dropdown menu."
            title = "Source Language Not Selected"
        else:
            message = "Please select a Target Language from the dropdown menu."
            title = "Target Language Not Selected"

        messagebox.showwarning(title, message)
        self._reset_translate_button()

    def _show_same_language_error(self):
        """Show error when source and target languages are the same"""
        messagebox.showwarning(
            "Same Language Selected",
            "Source and target languages cannot be the same. Please select different languages."
        )
        self._reset_translate_button()

    def _show_invalid_language_error(self, language_type, language_name):
        """Show error when selected language is not found in the dictionary"""
        message = f"The selected {language_type} language '{language_name}' is not valid. Please select a correct language from the dropdown menu."
        title = f"Invalid {language_type.title()} Language"
        messagebox.showerror(title, message)
        self._reset_translate_button()

    def _handle_translation_error(self, error_message):
        """Handle translation errors (runs in main thread)"""
        # Convert error to string if it's not already
        if not isinstance(error_message, str):
            error_message = str(error_message)

        error_text = f"Translation error: {error_message}"
        logger.error(error_text)

        # Update the translated text area with error message
        self.translated_text.configure(state="normal")
        self.translated_text.delete("1.0", tk.END)
        self.translated_text.insert("1.0", f"Translation failed: {error_message}")
        self.translated_text.configure(state="disabled")

        # Show error dialog
        messagebox.showerror("Translation Error", error_text)

        self._reset_translate_button()

    def _reset_translate_button(self):
        """Reset the translate button state"""
        if hasattr(self, 'translate_button'):
            self.translate_button.configure(state="normal", text="Translate")

    def clear_text_boxes(self):
        """Clear both text boxes"""
        self.extracted_text.delete("1.0", tk.END)
        self.translated_text.configure(state="normal")
        self.translated_text.delete("1.0", tk.END)
        self.translated_text.configure(state="disabled")
        self.source_language.set("English")
        self.target_language.set("English")
        self.detected_lang_label.configure(text="Detected: Not analyzed", text_color="silver")
        logger.info("Text boxes cleared")

    def export_extracted_text(self):
        """Export extracted text to file"""
        # Check if there's a text to export
        text_content = self.extracted_text.get("1.0", tk.END).strip()
        if not text_content:
            messagebox.showwarning("Warning", "No text to export")
            return

        Files = [('Text Document', '*.txt'), ('Log files', '*.log'), ('All files', '*.*')]
        file = asksaveasfile(filetypes=Files, defaultextension='.txt')

        if file is None:  # User cancelled the dialog
            return

        try:
            # Use UTF-8 encoding to handle all Unicode characters
            with open(file.name, 'w', encoding='utf-8') as text_file:
                text_file.write(text_content)
                messagebox.showinfo('Success', f'The file "{text_file.name}" has been saved successfully.')

        except Exception as e:
            messagebox.showerror("Export Error", f"Error saving file: {str(e)}")

    def export_translated_text(self):
        """Export translated text to file"""
        # Check if there's text to export
        text_content = self.translated_text.get("1.0", tk.END).strip()
        if not text_content:
            messagebox.showwarning("Warning", "No translated text to export")
            return

        Files = [('Text Document', '*.txt'), ('Log files', '*.log'), ('All files', '*.*')]
        file = asksaveasfile(filetypes=Files, defaultextension='.txt')

        if file is None:  # User cancelled the dialog
            return

        try:
            # Use UTF-8 encoding to handle all Unicode characters
            with open(file.name, 'w', encoding='utf-8') as text_file:
                text_file.write(text_content)
                messagebox.showinfo('Success', f'The file "{text_file.name}" has been saved successfully.')

        except Exception as e:
            messagebox.showerror("Export Error", f"Error saving file: {str(e)}")

    def close_ocr_window(self):
        """Close the OCR window"""
        if self.ocr_window:
            self.ocr_window.destroy()
            self.ocr_window = None
        logger.info("OCR window closed")

    def reset_settings_to_default(self):
        """Reset all settings to their default values"""
        try:
            # Set default values in instance variables
            self.tesseract_exe_path = self.initial_tesseract_exe_path
            self.default_ocr_used_value = self.OCR_engines[0]
            self.mistral_ocr_key = self.initial_mistral_ocr_key

            # Save default settings to config file
            parser = configparser.ConfigParser()

            # Ensure all sections exist
            parser.add_section('paths')
            parser.add_section('defaultOCR')
            parser.add_section('apikey')

            # Set default values
            parser.set('paths', 'tesseract_exe_path', self.initial_tesseract_exe_path)
            parser.set('defaultOCR', 'used_ocr', self.OCR_engines[0])
            parser.set('apikey', 'mistral_ai_api_key', self.initial_mistral_ocr_key)

            # Save the config file
            with open('./settings/settings.ini', 'w') as configfile:
                parser.write(configfile)

            # Update UI elements if they exist
            self.update_ui_with_defaults()

            logger.info("Settings reset to default values")
            messagebox.showinfo("Success", "Settings have been reset to default values.")

        except Exception as e:
            error_msg = f"Error resetting settings: {type(e).__name__} -> {str(e)}"
            logger.error(error_msg)
            messagebox.showerror("Error", error_msg)

    def update_ui_with_defaults(self):
        """Update UI elements with default values"""
        try:
            # Update tesseract exe file entry
            if hasattr(self, 'tesseract_exe_file') and self.tesseract_exe_file is not None:
                self.tesseract_exe_file.configure(state=tk.NORMAL)
                self.tesseract_exe_file.delete(0, tk.END)
                self.tesseract_exe_file.insert(0, self.initial_tesseract_exe_path)
                self.tesseract_exe_file.configure(state=tk.DISABLED)

            # Update tesseract StringVar
            self.tesseract_exe_text.set(self.initial_tesseract_exe_path)

            # Update OCR combobox
            if hasattr(self, 'default_ocr_combobox') and self.default_ocr_combobox is not None:
                self.default_ocr_combobox.set(self.OCR_engines[0])

            # Update combobox StringVar
            self.combobox_var.set(self.OCR_engines[0])

            # Update Mistral API key entry
            if hasattr(self, 'mistral_api_key_entry') and self.mistral_api_key_entry is not None:
                self.mistral_api_key_entry.delete(0, tk.END)
                self.mistral_api_key_entry.insert(0, self.initial_mistral_ocr_key)

            # Update Mistral API key StringVar
            self.mistral_api_key_text.set(self.initial_mistral_ocr_key)

            logger.debug("UI elements updated with default values")

        except Exception as e:
            logger.error(f"Error updating UI elements: {e}")

    def load_image(self, image_path, size=(20, 20)):
        """Load and resize an image"""
        try:
            image = Image.open(image_path)
            image = image.resize(size, Image.Resampling.LANCZOS)
            return customtkinter.CTkImage(light_image=image, dark_image=image, size=size)
        except Exception as e:
            logger.error(f"Error loading image {image_path}: {e}")
            # print(f"Error loading image {image_path}: {e}")
            return None

    def load_all_images(self):
        """Load all required images for the settings window"""
        image_configs = [
            ("./images/refresh.png", "refresh_image", (20, 20)),
            ("./images/redo.png", "redo_image", (20, 20)),
            ("./images/api.png", "api_image", (20, 20)),
            ("./images/white_check.png", "white_check_image", (20, 20)),
            ("./images/download_file.png", "download_file_image", (20, 20)),
            ("./images/add_file.png", "add_file_image", (20, 20)),
            ("./images/check_all.png", "check_image", (20, 20)),
            ("./images/check.png", "check_image", (20, 20))
        ]

        for image_path, attr_name, size in image_configs:
            setattr(self, attr_name, self.load_image(image_path, size))

    def _clean_var_traces(self, *variables):
        """Remove all Tcl traces from tkinter variables.

        CTkEntry / CTkInput registers an internal trace on its textvariable but
        does NOT clean it up when the widget is destroyed.  On the next open of
        the settings window a new widget is created with the same StringVar, the
        old (dead) trace fires, and tkinter raises TclError.  Calling this before
        recreating any settings widget prevents that.
        """
        for var in variables:
            if var is None:
                continue
            for mode, cbname in list(var.trace_info()):
                try:
                    var.trace_remove(mode, cbname)
                except Exception:
                    pass

    def save_config_setting(self, section, key, value):
        """Helper method to save a single configuration setting"""
        try:
            parser = configparser.ConfigParser()
            parser.read('./settings/settings.ini')

            if not parser.has_section(section):
                parser.add_section(section)

            parser.set(section, key, value)

            with open('./settings/settings.ini', 'w') as configfile:
                parser.write(configfile)

        except Exception as e:
            logger.error(f"Error saving config setting {section}.{key}: {e}")

    def default_ocr_combobox_callback(self, choice):
        """Callback for OCR engine selection"""
        self.default_ocr_used_value = choice
        self.save_config_setting('defaultOCR', 'used_ocr', choice)
        logger.info(f"OCR engine changed to: {choice}")
        self._update_ocr_section_visibility()

    def _update_ocr_section_visibility(self):
        """Show/hide settings widgets based on the selected OCR engine"""
        is_mistral = self.default_ocr_used_value == "Mistral OCR"
        is_tesseract = self.default_ocr_used_value == "Tesseract OCR"

        mistral_widgets = [
            self.mistral_api_key_label,
            self.mistral_api_key_entry,
            self.mistral_get_api_key_button,
            self.test_mistral_connection_button,
        ]
        tesseract_widgets = [
            self.default_tesseract_exe_label,
            self.tesseract_exe_file,
            self.tesseract_browse_button,
            self.tesseract_get_installer_button,
        ]

        for widget in mistral_widgets:
            if widget is not None:
                if is_mistral:
                    widget.grid()
                else:
                    widget.grid_remove()

        for widget in tesseract_widgets:
            if widget is not None:
                if is_tesseract:
                    widget.grid()
                else:
                    widget.grid_remove()

    def mistral_ocr_key_on_entry_change(self, *args):
        """Callback for Mistral API key changes"""
        # Skip saving during initialization
        if hasattr(self, '_initializing_api_key') and self._initializing_api_key:
            return

        self.mistral_ocr_key = self.mistral_api_key_text.get()
        self.save_config_setting('apikey', 'mistral_ai_api_key', self.mistral_ocr_key)

    def browse_tesseract_exe_file(self):
        """Browse for tesseract executable file"""
        try:
            file = filedialog.askopenfile(mode='r', filetypes=[('Executable files', 'tesseract.exe')])
            if file:
                self.tesseract_exe_path = os.path.abspath(file.name)
                self.tesseract_exe_text.set(str(self.tesseract_exe_path))
                self.save_config_setting('paths', 'tesseract_exe_path', self.tesseract_exe_path)
                logger.info(f"Tesseract path updated: {self.tesseract_exe_path}")
        except Exception as e:
            logger.error(f"Error browsing tesseract file: {e}")
            messagebox.showerror("Error", f"Failed to select tesseract file: {e}")

    def get_installer(self):
        """Open tesseract installer page"""
        try:
            webbrowser.open_new("https://github.com/UB-Mannheim/tesseract/wiki")
        except Exception as e:
            logger.error(f"Error opening installer page: {e}")
            messagebox.showerror("Error", f"Failed to open help page!\n{e}")

    def get_mistral_api_key(self):
        """Open Mistral API key page"""
        try:
            webbrowser.open_new("https://console.mistral.ai/api-keys")
        except Exception as e:
            logger.error(f"Error opening Mistral API page: {e}")
            messagebox.showerror("Error", f"Failed to open help page!\n{e}")

    def create_settings_header(self, parent):
        """Create the settings header section"""
        settings_frame_header = customtkinter.CTkFrame(
            master=parent,
            fg_color='#292929',
            corner_radius=0,
            bg_color="#292929",
            border_width=0
        )
        settings_frame_header.pack(fill=tk.BOTH)

        title_label = customtkinter.CTkLabel(
            master=settings_frame_header,
            corner_radius=0,
            font=customtkinter.CTkFont(size=21, weight="bold"),
            fg_color="transparent",
            text="Settings",
            text_color="silver"
        )
        title_label.grid(row=0, column=0, sticky="w", padx=10, pady=10)

        settings_page_note_label = customtkinter.CTkLabel(
            master=settings_frame_header,
            corner_radius=0,
            font=customtkinter.CTkFont(size=11, weight="normal"),
            fg_color="transparent",
            text="If the application settings have been modified, you need to restart the OCRLing tool to apply the changes.",
            text_color="silver"
        )
        settings_page_note_label.grid(row=1, column=0, sticky="w", padx=10, pady=5)

        return settings_frame_header

    def create_ocr_settings(self, parent):
        """Create OCR engine settings section"""
        # Remove stale CTkEntry internal traces left from a previous settings window
        self._clean_var_traces(self.mistral_api_key_text)

        settings_default_ocr_header = customtkinter.CTkFrame(
            master=parent,
            fg_color='#292929',
            corner_radius=0,
            bg_color="#292929",
            border_width=0
        )
        settings_default_ocr_header.pack(fill=tk.BOTH)
        self.ocr_engine_frame = settings_default_ocr_header

        # OCR Engine selection
        choose_default_ocr_label = customtkinter.CTkLabel(
            master=settings_default_ocr_header,
            corner_radius=0,
            fg_color="transparent",
            text="Choose default OCR engine: ",
            text_color="silver"
        )
        choose_default_ocr_label.grid(row=0, column=0, sticky="w", padx=5, pady=10)

        self.default_ocr_combobox = customtkinter.CTkComboBox(
            master=settings_default_ocr_header,
            values=self.OCR_engines,
            command=self.default_ocr_combobox_callback,
            variable=self.combobox_var
        )
        self.combobox_var.set(self.default_ocr_used_value)
        self.default_ocr_combobox.grid(row=0, column=1, sticky="w", padx=10, pady=10)

        # Mistral API Key
        self.mistral_api_key_label = customtkinter.CTkLabel(
            master=settings_default_ocr_header,
            corner_radius=0,
            fg_color='transparent',
            text="Mistral AI API Key: ",
            text_color="silver"
        )
        self.mistral_api_key_label.grid(row=1, column=0, sticky="w", padx=10, pady=10)

        # Add tooltip if CreateToolTip is available
        try:
            CreateToolTip(self.mistral_api_key_label,
                          "The Mistral API key retrieved from https://console.mistral.ai/api-keys")
        except NameError:
            pass  # CreateToolTip not available

        # Create the entry widget first
        self.mistral_api_key_entry = CTkInput(
            master=settings_default_ocr_header,
            corner_radius=5,
            height=35,
            width=400,
            border_width=1,
            placeholder_text_color="silver",
            text_color="silver",
            textvariable=self.mistral_api_key_text)
        self.mistral_api_key_entry.grid(row=1, column=1, sticky="w", padx=10, pady=10)

        self.mistral_api_key_entry.password_input()

        # Set up the trace callback first
        self.mistral_api_key_text.trace_add("write", self.mistral_ocr_key_on_entry_change)

        # Use a flag to prevent callback during initialization
        self._initializing_api_key = True
        self.mistral_api_key_entry.delete(0, tk.END)  # Clear any existing content
        self.mistral_api_key_entry.insert(0, self.mistral_ocr_key)
        self._initializing_api_key = False

        self.mistral_get_api_key_button = customtkinter.CTkButton(
            master=settings_default_ocr_header,
            text="Get API Key",
            command=self.get_mistral_api_key,
            image=self.api_image,
            compound="left"
        )
        self.mistral_get_api_key_button.grid(row=1, column=2, padx=3, pady=3, sticky="nswe")

        self.test_mistral_connection_button = customtkinter.CTkButton(
            master=settings_default_ocr_header,
            text="Test API Key",
            command=self.test_mistral_connection,
            image=self.white_check_image,
            compound="left"
        )
        self.test_mistral_connection_button.grid(row=1, column=3, padx=9, pady=3, sticky="nswe")

        return settings_default_ocr_header

    def create_tesseract_settings(self, parent):
        """Create Tesseract settings section"""
        # Remove stale CTkEntry internal traces left from a previous settings window
        self._clean_var_traces(self.tesseract_exe_text)

        settings_frame_bottom = customtkinter.CTkFrame(
            master=parent,
            fg_color='#292929',
            corner_radius=0,
            bg_color="#292929",
            border_width=0
        )
        settings_frame_bottom.pack(fill=tk.BOTH, expand=True)

        # Tesseract path
        self.default_tesseract_exe_label = customtkinter.CTkLabel(
            master=settings_frame_bottom,
            corner_radius=0,
            fg_color="transparent",
            text="Default tesseract.exe path: ",
            text_color="silver"
        )
        self.default_tesseract_exe_label.grid(row=0, column=0, sticky="e", padx=10, pady=10)

        self.tesseract_exe_file = customtkinter.CTkEntry(
            master=settings_frame_bottom,
            corner_radius=5,
            height=35,
            width=400,
            border_width=1,
            placeholder_text_color="silver",
            text_color="silver",
            textvariable=self.tesseract_exe_text
        )
        self.tesseract_exe_file.configure(state=tk.DISABLED)
        self.tesseract_exe_file.grid(row=0, column=1, padx=3, pady=3)
        self.tesseract_exe_file.insert(0, self.tesseract_exe_path)

        # Browse button
        self.tesseract_browse_button = customtkinter.CTkButton(
            master=settings_frame_bottom,
            text="Browse",
            command=self.browse_tesseract_exe_file,
            image=self.add_file_image,
            compound="left"
        )
        self.tesseract_browse_button.grid(row=0, column=2, padx=10, pady=3, sticky="nswe")

        # Get installer button
        self.tesseract_get_installer_button = customtkinter.CTkButton(
            master=settings_frame_bottom,
            text="Get installer",
            command=self.get_installer,
            image=self.download_file_image,
            compound="left"
        )
        self.tesseract_get_installer_button.grid(row=0, column=3, padx=3, pady=3, sticky="nswe")

        # Reset settings
        customtkinter.CTkLabel(
            master=settings_frame_bottom,
            corner_radius=0,
            fg_color="transparent",
            text="Reset settings to default: ",
            text_color="silver"
        ).grid(row=1, column=0, sticky="e", padx=10, pady=10)

        redo_button = customtkinter.CTkButton(
            master=settings_frame_bottom,
            text="Reset",
            fg_color="#2874A6",
            hover_color="#5499C7",
            text_color="white",
            width=90,
            height=40,
            hover=True,
            image=self.redo_image,
            compound="left",
            command=self.reset_settings_to_default
        )
        redo_button.grid(row=1, column=1, padx=10, pady=10, sticky="w")

        # Restart application
        customtkinter.CTkLabel(
            master=settings_frame_bottom,
            corner_radius=0,
            fg_color="transparent",
            text="Restart application: ",
            text_color="silver"
        ).grid(row=2, column=0, sticky="e", padx=0, pady=10)

        restart_button = customtkinter.CTkButton(
            master=settings_frame_bottom,
            text="Restart",
            fg_color="#2874A6",
            hover_color="#5499C7",
            text_color="white",
            width=90,
            height=40,
            hover=True,
            image=self.refresh_image,
            compound="left",
            command=self.restart_program
        )
        restart_button.grid(row=2, column=1, padx=10, pady=10, sticky="w")

        return settings_frame_bottom

    def restart_program(self):
        try:
            # Get the current script path
            script_path = sys.argv[0]

            # Start new process
            subprocess.Popen([sys.executable, script_path] + sys.argv[1:])

            # Exit current process
            sys.exit(0)
        except Exception as e:
            print(f"Failed to restart: {e}")

    def go_to_settings(self):
        """Open settings window"""
        try:
            # Check if settings window already exists
            if self.settings_page is not None:
                try:
                    self.settings_page.focus()
                    return
                except:
                    # Window might be destroyed, reset it
                    self.settings_page = None

            logger.info("Opening Settings window")

            # Create settings window
            self.settings_page = customtkinter.CTkToplevel(self.root)
            self.settings_page.title("Settings")

            window_width = 950
            window_height = 370

            # Center the window on the screen
            self.settings_page.minsize(window_width, window_height)
            self.settings_page.maxsize(window_width, window_height)
            self.settings_page.update_idletasks()

            screen_width = self.settings_page.winfo_screenwidth()
            screen_height = self.settings_page.winfo_screenheight()
            x_coordinate = int((screen_width / 2) - (window_width / 2))
            y_coordinate = int((screen_height / 2) - (window_height / 2))

            self.settings_page.geometry(
                f"{window_width}x{window_height}+{x_coordinate}+{y_coordinate}"
            )
            self.settings_page.resizable(False, False)

            # Set icon with error handling
            try:
                if os.path.exists("./images/app_logo.ico"):
                    self.settings_page.after(201, lambda: self.settings_page.iconbitmap("./images/app_logo.ico"))
                else:
                    logger.warning("Icon file not found: ./images/app_logo.ico")
            except Exception as icon_error:
                logger.error(f"Icon loading error: {icon_error}")

            # Load all images
            self.load_all_images()

            logger.debug("Creating Settings frame")

            # Create main settings frame
            settings_frame = customtkinter.CTkFrame(self.settings_page, corner_radius=0)
            settings_frame.pack(fill="both", expand=True, padx=20, pady=20)

            # Create sections
            self.create_settings_header(settings_frame)
            self.create_ocr_settings(settings_frame)
            self.create_tesseract_settings(settings_frame)

            # Apply initial visibility based on saved OCR engine choice
            self._update_ocr_section_visibility()

            logger.info("Settings window created successfully")

            # Force the window to appear
            self.settings_page.lift()
            self.settings_page.focus_force()

            logger.info("Settings window opened")

        except Exception as e:
            error_text = f"Settings error: {type(e).__name__} -> {str(e)}"
            logger.error(f"Settings window error: {error_text}")

            # Reset settings_page if there was an error
            self.settings_page = None
            self.root.after(0, lambda: messagebox.showerror("Error", error_text))

    def close_settings(self):
        """Close Settings window"""
        try:
            if self.settings_page is not None:
                self.settings_page.destroy()
                self.settings_page = None
                logger.info("Settings window closed")
        except Exception as e:
            print(f"Error closing settings: {e}")
            self.settings_page = None

    def go_to_help(self):
        help_file_path = r".\documentation\help.html"

        try:
            # Check if the help file exists
            if not os.path.exists(help_file_path):
                error_msg = f"Help file not found at: {os.path.abspath(help_file_path)}"
                logger.error(error_msg)
                messagebox.showerror(
                    "Help File Missing",
                    f"The help documentation could not be found.\n\n"
                    f"Expected location: {os.path.abspath(help_file_path)}\n\n"
                    f"Please ensure the documentation folder and help.html file exist."
                )
                return

            # Check if the file is readable
            if not os.access(help_file_path, os.R_OK):
                error_msg = f"Help file exists but is not readable: {os.path.abspath(help_file_path)}"
                logger.error(error_msg)
                messagebox.showerror(
                    "File Access Error",
                    f"The help file exists but cannot be accessed.\n\n"
                    f"Please check file permissions for: {os.path.abspath(help_file_path)}"
                )
                return

            # Get absolute path for better browser compatibility
            abs_path = os.path.abspath(help_file_path)
            file_url = f"file:///{abs_path.replace(os.sep, '/')}"

            # Try to open the help file
            logger.info(f"Opening help file: {abs_path}")
            webbrowser.open_new(file_url)

        except PermissionError as PermissionError_ex:
            error_msg = f"Permission denied accessing help file: {help_file_path}"
            logger.error(error_msg)
            logger.error(PermissionError_ex, exc_info=True)
            messagebox.showerror(
                "Permission Error",
                f"Permission denied when trying to access the help file.\n\n"
                f"Please check file permissions or run as administrator."
            )

        except FileNotFoundError as FileNotFoundError_ex:
            error_msg = f"Help file not found: {help_file_path}"
            logger.error(error_msg)
            logger.error(FileNotFoundError_ex, exc_info=True)
            messagebox.showerror(
                "File Not Found",
                f"The help file could not be found.\n\n"
                f"Please ensure the documentation is properly installed."
            )

        except OSError as OSError_ex:
            error_msg = f"System error opening help file: {help_file_path}"
            logger.error(error_msg)
            logger.error(OSError_ex, exc_info=True)
            messagebox.showerror(
                "System Error",
                f"A system error occurred while trying to open the help file.\n\n"
                f"Error details: {str(OSError_ex)}"
            )

        except Exception as General_ex:
            error_msg = f"Unexpected error opening help file: {help_file_path}"
            logger.error(error_msg)
            logger.error(General_ex, exc_info=True)
            messagebox.showerror(
                "Unexpected Error",
                f"An unexpected error occurred while trying to open the help file.\n\n"
                f"Error details: {str(General_ex)}\n\n"
                f"Please contact support if this problem persists."
            )

    def go_to_qr_barcode_reader(self):
        qr_file_path = r".\documentation\qr_barcode_reader.html"

        try:
            if not os.path.exists(qr_file_path):
                error_msg = f"QR & Barcode Reader file not found at: {os.path.abspath(qr_file_path)}"
                logger.error(error_msg)
                messagebox.showerror(
                    "File Missing",
                    f"The QR & Barcode Reader page could not be found.\n\n"
                    f"Expected location: {os.path.abspath(qr_file_path)}\n\n"
                    f"Please ensure the documentation folder and qr_barcode_reader.html file exist."
                )
                return

            if not os.access(qr_file_path, os.R_OK):
                error_msg = f"QR & Barcode Reader file exists but is not readable: {os.path.abspath(qr_file_path)}"
                logger.error(error_msg)
                messagebox.showerror(
                    "File Access Error",
                    f"The QR & Barcode Reader file exists but cannot be accessed.\n\n"
                    f"Please check file permissions for: {os.path.abspath(qr_file_path)}"
                )
                return

            abs_path = os.path.abspath(qr_file_path)
            file_url = f"file:///{abs_path.replace(os.sep, '/')}"
            logger.info(f"Opening QR & Barcode Reader: {abs_path}")
            webbrowser.open_new(file_url)

        except Exception as e:
            error_msg = f"Unexpected error opening QR & Barcode Reader: {qr_file_path}"
            logger.error(error_msg)
            logger.error(e, exc_info=True)
            messagebox.showerror(
                "Unexpected Error",
                f"An unexpected error occurred while trying to open the QR & Barcode Reader.\n\n"
                f"Error details: {str(e)}"
            )

    @logger.catch(level="DEBUG")
    def go_to_desktop_color_picker(self):
        """Launch the desktop color picker window"""
        if self.desktop_color_picker and self.desktop_color_picker.winfo_exists():
            self.desktop_color_picker.deiconify()
            self.desktop_color_picker.focus()
            return

        self.desktop_color_picker = customtkinter.CTkToplevel(fg_color="#242424")
        self.desktop_color_picker.title("Desktop Color Picker")
        window_width = 480
        window_height = 1015

        self.desktop_color_picker.attributes("-topmost", True)

        # Center the window on the screen
        # self.desktop_color_picker.minsize(window_width, window_height)
        self.desktop_color_picker.maxsize(window_width, window_height)

        self.desktop_color_picker.update_idletasks()

        screen_width = self.desktop_color_picker.winfo_screenwidth()
        screen_height = self.desktop_color_picker.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - (window_width / 2))
        y_cordinate = int((screen_height / 2) - (window_height / 2))

        self.desktop_color_picker.geometry(
            "{}x{}+{}+{}".format(window_width, window_height, x_cordinate, y_cordinate))

        self.desktop_color_picker.resizable(False, True)
        self.desktop_color_picker.after(201, lambda: self.desktop_color_picker.iconbitmap("./images/app_logo.ico"))

        # Setup the color picker UI
        self.setup_color_picker_ui()

        # Bind close event
        self.desktop_color_picker.protocol("WM_DELETE_WINDOW", self.close_color_picker)

    @logger.catch(level="DEBUG")
    def setup_color_picker_ui(self):
        """Setup the color picker user interface"""
        # Main frame
        main_frame = customtkinter.CTkScrollableFrame(master=self.desktop_color_picker, bg_color="#2b2b2b",
                                                      fg_color="#2b2b2b", corner_radius=5)
        main_frame.pack(fill="both", expand=True, padx=20, pady=20)

        pick_color_image = customtkinter.CTkImage(light_image=Image.open("./images/pick_color_white.png"),
                                                  size=(20, 20))
        copy_image = customtkinter.CTkImage(light_image=Image.open("./images/copy_white.png"), size=(20, 20))

        logger.info("Desktop Color Picker opened")

        # Title
        title_label = customtkinter.CTkLabel(master=main_frame, text="Color Information",
                                             font=customtkinter.CTkFont(size=20, weight="bold"))
        title_label.pack(pady=(10, 20))

        # Pick color button
        self.pick_btn = customtkinter.CTkButton(master=main_frame, text="Start Picking",
                                                command=self.start_color_picking,
                                                font=customtkinter.CTkFont(size=14, weight="bold"),
                                                height=30,
                                                image=pick_color_image)
        self.pick_btn.pack(pady=(0, 20))

        # Status label
        self.status_label = customtkinter.CTkLabel(master=main_frame,
                                                   text="Click 'Start Picking' then click any pixel on your screen to get its color information\n\nPress right-click to cancel picking",
                                                   font=customtkinter.CTkFont(size=11),
                                                   text_color="silver")
        self.status_label.pack(pady=(0, 10))

        # Color wheel canvas
        self.color_canvas = tk.Canvas(master=main_frame, height=self.image_dimension, width=self.image_dimension,
                                      highlightthickness=0, bg="#2b2b2b")
        self.color_canvas.pack(pady=(10, 20))

        # Load color wheel and target images
        self.load_color_wheel_images()

        # Color info frame
        info_frame = customtkinter.CTkFrame(master=main_frame, fg_color="#333333", bg_color="#333333", corner_radius=5)
        info_frame.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # Hex color
        hex_frame = customtkinter.CTkFrame(master=info_frame, fg_color="#2B2B2B", bg_color="#2B2B2B", corner_radius=5)
        hex_frame.pack(fill="x", padx=10, pady=(10, 5))

        customtkinter.CTkLabel(hex_frame, text="Hex Color:",
                               font=customtkinter.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=5)
        self.hex_entry = customtkinter.CTkEntry(master=hex_frame, placeholder_text="#000000")
        self.hex_entry.pack(fill="x", padx=10, pady=(0, 10))

        # ARGB values
        argb_frame = customtkinter.CTkFrame(master=info_frame, fg_color="#2B2B2B", bg_color="#2B2B2B", corner_radius=5)
        argb_frame.pack(fill="x", padx=10, pady=(5, 10))

        customtkinter.CTkLabel(master=argb_frame, text="ARGB Values:",
                               font=customtkinter.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Alpha
        alpha_frame = customtkinter.CTkFrame(master=argb_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        alpha_frame.pack(fill="x", padx=10, pady=2)
        customtkinter.CTkLabel(alpha_frame, text="Alpha:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.alpha_entry = customtkinter.CTkEntry(alpha_frame, placeholder_text="255", width=80)
        self.alpha_entry.pack(side="right", padx=(5, 10), pady=5)

        # ARGB Red
        argb_red_frame = customtkinter.CTkFrame(master=argb_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        argb_red_frame.pack(fill="x", padx=10, pady=2)
        customtkinter.CTkLabel(argb_red_frame, text="Red:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.argb_red_entry = customtkinter.CTkEntry(argb_red_frame, placeholder_text="0", width=80)
        self.argb_red_entry.pack(side="right", padx=(5, 10), pady=5)

        # ARGB Green
        argb_green_frame = customtkinter.CTkFrame(master=argb_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        argb_green_frame.pack(fill="x", padx=10, pady=2)
        customtkinter.CTkLabel(argb_green_frame, text="Green:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.argb_green_entry = customtkinter.CTkEntry(argb_green_frame, placeholder_text="0", width=80)
        self.argb_green_entry.pack(side="right", padx=(5, 10), pady=5)

        # ARGB Blue
        argb_blue_frame = customtkinter.CTkFrame(master=argb_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        argb_blue_frame.pack(fill="x", padx=10, pady=(2, 10))
        customtkinter.CTkLabel(argb_blue_frame, text="Blue:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.argb_blue_entry = customtkinter.CTkEntry(argb_blue_frame, placeholder_text="0", width=80)
        self.argb_blue_entry.pack(side="right", padx=(5, 10), pady=5)

        # HSV values
        hsv_frame = customtkinter.CTkFrame(master=info_frame, fg_color="#2B2B2B", bg_color="#2B2B2B", corner_radius=5)
        hsv_frame.pack(fill="x", padx=10, pady=(5, 10))

        customtkinter.CTkLabel(master=hsv_frame, text="HSV Values:",
                               font=customtkinter.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 5))

        # Hue
        hue_frame = customtkinter.CTkFrame(master=hsv_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        hue_frame.pack(fill="x", padx=10, pady=2)
        customtkinter.CTkLabel(hue_frame, text="Hue:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.hue_entry = customtkinter.CTkEntry(hue_frame, placeholder_text="0", width=80)
        self.hue_entry.pack(side="right", padx=(5, 10), pady=5)

        # Saturation
        sat_frame = customtkinter.CTkFrame(master=hsv_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        sat_frame.pack(fill="x", padx=10, pady=2)
        customtkinter.CTkLabel(sat_frame, text="Saturation:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.sat_entry = customtkinter.CTkEntry(sat_frame, placeholder_text="0", width=80)
        self.sat_entry.pack(side="right", padx=(5, 10), pady=5)

        # Value
        val_frame = customtkinter.CTkFrame(master=hsv_frame, fg_color="#2B2B2B", bg_color="#2B2B2B")
        val_frame.pack(fill="x", padx=10, pady=(2, 10))
        customtkinter.CTkLabel(val_frame, text="Value:", width=60).pack(side="left", padx=(10, 5), pady=5)
        self.val_entry = customtkinter.CTkEntry(val_frame, placeholder_text="0", width=80)
        self.val_entry.pack(side="right", padx=(5, 10), pady=5)

        # Copy buttons frame
        copy_frame = customtkinter.CTkFrame(master=main_frame, fg_color="transparent")
        copy_frame.pack(pady=10, fill="x", padx=20)

        # Copy Hex button (left side)
        self.copy_hex_btn = customtkinter.CTkButton(master=copy_frame,
                                                    text="Copy Hex to Clipboard",
                                                    font=customtkinter.CTkFont(size=12, weight="normal"),
                                                    height=30,
                                                    command=self.copy_hex_to_clipboard,
                                                    image=copy_image)
        self.copy_hex_btn.pack(side="left", expand=True, fill="x", padx=(0, 5))

        # Copy ARGB button (right side)
        self.copy_argb_btn = customtkinter.CTkButton(master=copy_frame,
                                                     text="Copy ARGB to Clipboard",
                                                     font=customtkinter.CTkFont(size=12, weight="normal"),
                                                     height=30,
                                                     command=self.copy_argb_to_clipboard,
                                                     image=copy_image)
        self.copy_argb_btn.pack(side="right", expand=True, fill="x", padx=(5, 0))

        # Setup event bindings
        self.setup_color_picker_bindings()

    @logger.catch(level="DEBUG")
    def load_color_wheel_images(self):
        """Load or create color wheel and target images"""
        try:
            # Try to load from images folder
            wheel_path = os.path.join("images", "color_wheel.png")
            target_path = os.path.join("images", "target.png")

            if os.path.exists(wheel_path) and os.path.exists(target_path):
                self.color_wheel_image = Image.open(wheel_path).resize((self.image_dimension, self.image_dimension),
                                                                       Image.Resampling.LANCZOS)
                self.target_image = Image.open(target_path).resize((self.target_dimension, self.target_dimension),
                                                                   Image.Resampling.LANCZOS)
            else:
                # Create a simple color wheel if images don't exist
                self.create_color_wheel()

            self.wheel_photo = ImageTk.PhotoImage(self.color_wheel_image)
            self.target_photo = ImageTk.PhotoImage(self.target_image)

            # Draw initial wheel and target
            self.color_canvas.create_image(self.image_dimension / 2, self.image_dimension / 2, image=self.wheel_photo)
            self.color_canvas.create_image(self.target_x, self.target_y, image=self.target_photo)

        except Exception as e:
            logger.error(f"Error loading color wheel images: {e}")
            self.create_color_wheel()

    @logger.catch(level="DEBUG")
    def create_color_wheel(self):
        """Create a color wheel programmatically"""
        # Create a high-resolution color wheel for better quality
        wheel_size = self.image_dimension * 2
        self.color_wheel_image = Image.new('RGBA', (wheel_size, wheel_size), (0, 0, 0, 0))
        pixels = self.color_wheel_image.load()

        center_x = center_y = wheel_size // 2
        max_radius = center_x - 2

        for x in range(wheel_size):
            for y in range(wheel_size):
                dx = x - center_x
                dy = y - center_y
                distance = math.sqrt(dx * dx + dy * dy)

                if distance <= max_radius:
                    angle = math.atan2(-dy, dx)
                    hue = (angle + math.pi) / (2 * math.pi)
                    saturation = min(distance / max_radius, 1.0)
                    value = 1.0

                    rgb = colorsys.hsv_to_rgb(hue, saturation, value)
                    alpha = 255
                    if distance > max_radius - 2:
                        alpha = max(0, int(255 * (max_radius - distance + 1)))

                    pixels[x, y] = (int(rgb[0] * 255), int(rgb[1] * 255), int(rgb[2] * 255), alpha)

        # Resize back to target size
        self.color_wheel_image = self.color_wheel_image.resize((self.image_dimension, self.image_dimension),
                                                               Image.Resampling.LANCZOS)

        # Convert to RGB with background color
        background = Image.new('RGB', (self.image_dimension, self.image_dimension), '#2b2b2b')
        background.paste(self.color_wheel_image,
                         mask=self.color_wheel_image.split()[-1] if self.color_wheel_image.mode == 'RGBA' else None)
        self.color_wheel_image = background

        # Create target crosshair
        target_size = self.target_dimension * 2
        self.target_image = Image.new('RGBA', (target_size, target_size), (0, 0, 0, 0))
        target_pixels = self.target_image.load()
        target_center = target_size // 2

        line_width = 2
        for x in range(target_size):
            for y in range(target_size):
                dx = x - target_center
                dy = y - target_center
                distance = math.sqrt(dx * dx + dy * dy)

                # Vertical line
                if abs(dx) <= line_width and abs(dy) <= target_center - 2:
                    if distance > 3:
                        target_pixels[x, y] = (255, 255, 255, 200)

                # Horizontal line
                if abs(dy) <= line_width and abs(dx) <= target_center - 2:
                    if distance > 3:
                        target_pixels[x, y] = (255, 255, 255, 200)

                # Outer circle
                if abs(distance - target_center + 3) < 1:
                    target_pixels[x, y] = (0, 0, 0, 150)

        self.target_image = self.target_image.resize((self.target_dimension, self.target_dimension),
                                                     Image.Resampling.LANCZOS)

    @logger.catch(level="DEBUG")
    def setup_color_picker_bindings(self):
        """Setup event bindings for color picker"""
        # Canvas mouse events
        self.color_canvas.bind("<Button-1>", self.on_color_wheel_click)
        self.color_canvas.bind("<B1-Motion>", self.on_color_wheel_drag)

        # Entry field bindings
        self.hex_entry.bind("<KeyRelease>", self.on_hex_change)
        self.hue_entry.bind("<KeyRelease>", self.on_hsv_change)
        self.sat_entry.bind("<KeyRelease>", self.on_hsv_change)
        self.val_entry.bind("<KeyRelease>", self.on_hsv_change)

        # ARGB entry field bindings
        self.alpha_entry.bind("<KeyRelease>", self.on_argb_change)
        self.argb_red_entry.bind("<KeyRelease>", self.on_argb_change)
        self.argb_green_entry.bind("<KeyRelease>", self.on_argb_change)
        self.argb_blue_entry.bind("<KeyRelease>", self.on_argb_change)

    @logger.catch(level="DEBUG")
    def start_color_picking(self):
        """Start the color picking process"""
        if self.is_picking_color:
            return

        self.is_picking_color = True
        self.pick_btn.configure(text="Picking... (Right-click to cancel)", state="disabled")
        self.status_label.configure(text="Click anywhere on screen to pick color")

        # Minimize the color picker window
        self.desktop_color_picker.withdraw()

        # Create overlay for picking
        self.create_color_picker_overlay()

        logger.info("Color picker started")

    @logger.catch(level="DEBUG")
    def close_color_picker(self):
        """Handle application closing"""
        try:
            logger.info("Closing Desktop Color Picker...")
            self.is_picking_color = False

            # Close overlay first
            try:
                if self.color_picker_overlay and self.color_picker_overlay.winfo_exists():
                    logger.debug("Destroying color picker overlay")
                    self.color_picker_overlay.destroy()
                    self.color_picker_overlay = None
            except Exception as overlay_error:
                logger.error(f"Error destroying color picker overlay: {overlay_error}")
                logger.exception("Overlay destroy error details:")

            # Close main color picker window
            try:
                if self.desktop_color_picker and self.desktop_color_picker.winfo_exists():
                    logger.debug("Destroying desktop color picker window")
                    self.desktop_color_picker.destroy()
                    self.desktop_color_picker = None
            except Exception as window_error:
                logger.error(f"Error destroying desktop color picker window: {window_error}")
                logger.exception("Window destroy error details:")

            logger.info("Desktop Color Picker closed successfully")

        except Exception as e:
            logger.error(f"Unexpected error in close_color_picker: {e}")
            logger.exception("Close color picker error details:")

    @logger.catch(level="DEBUG")
    def create_color_picker_overlay(self):
        """Create fullscreen overlay for color picking"""
        self.color_picker_overlay = tk.Toplevel(self.desktop_color_picker)

        # Make full-screen transparent overlay
        self.color_picker_overlay.attributes("-fullscreen", True)
        self.color_picker_overlay.attributes("-topmost", True)
        self.color_picker_overlay.attributes("-alpha", 0.01)
        self.color_picker_overlay.configure(bg='black')

        # Remove window decorations
        self.color_picker_overlay.overrideredirect(True)

        # Create crosshair cursor
        self.color_picker_overlay.configure(cursor="crosshair")

        # Instructions label
        info_label = tk.Label(self.color_picker_overlay, text="Click to pick color • Right click to cancel",
                              bg='black', fg='white', font=('Arial', 12))
        info_label.pack(pady=20)

        # Bind events - Fixed event binding
        self.color_picker_overlay.bind("<Button-1>", self.on_color_pick_click)
        self.color_picker_overlay.bind("<Button-3>", self.cancel_color_picking)

        # Also bind to the label to ensure it captures the event
        # info_label.bind("<Button-3>", self.cancel_color_picking)

        # Make the overlay focusable and grab focus
        self.color_picker_overlay.focus_set()
        self.color_picker_overlay.grab_set()  # Grab all input

        # Alternative: bind globally to the overlay
        # self.color_picker_overlay.bind_all("<Button-3>", self.cancel_color_picking)

    @logger.catch(level="DEBUG")
    def on_color_pick_click(self, event):
        """Handle mouse click to pick color from screen"""
        # Get absolute screen coordinates
        x = self.color_picker_overlay.winfo_pointerx()
        y = self.color_picker_overlay.winfo_pointery()

        # Hide overlay temporarily to get pixel color
        self.color_picker_overlay.withdraw()
        self.color_picker_overlay.update()

        try:
            # Get pixel color
            pixel_color = pyautogui.pixel(x, y)
            r, g, b = pixel_color

            # Update color info
            self.update_color_info_from_pick(r, g, b, x, y)
            logger.info(f"Color picked: {r}, {g}, {b}")

        except Exception as e:
            logger.error(f"Error picking color: {e}")
        finally:
            # Clean up and restore
            self.cleanup_color_picking()

    @logger.catch(level="DEBUG")
    def cancel_color_picking(self, event=None):
        """Cancel color picking process"""
        # Remove global bindings first
        try:
            if self.color_picker_overlay and self.color_picker_overlay.winfo_exists():
                self.color_picker_overlay.unbind_allcancel_color_picking
        except:
            pass

        self.cleanup_color_picking()
        logger.info("Color picking canceled")

    @logger.catch(level="DEBUG")
    def cleanup_color_picking(self):
        """Clean up color picking process"""
        self.is_picking_color = False

        # Destroy overlay and release grab
        if self.color_picker_overlay and self.color_picker_overlay.winfo_exists():
            try:
                self.color_picker_overlay.grab_release()  # Release input grab
            except:
                pass
            self.color_picker_overlay.destroy()
        self.color_picker_overlay = None

        # Restore main window
        if self.desktop_color_picker and self.desktop_color_picker.winfo_exists():
            self.desktop_color_picker.deiconify()
            self.desktop_color_picker.focus()

        # Restore UI
        if hasattr(self, 'pick_btn') and self.pick_btn.winfo_exists():
            self.pick_btn.configure(text="Start Picking", state="normal")
        if hasattr(self, 'status_label') and self.status_label.winfo_exists():
            self.status_label.configure(
                text="Click 'Start Picking' then click any pixel on your screen to get its color information\n\nPress right-click to cancel picking",
                text_color="silver")

    @logger.catch(level="DEBUG")
    def update_color_info_from_pick(self, r, g, b, x, y):
        """Update color information from picked color"""
        self.current_color = (r, g, b)
        # For screen picking, we assume full opacity since we can't detect transparency from screen
        self.current_alpha = 255

        self.updating_from_fields = True
        self.update_color_fields()
        self.move_cursor_to_color(r, g, b)
        self.updating_from_fields = False

        # Update status with ARGB
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        argb_hex = f"#{self.current_alpha:02x}{r:02x}{g:02x}{b:02x}"
        self.status_label.configure(text=f"Picked: {hex_color.upper()} (ARGB: {argb_hex.upper()}) at ({x}, {y})")

    @logger.catch(level="DEBUG")
    def on_color_wheel_click(self, event):
        """Handle mouse click on color wheel"""
        self.on_color_wheel_drag(event)

    @logger.catch(level="DEBUG")
    def on_color_wheel_drag(self, event):
        """Handle mouse drag on color wheel"""
        if self.updating_from_fields:
            return

        x = event.x
        y = event.y

        # Calculate distance from center
        center_x = center_y = self.image_dimension // 2
        d_from_center = math.sqrt((center_x - x) ** 2 + (center_y - y) ** 2)

        # Limit to circle boundary
        max_radius = self.image_dimension // 2 - 5
        if d_from_center < max_radius:
            self.target_x, self.target_y = x, y
        else:
            self.target_x, self.target_y = self.projection_on_circle(x, y, center_x, center_y, max_radius)

        # Redraw canvas
        self.redraw_color_canvas()

        # Get color and update fields
        self.updating_from_wheel = True
        self.get_target_color()
        self.update_color_fields()
        self.updating_from_wheel = False

    @logger.catch(level="DEBUG")
    def projection_on_circle(self, point_x, point_y, circle_x, circle_y, radius):
        """Project point onto circle boundary"""
        angle = math.atan2(point_y - circle_y, point_x - circle_x)
        projection_x = circle_x + radius * math.cos(angle)
        projection_y = circle_y + radius * math.sin(angle)
        return projection_x, projection_y

    @logger.catch(level="DEBUG")
    def redraw_color_canvas(self):
        """Redraw the color canvas with wheel and target"""
        self.color_canvas.delete("all")
        self.color_canvas.create_image(self.image_dimension / 2, self.image_dimension / 2, image=self.wheel_photo)
        self.color_canvas.create_image(self.target_x, self.target_y, image=self.target_photo)

    @logger.catch(level="DEBUG")
    def get_target_color(self):
        """Get color at target position"""
        try:
            pixel_color = self.color_wheel_image.getpixel((int(self.target_x), int(self.target_y)))
            if len(pixel_color) == 3:
                self.current_color = pixel_color
            elif len(pixel_color) == 4:
                self.current_color = pixel_color[:3]
            else:
                self.current_color = (255, 255, 255)
        except Exception as e:
            logger.error(f"Error getting target color: {e}")
            self.current_color = (255, 255, 255)

    @logger.catch(level="DEBUG")
    def on_hex_change(self, event):
        """Handle hex color change"""
        if self.updating_from_wheel:
            return

        try:
            hex_color = self.hex_entry.get()
            if not hex_color.startswith('#'):
                hex_color = '#' + hex_color

            # Validate hex color
            if len(hex_color) == 7:
                r = int(hex_color[1:3], 16)
                g = int(hex_color[3:5], 16)
                b = int(hex_color[5:7], 16)

                self.updating_from_fields = True
                self.update_from_rgb(r, g, b)
                self.updating_from_fields = False

        except ValueError:
            pass

    @logger.catch(level="DEBUG")
    def on_argb_change(self, event):
        """Handle ARGB value change"""
        if self.updating_from_wheel:
            return

        try:
            a = int(self.alpha_entry.get() or 255)
            r = int(self.argb_red_entry.get() or 0)
            g = int(self.argb_green_entry.get() or 0)
            b = int(self.argb_blue_entry.get() or 0)

            # Clamp values
            a = max(0, min(255, a))
            r = max(0, min(255, r))
            g = max(0, min(255, g))
            b = max(0, min(255, b))

            self.current_alpha = a
            self.updating_from_fields = True
            self.update_from_rgb(r, g, b)
            self.updating_from_fields = False

        except ValueError:
            pass

    @logger.catch(level="DEBUG")
    def on_hsv_change(self, event):
        """Handle HSV value change"""
        if self.updating_from_wheel:
            return

        try:
            h = float(self.hue_entry.get() or 0) / 360.0
            s = float(self.sat_entry.get() or 0) / 100.0
            v = float(self.val_entry.get() or 0) / 100.0

            # Clamp values
            h = max(0, min(1, h))
            s = max(0, min(1, s))
            v = max(0, min(1, v))

            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            r, g, b = int(r * 255), int(g * 255), int(b * 255)

            self.updating_from_fields = True
            self.update_from_rgb(r, g, b)
            self.updating_from_fields = False

        except ValueError:
            pass

    @logger.catch(level="DEBUG")
    def update_from_rgb(self, r, g, b):
        """Update cursor position and fields from RGB values"""
        self.current_color = (r, g, b)

        # Update cursor position on wheel
        self.move_cursor_to_color(r, g, b)

        # Update all fields
        self.update_color_fields()

    @logger.catch(level="DEBUG")
    def move_cursor_to_color(self, r, g, b):
        """Move cursor to approximate position for given RGB color"""
        # Convert RGB to HSV
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)

        # Calculate position on color wheel to match the generation logic
        center_x = center_y = self.image_dimension // 2
        max_radius = center_x - 10  # Leave some margin from edge
        radius = s * max_radius

        # Convert hue back to angle - this must match the color wheel generation
        angle = h * 2 * math.pi - math.pi  # Convert hue to angle in radians

        # Calculate target position - note the negative sin to match wheel generation
        self.target_x = center_x + radius * math.cos(angle)
        self.target_y = center_y - radius * math.sin(angle)  # Note the negative sign

        # Ensure target stays within bounds
        self.target_x = max(5, min(self.image_dimension - 5, self.target_x))
        self.target_y = max(5, min(self.image_dimension - 5, self.target_y))

        # Redraw canvas
        self.redraw_color_canvas()

    @logger.catch(level="DEBUG")
    def update_color_info(self, r, g, b):
        """Update color information from external source (desktop picker)"""
        self.updating_from_fields = True
        self.update_from_rgb(r, g, b)
        self.updating_from_fields = False

    @logger.catch(level="DEBUG")
    def copy_hex_to_clipboard(self):
        """Copy hex color to clipboard with proper exception handling"""
        try:
            hex_color = self.hex_entry.get()

            # Validate hex color format
            if not hex_color:
                raise ValueError("No hex color to copy")

            if not hex_color.startswith('#'):
                hex_color = '#' + hex_color

            # Validate hex format
            if len(hex_color) != 7:
                raise ValueError("Invalid hex color format")

            # Try to parse as hex to validate
            int(hex_color[1:], 16)

            # Copy to clipboard
            pyperclip.copy(hex_color)

            # Show success feedback
            original_text = self.copy_hex_btn.cget("text")
            self.copy_hex_btn.configure(text="Copied!")
            self.desktop_color_picker.after(1500, lambda: self.copy_hex_btn.configure(text=original_text))
            self.desktop_color_picker.after(1500, lambda: self.status_label.configure(
                text="Click 'Start Picking' then click any pixel on your screen to get its color information\n\nPress right-click to cancel picking",
                text_color="silver"))

            # Update status
            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"Copied {hex_color} to clipboard", text_color="green")

        except ValueError as e:
            logger.error(f"Invalid hex color format: {e}")
            # Show error feedback
            original_text = self.copy_hex_btn.cget("text")
            self.copy_hex_btn.configure(text="Invalid Color!")
            self.desktop_color_picker.after(1500, lambda: self.copy_hex_btn.configure(text=original_text))

            if hasattr(self, 'status_label'):
                self.status_label.configure(text="Error: Invalid hex color format", text_color="red")

        except Exception as e:
            logger.error(f"Error copying to clipboard: {e}")
            # Show error feedback
            original_text = self.copy_hex_btn.cget("text")
            self.copy_hex_btn.configure(text="Copy Failed!")
            self.desktop_color_picker.after(1500, lambda: self.copy_hex_btn.configure(text=original_text))

            if hasattr(self, 'status_label'):
                self.status_label.configure(text="Error: Failed to copy to clipboard", text_color="red")

    @logger.catch(level="DEBUG")
    def update_color_fields(self):
        """Update all color input fields"""
        # Ensure we have exactly 3 values
        if len(self.current_color) >= 3:
            r, g, b = self.current_color[:3]
        else:
            r, g, b = 255, 255, 255  # Default to white if something went wrong

        # Ensure we have alpha value
        if not hasattr(self, 'current_alpha'):
            self.current_alpha = 255

        # Update hex
        hex_color = f"#{r:02x}{g:02x}{b:02x}"
        self.hex_entry.delete(0, tk.END)
        self.hex_entry.insert(0, hex_color.upper())

        # Change hex entry background color
        self.hex_entry.configure(fg_color=hex_color)

        # Set text color based on brightness
        brightness = (r * 0.299 + g * 0.587 + b * 0.114)
        text_color = "white" if brightness < 128 else "black"
        self.hex_entry.configure(text_color=text_color)

        # Update HSV
        h, s, v = colorsys.rgb_to_hsv(r / 255.0, g / 255.0, b / 255.0)
        self.hue_entry.delete(0, tk.END)
        self.hue_entry.insert(0, str(int(h * 360)))
        self.sat_entry.delete(0, tk.END)
        self.sat_entry.insert(0, str(int(s * 100)))
        self.val_entry.delete(0, tk.END)
        self.val_entry.insert(0, str(int(v * 100)))

        # Update ARGB
        self.alpha_entry.delete(0, tk.END)
        self.alpha_entry.insert(0, str(self.current_alpha))
        self.argb_red_entry.delete(0, tk.END)
        self.argb_red_entry.insert(0, str(r))
        self.argb_green_entry.delete(0, tk.END)
        self.argb_green_entry.insert(0, str(g))
        self.argb_blue_entry.delete(0, tk.END)
        self.argb_blue_entry.insert(0, str(b))

    #  Method to get ARGB hex format
    @logger.catch(level="DEBUG")
    def get_argb_hex(self):
        """Get ARGB color in hex format"""
        if len(self.current_color) >= 3:
            r, g, b = self.current_color[:3]
        else:
            r, g, b = 255, 255, 255

        alpha = getattr(self, 'current_alpha', 255)
        return f"#{alpha:02x}{r:02x}{g:02x}{b:02x}".upper()

    # Method to get ARGB as integer
    @logger.catch(level="DEBUG")
    def get_argb_int(self):
        """Get ARGB color as integer"""
        if len(self.current_color) >= 3:
            r, g, b = self.current_color[:3]
        else:
            r, g, b = 255, 255, 255

        alpha = getattr(self, 'current_alpha', 255)
        return (alpha << 24) | (r << 16) | (g << 8) | b

    @logger.catch(level="DEBUG")
    def copy_argb_to_clipboard(self):
        """Copy ARGB color to clipboard in [A=255, R=102, G=204, B=255] format"""
        try:
            if len(self.current_color) >= 3:
                r, g, b = self.current_color[:3]
            else:
                r, g, b = 255, 255, 255

            alpha = getattr(self, 'current_alpha', 255)

            # Format as [A=255, R=102, G=204, B=255]
            argb_text = f"[A={alpha}, R={r}, G={g}, B={b}]"
            pyperclip.copy(argb_text)

            # Show success feedback
            original_text = self.copy_argb_btn.cget("text")
            self.copy_argb_btn.configure(text="ARGB Copied!")
            self.desktop_color_picker.after(1500, lambda: self.copy_argb_btn.configure(text=original_text))
            self.desktop_color_picker.after(1500, lambda: self.status_label.configure(
                text="Click 'Start Picking' then click any pixel on your screen to get its color information\n\nPress right-click to cancel picking",
                text_color="silver"))

            if hasattr(self, 'status_label'):
                self.status_label.configure(text=f"Copied {argb_text} to clipboard", text_color="green")

        except Exception as e:
            logger.error(f"Error copying ARGB to clipboard: {e}")
            # Show error feedback
            original_text = self.copy_argb_btn.cget("text")
            self.copy_argb_btn.configure(text="Copy Failed!")
            self.desktop_color_picker.after(1500, lambda: self.copy_argb_btn.configure(text=original_text))

            if hasattr(self, 'status_label'):
                self.status_label.configure(text="Error: Failed to copy ARGB to clipboard", text_color="red")

    def go_to_about(self):
        about_page = customtkinter.CTkToplevel()
        about_page.title("About")
        window_width = 1366
        window_height = 768

        # Center the window on the screen
        about_page.minsize(window_width, window_height)
        about_page.maxsize(window_width, window_height)

        about_page.update_idletasks()

        screen_width = about_page.winfo_screenwidth()
        screen_height = about_page.winfo_screenheight()
        x_cordinate = int((screen_width / 2) - (window_width / 2))
        y_cordinate = int((screen_height / 2) - (window_height / 2))

        about_page.geometry(
            "{}x{}+{}+{}".format(window_width, window_height, x_cordinate, y_cordinate))

        about_page.resizable(False, False)
        about_page.after(201, lambda: about_page.iconbitmap("./images/app_logo.ico"))

        uipath_logo_image = customtkinter.CTkImage(
            light_image=Image.open("./images/uipath_large_logo.png"),
            dark_image=Image.open("./images/uipath_large_logo.png"),
            size=(200, 100)  # Adjust size as needed (width, height)
        )

        # Create the image label
        uipath_name_label = customtkinter.CTkLabel(
            master=about_page,
            text="",  # Empty text
            image=uipath_logo_image
        )
        uipath_name_label.pack(pady=70)

        customtkinter.CTkLabel(master=about_page,
                               corner_radius=0,
                               font=('Arial', 20),
                               fg_color="transparent",
                               # bg_color=None,
                               text="OCRLing " + self.application_version,
                               text_color="silver").pack(pady=10)

        about_text = f"""An OCR (Optical Character Recognition) application with area selection and image processing capabilities.

        Built with CustomTkinter and Python 3.13.9

        Features:

        • Screen area selection
        • Image file processing  
        • QR Code processing  
        • Bar Code processing  
        • Desktop Color Picker
        • Text extraction using Tesseract OCR and Mistral AI OCR engines
        • Text translation using Google Translate ajax API (245 languages and maximum 54411 characters)
        • Export text functionality
        • System tray integration
        """
        customtkinter.CTkLabel(master=about_page,
                               corner_radius=0,
                               fg_color="transparent",
                               # bg_color=None,
                               text=about_text,
                               justify="left",
                               font=customtkinter.CTkFont(family="Arial", size=15, weight="normal"),
                               text_color="silver").pack(pady=40)

        def agreement_link_callback(event):
            webbrowser.open_new("https://www.uipath.com/legal/trust-and-security/legal-terms")

        agreement_link_label = customtkinter.CTkLabel(about_page,
                                                      font=('Arial', 10),
                                                      fg_color="transparent",
                                                      bg_color="transparent",
                                                      text="LICENSE AGREEMENT",
                                                      text_color="silver",
                                                      cursor="hand2")
        agreement_link_label.pack(side=tk.BOTTOM, pady=5)
        agreement_link_label.bind("<Button-1>", agreement_link_callback)

        customtkinter.CTkLabel(master=about_page,
                               corner_radius=0,
                               font=('Arial', 10),
                               fg_color="transparent",
                               # bg_color=None,
                               text='LEGAL NOTICE: By installing and using this software, you (individual or legal entity) agree to the applicable LICENSE AGREEMENT.\nPlease read it carefully. If you disagree with the license agreement, do not install or use the software and delete it from your computer.',
                               text_color="silver").pack(side=tk.BOTTOM, pady=10)

        todays_date = date.today()
        current_year = todays_date.year

        customtkinter.CTkLabel(master=about_page,
                               corner_radius=0,
                               font=('Arial', 12),
                               fg_color="transparent",
                               # bg_color=None,
                               text="Copyright © {current_year} - UiPath Support Team\nAll rights reserved.".format(
                                   current_year=current_year),
                               text_color="silver").pack(side=tk.BOTTOM, pady=5)

    def exit_application(self, icon=None, item=None):
        """Exit the application completely - Nuclear option for CustomTkinter"""
        with self._exit_lock:
            if self._is_exiting:
                return  # Already exiting, prevent multiple calls

            self._is_exiting = True

        try:
            logger.info("Application exit requested")

            # Stop system tray immediately to prevent callbacks
            if hasattr(self, 'icon') and self.icon:
                try:
                    self.icon.stop()
                except:
                    pass

            # Force quit the mainloop immediately - this stops all pending events
            if hasattr(self, 'root') and self.root:
                try:
                    self.root.quit()  # This exits mainloop immediately
                except:
                    pass

            # Small delay to let quit() take effect
            time.sleep(0.1)

            # Now destroy windows - but wrapped in individual try-catch
            windows = [
                ('ocr_window', getattr(self, 'ocr_window', None)),
                ('settings_page', getattr(self, 'settings_page', None)),
                ('win', getattr(self, 'win', None)),
                ('root', getattr(self, 'root', None))
            ]

            for name, window in windows:
                if window:
                    try:
                        window.destroy()
                    except:
                        pass  # Ignore any destroy errors
                    finally:
                        setattr(self, name, None)

            logger.info("Application exited successfully")

        except Exception as e:
            logger.error(f"Exit error: {e}")

        finally:
            # Force exit the process - no matter what happened above
            os._exit(0)

    def run_tray(self):
        """Run the system tray in a separate thread"""
        try:
            if self.icon and not self._is_exiting:
                self.icon.run()
        except Exception as e:
            if not self._is_exiting:
                logger.error(f"Tray error: {e}")

    def run(self):
        """Main application run method with better exit handling"""
        try:
            # Start system tray in separate thread
            tray_thread = threading.Thread(target=self.run_tray, daemon=True)
            tray_thread.start()

            # Run the main tkinter loop
            if self.root:
                self.root.mainloop()

            # If we get here, mainloop() has exited (probably via quit())
            # Don't call exit_application() again as it's likely already been called

        except KeyboardInterrupt:
            logger.info("Application interrupted by user")
            if not self._is_exiting:
                self.exit_application()
        except Exception as e:
            logger.error(f"Application error: {e}")
            if not self._is_exiting:
                self.exit_application()

    # Alternative approach - Add cleanup method to be called before destroying windows
    def cleanup_widgets(self):
        """Clean up widgets before destroying windows"""
        try:
            # Stop any running animations or periodic updates
            if hasattr(self, 'root') and self.root:
                # If you have any after() calls, store their IDs and cancel them
                # Example: if hasattr(self, 'update_job_id'): self.root.after_cancel(self.update_job_id)
                pass

            # Disable any widgets that might still be processing events
            for window in [self.root, self.win, self.settings_page, self.ocr_window]:
                if window:
                    try:
                        # Recursively disable all child widgets
                        def disable_children(widget):
                            try:
                                if hasattr(widget, 'configure'):
                                    widget.configure(state='disabled')
                            except:
                                pass
                            try:
                                for child in widget.winfo_children():
                                    disable_children(child)
                            except:
                                pass

                        disable_children(window)
                    except:
                        pass
        except Exception as e:
            logger.debug(f"Cleanup error: {e}")

    # Modified exit method using cleanup
    def setup_window_close_protocol(self):
        """Call this after creating your windows to set proper close protocols"""

        def on_closing():
            self.exit_application()

        def on_root_closing():
            """Special handler for root window - hide instead of exit"""
            logger.info("Root window close requested - hiding instead of exiting")
            if self.root:
                self.root.withdraw()

        # Set protocol for all windows
        if self.root:
            # Root window should hide, not exit (system tray app)
            self.root.protocol("WM_DELETE_WINDOW", on_root_closing)
        if self.win:
            self.win.protocol("WM_DELETE_WINDOW", on_closing)
        if self.settings_page:
            self.settings_page.protocol("WM_DELETE_WINDOW", on_closing)
        if self.ocr_window:
            self.ocr_window.protocol("WM_DELETE_WINDOW", on_closing)

    def setup_periodic_cleanup(self):
        """Optional: Set up periodic cleanup of dead widgets"""

        def cleanup_dead_widgets():
            if not self._is_exiting:
                try:
                    # This will run every 5 seconds and clean up any orphaned after() calls
                    if hasattr(self, 'root') and self.root:
                        # Check if root still exists
                        self.root.winfo_exists()
                        # Schedule next cleanup
                        self.root.after(5000, cleanup_dead_widgets)
                except:
                    # If root is dead, we're probably shutting down
                    pass

        if hasattr(self, 'root') and self.root:
            self.root.after(5000, cleanup_dead_widgets)

    # If you want an even more aggressive approach for stubborn cases:
    def nuclear_exit(self, icon=None, item=None):
        """Nuclear option - immediately terminate the process"""
        try:
            logger.info("Nuclear exit requested")

            # Stop tray
            if hasattr(self, 'icon') and self.icon:
                try:
                    self.icon.stop()
                except:
                    pass

            # Try to quit mainloop
            if hasattr(self, 'root') and self.root:
                try:
                    self.root.quit()
                except:
                    pass

        except:
            pass

        finally:
            # Immediate process termination
            os._exit(0)


if __name__ == "__main__":
    import signal

    app = OCRLingApp()


    # Handle Ctrl+C and other termination signals
    def signal_handler(signum, frame):
        logger.info("Signal received, exiting...")
        app.exit_application()


    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    app.run()