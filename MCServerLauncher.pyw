"""MC Server Launcher - หน้าต่างหลัก

เปิดเซิร์ฟเวอร์ Minecraft modpack จาก CurseForge ในคลิ๊กเดียว
"""
from __future__ import annotations

import os
import queue
import re
import sys
import threading
import time
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent))

from launcher import instances as inst_mod                      # noqa: E402
from launcher import autoheal, dnd, sync, tunnel                # noqa: E402
from launcher.config import (APP_DIR, APP_NAME, APP_VERSION,  # noqa: E402
                             LOGS_DIR, SERVERS_DIR, PackSettings, Settings,
                             ensure_dirs)
from launcher.session import Session                            # noqa: E402

BG = "#1b1d23"
PANEL = "#24272f"
FG = "#e6e8ee"
MUTED = "#9aa0ad"
ACCENT = "#4ea36a"
DANGER = "#c9524b"
CONSOLE_BG = "#131519"

# Where people can reach the developer. Kept together so there is one place to
# change if a link ever moves.
CONTACT_LINKS = [
    ("โพสต์แนะนำโปรแกรม (Facebook)",
     "https://www.facebook.com/share/p/19eToA261T/"),
    ("ทักผู้พัฒนา (Facebook)",
     "https://www.facebook.com/doxx.ing.2025/?locale=th_TH"),
    ("แจ้งปัญหาบน GitHub",
     "https://github.com/BrefGhost/MCServerLauncher/issues"),
]
FONT = ("Leelawadee UI", 10)
FONT_BOLD = ("Leelawadee UI", 10, "bold")
FONT_TITLE = ("Leelawadee UI", 15, "bold")
FONT_MONO = ("Cascadia Mono", 9)

DIFFICULTIES = [("peaceful", "สงบ"), ("easy", "ง่าย"),
                ("normal", "ปกติ"), ("hard", "ยาก")]
NL = "\n"                      # keeps the hint texts below readable


class Hint(tk.Label):
    """A small "?" badge that explains a setting on hover.

    Every option here decides something about a Minecraft server, which is
    exactly the knowledge this launcher exists to spare people - so the
    explanation has to be one hover away, not in a manual.
    """

    def __init__(self, parent, text: str) -> None:
        super().__init__(parent, text=" ? ", bg="#3a4150", fg="#cdd3e0",
                         font=("Leelawadee UI", 8, "bold"), cursor="question_arrow")
        self.text = text
        self._tip: tk.Toplevel | None = None
        self.bind("<Enter>", self._show)
        self.bind("<Leave>", self._hide)

    def _show(self, _event=None) -> None:
        if self._tip is not None:
            return
        self.configure(bg=ACCENT, fg="#0d1410")
        tip = tk.Toplevel(self)
        tip.wm_overrideredirect(True)
        tip.attributes("-topmost", True)
        tk.Label(tip, text=self.text, justify="left", wraplength=330,
                 bg="#11141a", fg=FG, font=FONT, relief="solid", bd=1,
                 padx=10, pady=8).pack()
        tip.update_idletasks()
        x = self.winfo_rootx() + 18
        y = self.winfo_rooty() + self.winfo_height() + 6
        # keep the bubble on screen when the badge sits near the bottom edge
        if y + tip.winfo_height() > self.winfo_screenheight():
            y = self.winfo_rooty() - tip.winfo_height() - 6
        tip.wm_geometry(f"+{x}+{y}")
        self._tip = tip

    def _hide(self, _event=None) -> None:
        self.configure(bg="#3a4150", fg="#cdd3e0")
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


