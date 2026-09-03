"""One-off patch: a button that links the playit.gg account on demand."""
import pathlib

p = pathlib.Path(__file__).resolve().parent.parent / "MCServerLauncher.pyw"
s = p.read_text(encoding="utf-8")


def swap(old: str, new: str) -> None:
    global s
    assert old in s, old[:70]
    s = s.replace(old, new, 1)


swap("""        ttk.Button(addr, text="ดูที่ playit.gg",
                   command=tunnel.open_tunnels_page).grid(row=0, column=3, padx=(6, 0))""",
     """        self.link_btn = ttk.Button(addr, text="เชื่อมบัญชี playit.gg",
                                   command=self.link_playit)
        self.link_btn.grid(row=0, column=3, padx=(6, 0))""")

swap("""    def copy_address(self) -> None:""",
     '''    def link_playit(self) -> None:
        """Link (or re-link) the playit.gg account without starting a server.

        The account can stop working at any time - the agent gets deleted on
        the website, or a key is reset - and until now the only sign was a
        wall of "401 Unauthorized" with nothing the user could press.
        """
        if self.session and self.session.running:
            messagebox.showinfo(
                APP_NAME, "กำลังเปิดเซิร์ฟเวอร์อยู่ — กดหยุดก่อนแล้วค่อยเชื่อมบัญชีใหม่")
            return
        if tunnel.has_secret() and not messagebox.askyesno(
                APP_NAME,
                "ตอนนี้เชื่อมบัญชี playit.gg ไว้แล้ว\\n\\n"
                "จะเลิกใช้บัญชีเดิมแล้วเชื่อมใหม่ไหม?\\n"
                "(ที่อยู่เซิร์ฟเวอร์จะเปลี่ยน ต้องส่งอันใหม่ให้เพื่อน)"):
            return

        self.link_btn.config(state="disabled")
        self.status_var.set("กำลังเชื่อมบัญชี playit.gg …")
        self.log("กำลังเชื่อมบัญชี playit.gg — จะเปิดหน้าเว็บให้กดยืนยัน", "sys")

        def work() -> None:
            try:
                tunnel.forget_account()
                agent = tunnel.PlayitAgent(
                    on_log=lambda line: self.events.put(("log", line)),
                    on_claim=lambda url: self.events.put(("claim", url)),
                    on_tunnels=lambda n: self.events.put(("linked", n)))
                agent.start(progress=lambda msg, pct:
                            self.events.put(("status", msg)))
                # The agent prints the claim link, waits for the approval, then
                # writes the key itself; five minutes is longer than anyone
                # needs to press one button.
                for _ in range(300):
                    if tunnel.has_secret() and agent.connected:
                        break
                    time.sleep(1.0)
                agent.stop()
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
                self.events.put(("linkdone", ""))

        threading.Thread(target=work, daemon=True).start()

    def copy_address(self) -> None:''')

# events raised by the linking thread
swap("""                elif kind == "state":
                    self._on_state(payload)""",
     """                elif kind == "claim":
                    self.log("เปิดหน้าเว็บนี้แล้วกดยืนยันเพื่อเชื่อมบัญชี:", "sys")
                    self.log(f"    {payload}", "sys")
                    webbrowser.open(payload)
                elif kind == "linked":
                    if payload:
                        self.log(f"บัญชีพร้อมใช้งาน ({payload} tunnel)", "ok")
                elif kind == "linkdone":
                    self.link_btn.config(state="normal")
                elif kind == "state":
                    self._on_state(payload)""")

swap("import queue\nimport sys", "import queue\nimport sys\nimport threading\nimport time")

p.write_text(s, encoding="utf-8")
print("ใส่ปุ่มเชื่อมบัญชีแล้ว")
