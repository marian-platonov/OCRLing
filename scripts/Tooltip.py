import tkinter as tk
from tkinter import *
import os
from PIL import Image, ImageTk

import customtkinter

CURRENT_PATH = os.path.dirname(os.path.realpath(__file__))
ICON_DIR = os.path.join(CURRENT_PATH, "..", "images")



ICON_PATH = {
    "close": (os.path.join(ICON_DIR, "close_black.png"), os.path.join(ICON_DIR, "close_white.png")),
    "images": list(os.path.join(ICON_DIR, f"image{i}.jpg") for i in range(1, 4)),
    "eye1": (os.path.join(ICON_DIR, "eye1_black.png"), os.path.join(ICON_DIR, "eye1_white.png")),
    "eye2": (os.path.join(ICON_DIR, "eye2_black.png"), os.path.join(ICON_DIR, "eye2_white.png")),
    "info": os.path.join(ICON_DIR, "info.png"),
    "warning": os.path.join(ICON_DIR, "warning.png"),
    "error": os.path.join(ICON_DIR, "error.png"),
    "left": os.path.join(ICON_DIR, "left.png"),
    "right": os.path.join(ICON_DIR, "right.png"),
    "warning2": os.path.join(ICON_DIR, "warning2.png"),
    "loader": os.path.join(ICON_DIR, "loader.gif"),
    "icon": os.path.join(ICON_DIR, "icon.png"),
    "arrow": os.path.join(ICON_DIR, "arrow.png"),
    "image": os.path.join(ICON_DIR, "image.png"),
}

DEFAULT_BTN = {
    "fg_color": "transparent",
    "hover": False,
    "compound": "left",
    "anchor": "w",
}

class CTkInput(customtkinter.CTkEntry):
    def __init__(self, master: any, icon_width=20, icon_height=20, **kwargs):
        super().__init__(master, **kwargs)

        self.icon_width = icon_width
        self.icon_height = icon_height

        self.is_hidden = False
        self.eye_btn = None

        self.warning = customtkinter.CTkImage(Image.open(ICON_PATH["warning2"]), Image.open(ICON_PATH["warning2"]),
                                    (self.icon_width, self.icon_height))
        self.eye1 = customtkinter.CTkImage(Image.open(ICON_PATH["eye1"][0]), Image.open(ICON_PATH["eye1"][1]),
                                 (self.icon_width, self.icon_height))
        self.eye2 = customtkinter.CTkImage(Image.open(ICON_PATH["eye2"][0]), Image.open(ICON_PATH["eye2"][1]),
                                 (self.icon_width, self.icon_height))

        self.button_bg = customtkinter.ThemeManager.theme["CTkEntry"]["fg_color"]
        self.border_color = customtkinter.ThemeManager.theme["CTkEntry"]["border_color"]

    def custom_input(self, icon_path, text=None, compound="right"):
        icon = customtkinter.CTkImage(Image.open(icon_path), Image.open(icon_path), (self.icon_width, self.icon_height))

        icon_label = customtkinter.CTkLabel(self, text=text if text else None, image=icon, width=self.icon_width,
                                  height=self.icon_height, compound=compound)
        icon_label.grid(row=0, column=0, padx=4, pady=0, sticky="e")

    def password_input(self):
        self.is_hidden = True
        self.configure(show="*")
        self.eye_btn = customtkinter.CTkButton(self, text="", width=self.icon_width, height=self.icon_height,
                                     fg_color=self.button_bg, hover=False, image=self.eye1,
                                     command=self.toggle_input)
        self.eye_btn.grid(row=0, column=0, padx=2, pady=0, sticky="e")

    def show_waring(self, border_color="red"):
        self.configure(border_color=border_color)
        icon_label = customtkinter.CTkLabel(self, text="", image=self.warning, width=self.icon_width, height=self.icon_height)
        icon_label.grid(row=0, column=0, padx=4, pady=0, sticky="e")

    def toggle_input(self):
        if self.is_hidden:
            self.is_hidden = False
            self.configure(show="")
            self.eye_btn.configure(image=self.eye2)
        else:
            self.is_hidden = True
            self.configure(show="*")
            self.eye_btn.configure(image=self.eye1)

    def reset_default(self):
        self.configure(border_color=self.border_color)
        self.configure(show="")
        self.is_hidden = False
        for widget in self.winfo_children():
            widget_name = widget.winfo_name()
            if widget_name.startswith("!ctklabel") or widget_name.startswith("!ctkbutton"):
                widget.destroy()



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
        label = tk.Label(self.tw,
                         text=self.text,
                         justify='left',
                         background="#ffffff",
                         relief='solid',
                         borderwidth=1,
                         wraplength=self.wraplength)
        label.pack(ipadx=1)

    def hidetip(self):
        tw = self.tw
        self.tw = None
        if tw:
            tw.destroy()


class Tooltip(object):
    '''
    create a tooltip for a given widget
    '''
    def __init__(self, widget, text='widget info', manual=False, delay=True):
        self.widget = widget
        self.text = text
        self.delay = delay
        self.wraplength = 580

        self.tw = None

        self.manual = manual

        if not manual:
            self.widget.bind("<Enter>", self.enter)
            self.widget.bind("<Leave>", self.close)

    def enter(self, event=None):
        # if self.delay:
        #     self.widget.winfo_toplevel().after(600, self.create)
        # else:
        #     self.create()
        # else:
        #     self.close()

        self.create()

    def create(self):
        x = y = 0
        x, y, cx, cy = self.widget.bbox("insert")

        if self.manual:
            x += self.widget.winfo_rootx() - 1
            y += self.widget.winfo_rooty() + 20
        else:
            x += self.widget.winfo_rootx() + 25
            y += self.widget.winfo_rooty() + 30

        # creates a toplevel window
        self.tw = tk.Toplevel(self.widget)
        # Leaves only the label and removes the app window
        self.tw.wm_overrideredirect(True)
        self.tw.wm_geometry("+%d+%d" % (x, y))
        label = tk.Label(self.tw, text=self.text, justify='left',
                       relief='solid', borderwidth=1, wraplength=self.wraplength,
                       font=("Helvetica", "8", "normal"))

        label.pack(ipadx=1)

    def close(self, *args):

        if self.tw:
            self.tw.destroy()
            self.tw = None