class App(dnd.tk_base()):
    def __init__(self) -> None:
        super().__init__()
        ensure_dirs()
        self.title(f"{APP_NAME} {APP_VERSION}")
        self._set_icon()
        self.geometry("1060x720")
        self.minsize(940, 620)
        self.configure(bg=BG)

        self.settings = Settings.load()
        self.instances: list[inst_mod.Instance] = []
        self.session: Session | None = None
        self.events: queue.Queue = queue.Queue()
        self.address = ""

        self._build_style()
        self._build_ui()
        self._enable_drop()
        self.refresh_instances()
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        self.after(80, self._drain_events)

    def _set_icon(self) -> None:
        """PyInstaller unpacks data next to the exe, so look in both places."""
        for base in (Path(getattr(sys, "_MEIPASS", "")), Path(__file__).parent):
            ico = base / "assets" / "icon.ico"
            if ico.is_file():
                try:
                    self.iconbitmap(default=str(ico))
                    return
                except Exception:
                    pass

    # --------------------------------------------------------------- styling
    def _build_style(self) -> None:
        st = ttk.Style(self)
        st.theme_use("clam")
        st.configure(".", background=BG, foreground=FG, font=FONT,
                     fieldbackground=PANEL, bordercolor="#333743")
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=FG, font=FONT)
        st.configure("Panel.TLabel", background=PANEL, foreground=FG)
        st.configure("Muted.TLabel", background=BG, foreground=MUTED)
        st.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED)
        st.configure("Title.TLabel", background=BG, foreground=FG, font=FONT_TITLE)
        st.configure("TCheckbutton", background=PANEL, foreground=FG, font=FONT)
        st.map("TCheckbutton", background=[("active", PANEL)])
        st.configure("TButton", background="#333743", foreground=FG,
                     borderwidth=0, padding=(12, 7), font=FONT)
        st.map("TButton", background=[("active", "#3d4250")])
        st.configure("Go.TButton", background=ACCENT, foreground="#0d1410",
                     font=("Leelawadee UI", 13, "bold"), padding=(16, 14))
        st.map("Go.TButton", background=[("active", "#5cb87a"),
                                         ("disabled", "#3a4740")])
        st.configure("Stop.TButton", background=DANGER, foreground="#fff",
                     font=("Leelawadee UI", 13, "bold"), padding=(16, 14))
        st.map("Stop.TButton", background=[("active", "#d9635c")])
        st.configure("TCombobox", fieldbackground=PANEL, background=PANEL,
                     foreground=FG, arrowcolor=FG)
        st.configure("TSpinbox", fieldbackground=PANEL, foreground=FG,
                     arrowcolor=FG)
        st.configure("TEntry", fieldbackground=PANEL, foreground=FG,
                     insertcolor=FG)
        st.configure("Horizontal.TProgressbar", background=ACCENT,
                     troughcolor=PANEL, borderwidth=0)

    # -------------------------------------------------------------------- UI
    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)
        root.columnconfigure(0, weight=0, minsize=320)
        root.columnconfigure(1, weight=1)
        root.rowconfigure(1, weight=1)

        header = ttk.Frame(root)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 12))
        ttk.Label(header, text="เปิดเซิร์ฟเวอร์ Minecraft", style="Title.TLabel").pack(side="left")
        ttk.Button(header, text="โฟลเดอร์เซิร์ฟเวอร์", command=self.open_server_folder).pack(side="right")
        ttk.Button(header, text="สแกนใหม่", command=self.refresh_instances).pack(side="right", padx=6)
        ttk.Button(header, text="เพิ่มโฟลเดอร์…",
                   command=self.add_instance_folder).pack(side="right", padx=6)
        ttk.Button(header, text="คู่มือ",
                   command=self.open_manual).pack(side="right", padx=6)
        ttk.Button(header, text="ฟีดแบ็ก",
                   command=self.open_feedback).pack(side="right")

        self._build_left(root)
        self._build_right(root)

    def _build_left(self, root: ttk.Frame) -> None:
        left = ttk.Frame(root, style="Panel.TFrame", padding=14)
        left.grid(row=1, column=0, sticky="nsew", padx=(0, 12))
        left.columnconfigure(0, weight=1)
        r = 0

        def label(text: str, hint: str = "") -> None:
            nonlocal r
            row = ttk.Frame(left, style="Panel.TFrame")
            row.grid(row=r, column=0, sticky="ew", pady=(10, 2))
            ttk.Label(row, text=text, style="PanelMuted.TLabel").pack(side="left")
            if hint:
                Hint(row, hint).pack(side="left", padx=(6, 0))
            r += 1

        self.drop_zone = tk.Label(
            left, text="⤓  ลากโฟลเดอร์ modpack มาวางตรงนี้",
            bg="#2b303a", fg=MUTED, font=FONT, relief="flat",
            padx=10, pady=16, cursor="hand2")
        self.drop_zone.grid(row=r, column=0, sticky="ew", pady=(0, 4)); r += 1
        self.drop_zone.bind("<Button-1>", lambda e: self.add_instance_folder())

        label("modpack", """modpack ที่จะเปิดเป็นเซิร์ฟเวอร์

โปรแกรมสแกนโฟลเดอร์ของ CurseForge ให้เองอยู่แล้ว ถ้าแพ็คอยู่ที่อื่น ให้ลากโฟลเดอร์นั้นมาวางในหน้าต่างนี้ได้เลย

เซิร์ฟเวอร์กับเกมต้องเป็นแพ็คเวอร์ชันเดียวกัน ถ้าอัปเดตแพ็คในเกมแล้ว ให้กดเริ่มเซิร์ฟเวอร์ใหม่ โปรแกรมจะซิงก์ให้เอง""")
        self.pack_var = tk.StringVar()
        self.pack_combo = ttk.Combobox(left, textvariable=self.pack_var,
                                       state="readonly", font=FONT)
        self.pack_combo.grid(row=r, column=0, sticky="ew"); r += 1
        self.pack_combo.bind("<<ComboboxSelected>>", self.on_pack_changed)

        self.pack_info = ttk.Label(left, text="", style="PanelMuted.TLabel",
                                   wraplength=290, justify="left")
        self.pack_info.grid(row=r, column=0, sticky="ew", pady=(6, 0)); r += 1

        label("แรมที่ให้เซิร์ฟเวอร์ (GB)", """แรมที่กันไว้ให้เซิร์ฟเวอร์

แพ็คใหญ่ (200 ม็อดขึ้นไป) ควรให้ 8 GB ขึ้นไป

ถ้าจะเล่นเกมบนเครื่องเดียวกันด้วย อย่าให้เกินครึ่งหนึ่งของแรมทั้งเครื่อง เพราะตัวเกมเองก็กินหลาย GB — ให้มากเกินจะทำให้ทั้งเกมและเซิร์ฟช้าลงพร้อมกัน""")
        self.ram_var = tk.IntVar(value=8)
        ram_row = ttk.Frame(left, style="Panel.TFrame")
        ram_row.grid(row=r, column=0, sticky="ew"); r += 1
        ram_row.columnconfigure(0, weight=1)
        self.ram_scale = ttk.Scale(ram_row, from_=2, to=self._max_ram(),
                                   variable=self.ram_var, orient="horizontal",
                                   command=lambda v: self.ram_label.config(
                                       text=f"{int(float(v))} GB"))
        self.ram_scale.grid(row=0, column=0, sticky="ew")
        self.ram_label = ttk.Label(ram_row, text="8 GB", style="Panel.TLabel", width=6)
        self.ram_label.grid(row=0, column=1, padx=(8, 0))

        label("จำนวนผู้เล่นสูงสุด", """จำนวนคนที่เข้าเซิร์ฟเวอร์พร้อมกันได้""")
        self.players_var = tk.IntVar(value=8)
        ttk.Spinbox(left, from_=1, to=100, textvariable=self.players_var,
                    width=8).grid(row=r, column=0, sticky="w"); r += 1

        label("ความยาก", """ความยากของโลก

สงบ = ไม่มีมอนสเตอร์และไม่หิว
ง่าย / ปกติ / ยาก = มอนสเตอร์แรงขึ้นตามลำดับ

เปลี่ยนทีหลังได้ตลอด มีผลกับโลกที่มีอยู่แล้วด้วย""")
        self.diff_var = tk.StringVar(value="ปกติ")
        ttk.Combobox(left, textvariable=self.diff_var, state="readonly",
                     values=[t for _, t in DIFFICULTIES]).grid(
            row=r, column=0, sticky="ew"); r += 1

        label("ข้อความหน้าเซิร์ฟ (MOTD)", """ข้อความที่เพื่อนเห็นใต้ชื่อเซิร์ฟเวอร์ ในหน้ารายชื่อเซิร์ฟเวอร์ของเกม""")
        self.motd_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.motd_var).grid(
            row=r, column=0, sticky="ew"); r += 1

        label("แอดมิน (ชื่อผู้เล่น คั่นด้วยเว้นวรรค)", """ชื่อผู้เล่นที่จะได้สิทธิ์แอดมิน (op) — ใช้คำสั่งอย่าง /gamemode /tp /give ได้

ใส่ชื่อในเกมของคุณเองไว้ด้วย ไม่งั้นจะไม่มีใครสั่งอะไรได้เลย ใส่หลายคนได้โดยเว้นวรรค""")
        self.ops_var = tk.StringVar()
        ttk.Entry(left, textvariable=self.ops_var).grid(
            row=r, column=0, sticky="ew"); r += 1

        label("โลก", """จะสร้างโลกใหม่ หรือเอาโลกที่เคยเล่นคนเดียวมาเปิดเป็นเซิร์ฟเวอร์ก็ได้

โปรแกรมจะคัดลอกโลกนั้นมา ไม่ได้ย้ายไฟล์ต้นฉบับ โลกเดิมในเกมยังอยู่ครบ""")
        self.world_var = tk.StringVar(value="สร้างโลกใหม่")
        self.world_combo = ttk.Combobox(left, textvariable=self.world_var,
                                        state="readonly", values=["สร้างโลกใหม่"])
        self.world_combo.grid(row=r, column=0, sticky="ew"); r += 1

        self.tunnel_var = tk.BooleanVar(value=True)
        tunnel_row = ttk.Frame(left, style="Panel.TFrame")
        tunnel_row.grid(row=r, column=0, sticky="w", pady=(12, 0)); r += 1
        ttk.Checkbutton(tunnel_row, text="ให้เพื่อนต่อจากข้างนอกได้ (playit.gg)",
                        variable=self.tunnel_var).pack(side="left")
        Hint(tunnel_row, "เปิดช่องทางให้คนนอกบ้านต่อเข้าเซิร์ฟเวอร์ได้"
             + NL + NL +
             "เน็ตบ้านส่วนใหญ่ต่อตรงจากข้างนอกไม่ได้ โปรแกรมเลยใช้ playit.gg "
             "เป็นทางผ่านให้ ไม่ต้องตั้งค่า router อะไรเลย"
             + NL + NL +
             "ถ้าปิดอันนี้ จะเล่นได้เฉพาะคนที่ต่อ Wi-Fi เดียวกันเท่านั้น"
             ).pack(side="left", padx=(6, 0))

        self.online_var = tk.BooleanVar(value=True)
        online_row = ttk.Frame(left, style="Panel.TFrame")
        online_row.grid(row=r, column=0, sticky="w"); r += 1
        ttk.Checkbutton(online_row, text="ต้องเป็นบัญชี Minecraft แท้",
                        variable=self.online_var).pack(side="left")
        Hint(online_row, "ตรวจกับ Mojang ว่าคนที่เข้ามาเป็นเจ้าของบัญชีจริง"
             + NL + NL +
             "แนะนำให้เปิดไว้ ถ้าปิด ใครก็ตั้งชื่อเป็นใครก็ได้แล้วเข้ามาได้เลย "
             "รวมถึงสวมชื่อคุณเองด้วย"
             ).pack(side="left", padx=(6, 0))

        self.eula_var = tk.BooleanVar(value=self.settings.eula_accepted)
        eula_row = ttk.Frame(left, style="Panel.TFrame")
        eula_row.grid(row=r, column=0, sticky="w", pady=(4, 0)); r += 1
        ttk.Checkbutton(eula_row, text="ยอมรับ", variable=self.eula_var,
                        command=self.on_eula).pack(side="left")
        eula_link = tk.Label(eula_row, text="Minecraft EULA", bg=PANEL, fg="#7aa7ff",
                             cursor="hand2", font=FONT)
        eula_link.pack(side="left")
        eula_link.bind("<Button-1>",
                       lambda e: webbrowser.open("https://aka.ms/MinecraftEULA"))

        ttk.Label(left, text="ม็อดที่เซิร์ฟเวอร์ขาด", style="PanelMuted.TLabel").grid(
            row=r, column=0, sticky="w", pady=(14, 0)); r += 1
        ttk.Label(left, text="ถ้าเข้าเกมแล้วขึ้น mismatched mod channel list "
                             "ให้พิมพ์ชื่อม็อดที่หน้าจอบอก แล้วกดเพิ่ม",
                  style="PanelMuted.TLabel", wraplength=290,
                  justify="left").grid(row=r, column=0, sticky="w"); r += 1
        self.missing_var = tk.StringVar()
        missing_row = ttk.Frame(left, style="Panel.TFrame")
        missing_row.grid(row=r, column=0, sticky="ew", pady=(4, 0)); r += 1
        missing_row.columnconfigure(0, weight=1)
        missing_entry = ttk.Entry(missing_row, textvariable=self.missing_var)
        missing_entry.grid(row=0, column=0, sticky="ew")
        missing_entry.bind("<Return>", lambda e: self.add_missing_mods())
        ttk.Button(missing_row, text="เพิ่ม",
                   command=self.add_missing_mods).grid(row=0, column=1, padx=(6, 0))

        left.rowconfigure(r, weight=1)
        r += 1
        ttk.Button(left, text="ล้างม็อดที่ถูกปิดอัตโนมัติ",
                   command=self.reset_disabled).grid(row=r, column=0, sticky="ew")

    def _build_right(self, root: ttk.Frame) -> None:
        right = ttk.Frame(root)
        right.grid(row=1, column=1, sticky="nsew")
        right.columnconfigure(0, weight=1)
        right.rowconfigure(3, weight=1)

        top = ttk.Frame(right, style="Panel.TFrame", padding=14)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        self.go_btn = ttk.Button(top, text="▶  เริ่มเซิร์ฟเวอร์", style="Go.TButton",
                                 command=self.on_go)
        self.go_btn.grid(row=0, column=0, rowspan=2, sticky="nsw", padx=(0, 14))

        self.status_var = tk.StringVar(value="พร้อมเริ่ม")
        ttk.Label(top, textvariable=self.status_var, style="Panel.TLabel",
                  font=FONT_BOLD).grid(row=0, column=1, sticky="w")
        self.progress = ttk.Progressbar(top, mode="indeterminate")
        self.progress.grid(row=1, column=1, sticky="ew", pady=(6, 0))

        addr = ttk.Frame(right, style="Panel.TFrame", padding=(14, 10))
        addr.grid(row=1, column=0, sticky="ew", pady=(10, 0))
        addr.columnconfigure(1, weight=1)
        addr_label = ttk.Frame(addr, style="Panel.TFrame")
        addr_label.grid(row=0, column=0, padx=(0, 10))
        ttk.Label(addr_label, text="ที่อยู่เซิร์ฟเวอร์",
                  style="PanelMuted.TLabel").pack(side="left")
        Hint(addr_label, "ที่อยู่ที่ส่งให้เพื่อนเอาไปใส่ในเกม"
             + NL + NL +
             "ในเกมกด Multiplayer แล้ว Add Server แล้ววางที่อยู่นี้ลงช่อง "
             "Server Address"
             + NL + NL +
             "ที่อยู่นี้เปลี่ยนได้ทุกครั้งที่เปิดเซิร์ฟใหม่ ส่งอันล่าสุดให้เพื่อนเสมอ"
             ).pack(side="left", padx=(6, 0))
        self.addr_var = tk.StringVar()
        addr_entry = ttk.Entry(addr, textvariable=self.addr_var,
                               font=("Cascadia Mono", 11))
        addr_entry.grid(row=0, column=1, sticky="ew")
        addr_entry.bind("<FocusOut>", lambda e: self.save_address())
        addr_entry.bind("<Return>", lambda e: self.save_address())
        ttk.Button(addr, text="ก๊อป", command=self.copy_address).grid(
            row=0, column=2, padx=(8, 0))
        self.link_btn = ttk.Button(addr, text="เชื่อมบัญชี playit.gg",
                                   command=self.link_playit)
        self.link_btn.grid(row=0, column=3, padx=(6, 0))
        ttk.Label(addr, text="โปรแกรมดึงที่อยู่มาให้เองตอนเปิดเซิร์ฟ "
                             "(พิมพ์ทับได้ถ้าอยากใช้ที่อยู่อื่น)",
                  style="PanelMuted.TLabel").grid(row=1, column=1, columnspan=3,
                                                  sticky="w", pady=(4, 0))

        self.players_var_txt = tk.StringVar(value="ยังไม่มีใครออนไลน์")
        ttk.Label(right, textvariable=self.players_var_txt,
                  style="Muted.TLabel").grid(row=2, column=0, sticky="w", pady=(8, 4))

        console_wrap = ttk.Frame(right)
        console_wrap.grid(row=3, column=0, sticky="nsew")
        console_wrap.rowconfigure(0, weight=1)
        console_wrap.columnconfigure(0, weight=1)
        self.console = tk.Text(console_wrap, bg=CONSOLE_BG, fg="#cfd4de",
                               insertbackground=FG, font=FONT_MONO, wrap="word",
                               relief="flat", padx=10, pady=8, state="disabled")
        self.console.grid(row=0, column=0, sticky="nsew")
        bar = ttk.Scrollbar(console_wrap, command=self.console.yview)
        bar.grid(row=0, column=1, sticky="ns")
        self.console.configure(yscrollcommand=bar.set)
        self.console.tag_configure("warn", foreground="#e0b155")
        self.console.tag_configure("err", foreground="#e8756c")
        self.console.tag_configure("ok", foreground="#6fc98a")
        self.console.tag_configure("sys", foreground="#7aa7ff")

        where = ttk.Frame(right)
        where.grid(row=4, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(where, text="เซิร์ฟเวอร์และโลกเก็บไว้ที่",
                  style="Muted.TLabel").pack(side="left")
        location = tk.Label(where, text=str(APP_DIR), bg=BG, fg="#7aa7ff",
                            cursor="hand2", font=FONT)
        location.pack(side="left", padx=(6, 0))
        location.bind("<Button-1>", lambda e: self.open_data_folder())
        Hint(where, "ทุกอย่างที่โปรแกรมสร้างขึ้นอยู่ในโฟลเดอร์นี้"
             + NL + NL +
             "ถ้าเปิดโปรแกรมจากโฟลเดอร์ Downloads หรือหน้า Desktop โปรแกรมจะไม่ทิ้งไฟล์"
             "ไว้ปนกับของคุณ แต่จะสร้างโฟลเดอร์ของตัวเองไว้ใน Documents แทน"
             + NL + NL +
             "ถ้าอยากเก็บไว้ที่อื่น ให้ย้ายไฟล์ .exe ไปไว้ในโฟลเดอร์ว่าง ๆ "
             "ที่ต้องการแล้วเปิดจากตรงนั้น"
             ).pack(side="left", padx=(6, 0))

        cmd = ttk.Frame(right)
        cmd.grid(row=5, column=0, sticky="ew", pady=(8, 0))
        cmd.columnconfigure(0, weight=1)
        self.cmd_var = tk.StringVar()
        entry = ttk.Entry(cmd, textvariable=self.cmd_var, font=FONT_MONO)
        entry.grid(row=0, column=0, sticky="ew")
        entry.bind("<Return>", lambda e: self.send_command())
        ttk.Button(cmd, text="ส่งคำสั่ง", command=self.send_command).grid(
            row=0, column=1, padx=(8, 0))

    # ----------------------------------------------------------------- state
    def _max_ram(self) -> int:
        try:
            import ctypes

            class MemStatus(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong),
                            ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong),
                            ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong),
                            ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong),
                            ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]

            st = MemStatus()
            st.dwLength = ctypes.sizeof(MemStatus)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(st))
            total_gb = int(st.ullTotalPhys / (1024 ** 3))
            return max(4, total_gb - 4)      # leave headroom for Windows
        except Exception:
            return 16

    def current_instance(self) -> inst_mod.Instance | None:
        name = self.pack_var.get()
        return next((i for i in self.instances if i.name == name), None)

    def refresh_instances(self) -> None:
        self.instances = inst_mod.scan(self.settings.instance_dirs)
        names = [i.name for i in self.instances]
        self.pack_combo["values"] = names
        if not names:
            self.log("ไม่พบ modpack เลย — เปิด CurseForge แล้วติดตั้ง modpack สักตัวก่อน", "warn")
            return
        pick = self.settings.last_pack if self.settings.last_pack in names else names[0]
        self.pack_var.set(pick)
        self.on_pack_changed()
        self.log(f"เจอ modpack {len(names)} ตัว", "sys")

    def on_pack_changed(self, _event=None) -> None:
        inst = self.current_instance()
        if not inst:
            return
        self.pack_info.config(
            text=f"Minecraft {inst.mc_version} · {inst.loader_label} · "
                 f"ม็อด {inst.mods_count} ตัว")
        ps = self.settings.pack(inst.name)
        if inst.recommended_ram and inst.name not in self.settings.packs:
            ps.ram_gb = max(4, min(self._max_ram(),
                                   round(inst.recommended_ram / 1024)))
        self.ram_var.set(ps.ram_gb)
        self.ram_label.config(text=f"{ps.ram_gb} GB")
        self.players_var.set(ps.max_players)
        self.diff_var.set(dict(DIFFICULTIES).get(ps.difficulty, "ปกติ"))
        self.motd_var.set(ps.motd or f"{inst.name}")
        self.ops_var.set(" ".join(ps.ops))
        self.tunnel_var.set(ps.use_tunnel)
        self.online_var.set(ps.online_mode)
        self.address = ps.tunnel_address
        self.addr_var.set(ps.tunnel_address)

        worlds = sync.list_worlds(inst.path)
        self.world_combo["values"] = ["สร้างโลกใหม่"] + worlds
        self.world_var.set("สร้างโลกใหม่")

        self.settings.last_pack = inst.name
        self.settings.save()

    def collect_settings(self) -> PackSettings:
        ps = PackSettings()
        ps.ram_gb = int(self.ram_var.get())
        ps.max_players = int(self.players_var.get())
        ps.difficulty = next((k for k, t in DIFFICULTIES if t == self.diff_var.get()),
                             "normal")
        ps.motd = self.motd_var.get().strip()
        ps.ops = [o for o in self.ops_var.get().split() if o]
        ps.use_tunnel = bool(self.tunnel_var.get())
        ps.online_mode = bool(self.online_var.get())
        ps.tunnel_address = self.addr_var.get().strip()
        return ps

    # --------------------------------------------------------------- actions
    def on_eula(self) -> None:
        self.settings.eula_accepted = bool(self.eula_var.get())
        self.settings.save()

    def on_go(self) -> None:
        if self.session and self.session.running:
            self.stop_server()
        else:
            self.start_server()

    def start_server(self) -> None:
        inst = self.current_instance()
        if not inst:
            messagebox.showwarning(APP_NAME, "ยังไม่ได้เลือก modpack")
            return
        if not self.eula_var.get():
            messagebox.showwarning(
                APP_NAME, "ต้องติ๊กยอมรับ Minecraft EULA ก่อนถึงจะเปิดเซิร์ฟเวอร์ได้")
            return

        ps = self.collect_settings()
        self.settings.set_pack(inst.name, ps)
        self.settings.eula_accepted = True
        self.settings.save()

        world = self.world_var.get()
        if world and world != "สร้างโลกใหม่":
            try:
                sync.copy_world(inst.path, SERVERS_DIR / inst.slug, world, self.log)
            except Exception as exc:
                messagebox.showerror(APP_NAME, str(exc))
                return

        # Never leave the previous run's address on screen: it would be copied
        # and handed out while the server it points at is gone.
        self.address = ""
        self.addr_var.set("กำลังรอ …")
        self.progress.start(14)
        self.go_btn.config(text="■  หยุดเซิร์ฟเวอร์", style="Stop.TButton")

        self.session = Session(
            instance=inst, settings=ps, eula_accepted=True,
            on_log=lambda line: self.events.put(("log", line)),
            on_status=lambda s: self.events.put(("status", s)),
            on_state=lambda s: self.events.put(("state", s)),
            on_address=lambda a: self.events.put(("addr", a)),
            on_players=lambda p: self.events.put(("players", p)))
        self.session.start()

    def stop_server(self) -> None:
        if not self.session:
            return
        self.status_var.set("กำลังปิดเซิร์ฟเวอร์ (เซฟโลกอยู่) …")
        self.go_btn.config(state="disabled")
        self.session.request_stop()

    def send_command(self) -> None:
        text = self.cmd_var.get().strip()
        if not text or not self.session:
            return
        try:
            self.session.send(text)
            self.log(f"> {text}", "sys")
            self.cmd_var.set("")
        except Exception as exc:
            self.log(f"ส่งคำสั่งไม่ได้: {exc}", "err")

    def save_address(self) -> None:
        """Remember the address the user pasted from playit.gg."""
        inst = self.current_instance()
        text = self.addr_var.get().strip()
        if not inst or text == self.address:
            return
        self.address = text
        ps = self.settings.pack(inst.name)
        ps.tunnel_address = text
        self.settings.set_pack(inst.name, ps)
        self.settings.save()
        if text:
            self.log(f"จำที่อยู่ {text} ไว้แล้ว", "ok")

    def link_playit(self) -> None:
        """Link (or re-link) the playit.gg account without starting a server.

        The link can break at any time - the agent gets deleted on the website,
        or its key is reset - and the only sign used to be a wall of
        "401 Unauthorized" with nothing the user could press.
        """
        if self.session and self.session.running:
            messagebox.showinfo(
                APP_NAME, "กำลังเปิดเซิร์ฟเวอร์อยู่ — กดหยุดก่อนแล้วค่อยเชื่อมบัญชีใหม่")
            return
        if tunnel.has_secret() and not messagebox.askyesno(
                APP_NAME,
                "ตอนนี้เชื่อมบัญชี playit.gg ไว้แล้ว" + NL + NL
                + "จะเลิกใช้บัญชีเดิมแล้วเชื่อมใหม่ไหม?" + NL
                + "(ที่อยู่เซิร์ฟเวอร์จะเปลี่ยน ต้องส่งอันใหม่ให้เพื่อน)"):
            return

        self.link_btn.config(state="disabled")
        self.status_var.set("กำลังเชื่อมบัญชี playit.gg …")
        self.log("กำลังเชื่อมบัญชี playit.gg — จะเปิดหน้าเว็บให้กดยืนยัน", "sys")

        def work() -> None:
            agent = None
            try:
                tunnel.forget_account()
                agent = tunnel.PlayitAgent(
                    on_log=lambda line: self.events.put(("log", line)),
                    on_claim=lambda url: self.events.put(("claim", url)),
                    on_tunnels=lambda n: self.events.put(("linked", n)))
                agent.start(progress=lambda msg, pct:
                            self.events.put(("status", msg)))
                # The agent prints the claim link, waits for approval, then
                # writes the key itself. Five minutes is far longer than
                # pressing one button on a web page takes.
                for _ in range(300):
                    if tunnel.has_secret():
                        break
                    time.sleep(1.0)
                if tunnel.has_secret():
                    self.events.put(("status", "เชื่อมบัญชี playit.gg เรียบร้อย"))
                    self.events.put(("log", "เชื่อมบัญชี playit.gg เรียบร้อย "
                                            "กดเริ่มเซิร์ฟเวอร์ได้เลย"))
                else:
                    self.events.put(("status", "ยังไม่ได้เชื่อมบัญชี"))
            except Exception as exc:
                self.events.put(("log", f"[playit] เชื่อมบัญชีไม่สำเร็จ: {exc}"))
                self.events.put(("status", "เชื่อมบัญชีไม่สำเร็จ"))
            finally:
                if agent is not None:
                    agent.stop()
                self.events.put(("linkdone", ""))

        threading.Thread(target=work, daemon=True).start()

    def copy_address(self) -> None:
        self.save_address()
        if not self.address:
            self.status_var.set("ยังไม่มีที่อยู่ — ก๊อปมาจาก playit.gg ก่อน")
            return
        self.clipboard_clear()
        self.clipboard_append(self.address)
        self.status_var.set("ก๊อปที่อยู่แล้ว — ส่งให้เพื่อนได้เลย")

    def _enable_drop(self) -> None:
        """Dropping a pack anywhere on the window is the main way in."""
        ok = dnd.enable(self, self.on_dropped) or dnd.enable(self.drop_zone,
                                                             self.on_dropped)
        if not ok:
            self.drop_zone.config(text="เลือกโฟลเดอร์ modpack…", fg=FG)
        # Recorded because drag-and-drop is the main way in, and when it fails
        # inside a packaged exe there is nothing else on screen to say why.
        try:
            (LOGS_DIR / "startup.log").write_text(
                f"{APP_NAME} {APP_VERSION}\n"
                f"frozen={getattr(sys, 'frozen', False)}\n"
                f"drag_and_drop={'ok' if ok else 'unavailable'}\n"
                f"data_dir={APP_DIR}\n",
                encoding="utf-8")
        except OSError:
            pass

    def on_dropped(self, paths: list[str]) -> None:
        """A pack was dropped: add it, select it, and start it."""
        if self.session and self.session.running:
            messagebox.showinfo(APP_NAME, "เซิร์ฟเวอร์กำลังทำงานอยู่ — กดหยุดก่อน")
            return
        dropped = []
        for path in paths:
            folder = Path(path)
            if folder.is_file():
                folder = folder.parent
            if not folder.is_dir():
                continue
            # Look only inside what was dropped, or the default folders would
            # come back too and drown out the pack the user actually wants.
            found = inst_mod.scan([str(folder)], include_defaults=False)
            if found and str(folder) not in self.settings.instance_dirs:
                self.settings.instance_dirs.append(str(folder))
            dropped.extend(found)

        if not dropped:
            self.log("ไม่พบ modpack ในสิ่งที่ลากมา — ต้องเป็นโฟลเดอร์ของ modpack "
                     "ที่มีไฟล์ minecraftinstance.json, manifest.json "
                     "หรือ mmc-pack.json", "warn")
            self.status_var.set("โฟลเดอร์นั้นไม่ใช่ modpack")
            return

        self.settings.save()
        self.refresh_instances()
        self.pack_var.set(dropped[0].name)
        self.on_pack_changed()
        self.log(f"รับ modpack แล้ว: {dropped[0].name}", "ok")
        if self.eula_var.get():
            self.start_server()
        else:
            self.status_var.set("ติ๊กยอมรับ Minecraft EULA แล้วกดเริ่มได้เลย")

    def add_instance_folder(self) -> None:
        """Point the launcher at a modpack outside the CurseForge folder."""
        folder = filedialog.askdirectory(
            title="เลือกโฟลเดอร์ modpack (หรือโฟลเดอร์ที่เก็บ modpack หลายตัว)")
        if not folder:
            return
        found = inst_mod.scan([folder])
        known = {i.path.resolve() for i in self.instances}
        added = [i for i in found if i.path.resolve() not in known]
        if not added:
            messagebox.showwarning(
                APP_NAME,
                "ไม่พบ modpack ในโฟลเดอร์นี้\n\n"
                "โปรแกรมต้องการไฟล์ minecraftinstance.json, manifest.json "
                "หรือ mmc-pack.json เพื่อรู้เวอร์ชัน Minecraft และ mod loader")
            return
        if folder not in self.settings.instance_dirs:
            self.settings.instance_dirs.append(folder)
            self.settings.save()
        self.refresh_instances()
        self.pack_var.set(added[0].name)
        self.on_pack_changed()
        self.log(f"เพิ่มโฟลเดอร์แล้ว เจอ modpack {len(added)} ตัว: "
                 + ", ".join(i.name for i in added[:5]), "ok")

    def open_feedback(self) -> None:
        """Contact links, plus the log the developer will ask for anyway."""
        win = tk.Toplevel(self)
        win.title("ฟีดแบ็ก / ติดต่อผู้พัฒนา")
        win.configure(bg=PANEL)
        win.resizable(False, False)
        win.transient(self)

        frame = tk.Frame(win, bg=PANEL, padx=22, pady=18)
        frame.pack(fill="both", expand=True)

        tk.Label(frame, text="เจอบั๊ก หรืออยากเสนออะไร?", bg=PANEL, fg=FG,
                 font=FONT_BOLD).pack(anchor="w")
        tk.Label(frame, text="ทักมาได้เลยตามช่องทางด้านล่าง", bg=PANEL, fg=MUTED,
                 font=FONT).pack(anchor="w", pady=(2, 14))

        for text, url in CONTACT_LINKS:
            row = tk.Frame(frame, bg=PANEL)
            row.pack(anchor="w", fill="x", pady=3)
            tk.Label(row, text="•", bg=PANEL, fg=ACCENT, font=FONT).pack(side="left")
            link = tk.Label(row, text=text, bg=PANEL, fg="#7aa7ff", cursor="hand2",
                            font=FONT)
            link.pack(side="left", padx=(6, 0))
            link.bind("<Button-1>", lambda e, u=url: webbrowser.open(u))
            link.bind("<Enter>", lambda e, w=link: w.config(font=(FONT[0], FONT[1],
                                                                 "underline")))
            link.bind("<Leave>", lambda e, w=link: w.config(font=FONT))

        tk.Label(frame,
                 text="ถ้าแจ้งปัญหา แนบไฟล์บันทึกมาด้วยจะหาสาเหตุได้เร็วขึ้นมาก",
                 bg=PANEL, fg=MUTED, font=FONT, wraplength=380,
                 justify="left").pack(anchor="w", pady=(16, 8))

        buttons = tk.Frame(frame, bg=PANEL)
        buttons.pack(anchor="w", fill="x")
        ttk.Button(buttons, text="เปิดโฟลเดอร์บันทึก",
                   command=self.open_logs_folder).pack(side="left")
        ttk.Button(buttons, text="ปิด", command=win.destroy).pack(side="right")

        win.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - win.winfo_width()) // 2
        y = self.winfo_rooty() + 140
        win.geometry(f"+{max(x, 0)}+{max(y, 0)}")
        win.grab_set()

    def open_logs_folder(self) -> None:
        LOGS_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(LOGS_DIR)                                # noqa: S606

    def open_manual(self) -> None:
        """Open the bundled manual, or the online one if it is missing."""
        for base in (Path(getattr(sys, "_MEIPASS", "")), Path(__file__).parent):
            for name in ("คู่มือการใช้งาน.docx", "README.md"):
                doc = base / name
                if doc.is_file():
                    os.startfile(doc)                      # noqa: S606
                    return
        webbrowser.open("https://github.com/BrefGhost/MCServerLauncher")

    def open_data_folder(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        os.startfile(APP_DIR)                                 # noqa: S606

    def open_server_folder(self) -> None:
        inst = self.current_instance()
        if not inst:
            return
        path = SERVERS_DIR / inst.slug
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)                                    # noqa: S606

    def add_missing_mods(self) -> None:
        """Force mods named on the game's disconnect screen back onto the server."""
        inst = self.current_instance()
        text = self.missing_var.get().strip()
        if not inst or not text:
            return
        names = [n for n in re.split(r"[,\n]| {2,}", text) if n.strip()]
        added, unknown = autoheal.force_include(
            SERVERS_DIR / inst.slug, inst.slug, inst.path / "mods", names)
        for jar in added:
            self.log(f"จะเก็บ {jar} ไว้บนเซิร์ฟเวอร์ตั้งแต่นี้ไป", "ok")
        for name in unknown:
            self.log(f"หาม็อดชื่อ '{name}' ใน modpack นี้ไม่เจอ", "warn")
        if added:
            self.missing_var.set("")
            self.status_var.set("เพิ่มแล้ว — กดเริ่มเซิร์ฟเวอร์ใหม่เพื่อให้มีผล")
            if self.session and self.session.running:
                messagebox.showinfo(
                    APP_NAME, "เพิ่มม็อดแล้ว\nกดหยุดแล้วเริ่มเซิร์ฟเวอร์ใหม่ "
                              "เพื่อนถึงจะเข้าได้")

    def reset_disabled(self) -> None:
        inst = self.current_instance()
        if not inst:
            return
        if self.session and self.session.running:
            messagebox.showwarning(APP_NAME, "ปิดเซิร์ฟเวอร์ก่อน")
            return
        count = autoheal.reset_disabled(SERVERS_DIR / inst.slug, inst.slug)
        self.log(f"เอาม็อดที่ถูกปิดอัตโนมัติกลับมา {count} ตัว", "ok")

    # ---------------------------------------------------------------- events
    def _drain_events(self) -> None:
        try:
            while True:
                kind, payload = self.events.get_nowait()
                if kind == "log":
                    self.log(payload)
                elif kind == "status":
                    self.status_var.set(payload)
                elif kind == "addr":
                    self.address = payload
                    self.addr_var.set(payload)
                elif kind == "players":
                    self.players_var_txt.set(
                        "ออนไลน์: " + ", ".join(sorted(payload))
                        if payload else "ยังไม่มีใครออนไลน์")
                elif kind == "claim":
                    self.log("เปิดหน้าเว็บนี้แล้วกดยืนยันเพื่อเชื่อมบัญชี:", "sys")
                    self.log(f"    {payload}", "sys")
                    webbrowser.open(payload)
                elif kind == "linked":
                    if payload:
                        self.log(f"บัญชีพร้อมใช้งาน ({payload} tunnel)", "ok")
                elif kind == "linkdone":
                    self.link_btn.config(state="normal")
                elif kind == "state":
                    self._on_state(payload)
        except queue.Empty:
            pass
        self.after(80, self._drain_events)

    def _on_state(self, state: str) -> None:
        if state == "running":
            self.progress.stop()
            self.progress.config(mode="determinate", value=100)
        elif state in ("stopped", "error"):
            self.progress.stop()
            self.progress.config(mode="indeterminate", value=0)
            self.go_btn.config(text="▶  เริ่มเซิร์ฟเวอร์", style="Go.TButton",
                               state="normal")
            self.players_var_txt.set("ยังไม่มีใครออนไลน์")
            if self.addr_var.get() == "กำลังรอ …":
                self.addr_var.set("")

    LEVELS = ((("/ERROR]", "ERROR:", "[ผิดพลาด]", "Exception", "Caused by:"), "err"),
              (("/WARN]", "WARN:", "[เตือน]"), "warn"),
              (("[แก้ไข]", "[วิเคราะห์]", "[launcher]", "[playit]"), "sys"),
              (('Done (',), "ok"))

    def log(self, line: str, tag: str | None = None) -> None:
        if tag is None:
            tag = ""
            for needles, name in self.LEVELS:
                if any(n in line for n in needles):
                    tag = name
                    break
        self.console.configure(state="normal")
        at_bottom = self.console.yview()[1] > 0.995
        self.console.insert("end", line + "\n", tag)
        if int(self.console.index("end-1c").split(".")[0]) > 4000:
            self.console.delete("1.0", "1500.0")
        self.console.configure(state="disabled")
        if at_bottom:
            self.console.see("end")

    # ----------------------------------------------------------------- close
    def on_close(self) -> None:
        if self.session and self.session.running:
            if not messagebox.askyesno(
                    APP_NAME, "เซิร์ฟเวอร์ยังทำงานอยู่ ปิดโปรแกรมเลยไหม?\n"
                              "(โปรแกรมจะสั่งเซฟและปิดเซิร์ฟเวอร์ให้ก่อน)"):
                return
            self.status_var.set("กำลังปิดเซิร์ฟเวอร์ …")
            self.session.request_stop()
            self.after(1500, self.destroy)
            return
        self.destroy()


if __name__ == "__main__":
    App().mainloop()
