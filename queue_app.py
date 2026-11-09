"""AMBOSS -> Anki Queue.

Copy cards in AMBOSS. This app moves them into a normal "AMBOSS Queue" deck in
Anki (unsuspended; already-studied ones are reset to new), so that deck holds
exactly the cards you've added. Needs Anki open with the AnkiConnect add-on
(code 2055492159).
"""
import json
import re
import urllib.request

import customtkinter as ctk

ANKI_URL = "http://127.0.0.1:8765"
QUEUE_DECK = "AMBOSS Queue"
CONFIRM_ABOVE = 200  # guard against an overly broad search
CLOZE_PATTERN = re.compile(r"\{\{c\d+::")
AMBOSS_PATTERN = re.compile(r"\bnid:\d+|tag:\S*AMBOSS", re.IGNORECASE)

ACCENT = ("#2f6fed", "#4c8dff")
GREEN = ("#1f9d55", "#3ddc84")
RED = ("#d64545", "#ff6b6b")
MUTED = ("#6b7280", "#9aa3b2")


def anki(action, timeout=10, **params):
    body = json.dumps({"action": action, "version": 6, "params": params}).encode()
    with urllib.request.urlopen(ANKI_URL, body, timeout=timeout) as resp:
        out = json.load(resp)
    if out.get("error"):
        raise RuntimeError(out["error"])
    return out["result"]


def clip_seq():
    """Windows counts every copy, so re-copying identical text still registers."""
    try:
        import ctypes
        return ctypes.windll.user32.GetClipboardSequenceNumber()
    except Exception:
        return None


def parse_cloze_lines(text):
    """AMBOSS 'Card Text' copy: optional header, then one cloze per line."""
    lines = [l.strip() for l in text.splitlines()]
    return [l for l in lines if l and l.lower() != "card text" and CLOZE_PATTERN.search(l)]


def add_text_cards(lines):
    """Create cloze notes for people without the AnKing deck. Returns (added, duplicates)."""
    if "Cloze" not in anki("modelNames"):
        raise RuntimeError("Your Anki has no 'Cloze' note type.")
    anki("createDeck", deck=QUEUE_DECK)
    notes = [{"deckName": QUEUE_DECK, "modelName": "Cloze", "fields": {"Text": l},
              "options": {"allowDuplicate": False}} for l in lines]
    ok = anki("canAddNotes", notes=notes)
    fresh = [n for n, good in zip(notes, ok) if good]
    if fresh:
        anki("addNotes", notes=fresh)
    return len(fresh), len(notes) - len(fresh)


def find_cards(query):
    return anki("findCards", query=query)


def queue_cards(cards):
    """Move the pasted cards into the queue deck, reset to new, unsuspended.
    Cards already in the queue deck are left exactly as they are, so pasting
    the same card again never wipes your progress.
    Returns (n_added, n_reset, n_unsuspended, n_already_there)."""
    anki("createDeck", deck=QUEUE_DECK)
    info = anki("cardsInfo", cards=cards)
    todo = [c for c in info if c["deckName"] != QUEUE_DECK]
    already = len(cards) - len(todo)
    if not todo:
        return 0, 0, 0, already
    ids = [c["cardId"] for c in todo]
    suspended = [c["cardId"] for c in todo if c["queue"] == -1]
    studied = [c["cardId"] for c in todo if c["type"] != 0]
    if suspended:
        anki("unsuspend", cards=suspended)
    if studied:
        anki("forgetCards", cards=studied)
    anki("changeDeck", cards=ids, deck=QUEUE_DECK)
    return len(ids), len(studied), len(suspended), already


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        ctk.set_appearance_mode("system")
        ctk.set_default_color_theme("blue")
        self.title("AMBOSS → Anki Queue")
        self.geometry("460x560")
        self.minsize(420, 520)
        self.attributes("-topmost", True)
        self.total = 0
        self.last_clip = ""
        self.pending = None  # query awaiting confirmation

        self.configure(padx=22, pady=20)
        ctk.CTkLabel(self, text="AMBOSS → Anki", font=ctk.CTkFont(size=24, weight="bold"),
                     anchor="w").pack(fill="x")
        ctk.CTkLabel(self, text="Copy cards in AMBOSS. That's it.", text_color=MUTED,
                     anchor="w").pack(fill="x", pady=(0, 14))

        self.status = ctk.CTkLabel(self, text="", anchor="w", corner_radius=10,
                                   fg_color=("#eef1f6", "#232733"), padx=14, pady=10)
        self.status.pack(fill="x")

        self.big = ctk.CTkLabel(self, text="Waiting for a copy…", font=ctk.CTkFont(size=16),
                                corner_radius=14, fg_color=("#e8efff", "#1c2540"),
                                height=120)
        self.big.pack(fill="x", pady=14)

        self.confirm = ctk.CTkFrame(self, corner_radius=12, fg_color=("#fdeaea", "#3b2326"))
        self.confirm_lbl = ctk.CTkLabel(self.confirm, anchor="w", justify="left", wraplength=380)
        self.confirm_lbl.pack(fill="x", padx=14, pady=(10, 4))
        row = ctk.CTkFrame(self.confirm, fg_color="transparent")
        row.pack(fill="x", padx=14, pady=(0, 10))
        ctk.CTkButton(row, text="Add anyway", width=110, fg_color=RED,
                      command=self.confirm_yes).pack(side="left")
        ctk.CTkButton(row, text="Cancel", width=90, fg_color="transparent", border_width=1,
                      text_color=("#222", "#ddd"), command=self.confirm_no).pack(side="left", padx=8)

        self.open_btn = ctk.CTkButton(self, text="Open AMBOSS Queue in Anki", height=40,
                                      font=ctk.CTkFont(size=14, weight="bold"),
                                      command=self.open_deck)
        self.open_btn.pack(fill="x")

        ctk.CTkLabel(self, text="Activity", anchor="w", text_color=MUTED).pack(fill="x", pady=(16, 2))
        self.log = ctk.CTkTextbox(self, height=110, state="disabled", corner_radius=10)
        self.log.pack(fill="both", expand=True)

        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", pady=(10, 0))
        self.watch = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(bar, text="Watch clipboard", variable=self.watch).pack(side="left")
        self.ontop = ctk.BooleanVar(value=True)
        ctk.CTkSwitch(bar, text="On top", variable=self.ontop,
                      command=lambda: self.attributes("-topmost", self.ontop.get())
                      ).pack(side="right")

        self.last_clip = self.clipboard()
        self.last_seq = clip_seq()
        self.refresh_status()
        self.poll()
        self.keep_connected()

    # --- helpers ---
    def clipboard(self):
        try:
            return self.clipboard_get().strip()
        except Exception:
            return ""

    def write(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def refresh_status(self):
        try:
            anki("version", timeout=2)
            self.status.configure(text="●  Connected to Anki", text_color=GREEN)
            return True
        except Exception:
            self.status.configure(
                text="●  Can't reach Anki. Open Anki (with AnkiConnect installed).",
                text_color=RED)
            return False

    # --- actions ---
    def handle(self, query):
        if not self.refresh_status():
            return
        if CLOZE_PATTERN.search(query):
            try:
                a, d = add_text_cards(parse_cloze_lines(query))
                self.total += a
                dup = f"\n{d} already in Anki: skipped" if d else ""
                self.big.configure(text=f"✓  {a} cards created{dup}"
                                   if a else f"Nothing new to create{dup}",
                                   text_color=GREEN if a else MUTED)
                self.write(f"{a} cards created in '{QUEUE_DECK}', {d} duplicates skipped.")
            except Exception as e:
                self.write(f"Error: {e}")
            return
        query = " ".join(query.split())
        try:
            cards = find_cards(query)
            if not cards:
                self.big.configure(text="No matching cards\nin your Anki.", text_color=RED)
                self.write("No matching cards.")
            elif len(cards) > CONFIRM_ABOVE:
                self.pending = cards
                self.confirm_lbl.configure(
                    text=f"That search matches {len(cards)} cards, which is more than usual. "
                         "Add them all?")
                self.confirm.pack(fill="x", before=self.open_btn, pady=(0, 10))
            else:
                self.finish(cards)
        except Exception as e:
            self.write(f"Error: {e}")

    def finish(self, cards):
        n, r, u, k = queue_cards(cards)
        self.total += n
        parts = [f"{n} added to {QUEUE_DECK}"] if n else []
        if r:
            parts.append(f"{r} reset to new")
        note = f"\n{k} already in the queue: left alone" if k else ""
        if n:
            self.big.configure(text=f"✓  {', '.join(parts)}{note}", text_color=GREEN)
        else:
            self.big.configure(text=f"Nothing new to add{note}", text_color=MUTED)
        self.write(f"{n} added ({r} reset, {u} unsuspended), {k} already there. Total: {self.total}")

    def confirm_yes(self):
        cards, self.pending = self.pending, None
        self.confirm.pack_forget()
        if cards:
            self.finish(cards)

    def confirm_no(self):
        self.pending = None
        self.confirm.pack_forget()
        self.write("Cancelled.")

    def open_deck(self):
        try:
            anki("guiDeckOverview", name=QUEUE_DECK)
        except Exception as e:
            self.write(f"Couldn't open deck: {e}")

    def keep_connected(self):
        """Re-check Anki every 3s so the app connects whenever Anki opens."""
        self.refresh_status()
        self.after(3000, self.keep_connected)

    def poll(self):
        if self.watch.get():
            clip, seq = self.clipboard(), clip_seq()
            if seq is not None:
                changed = seq != self.last_seq
            else:
                changed = clip != self.last_clip
            if changed and clip and (AMBOSS_PATTERN.search(clip) or CLOZE_PATTERN.search(clip)):
                self.write("Copied from AMBOSS…")
                self.handle(clip)
            self.last_clip, self.last_seq = clip, seq
        self.after(1000, self.poll)


if __name__ == "__main__":
    App().mainloop()
