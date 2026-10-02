import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import json
from pathlib import Path
from datetime import datetime


OLLAMA_MODEL = "gemma3:12b"
OLLAMA_URL = "http://localhost:11434/api/chat"

APP_DIR = Path(__file__).parent
WORK_DIR = APP_DIR / "workspace"
AUTOSAVE_DIR = WORK_DIR / "autosaves"
VERSIONS_DIR = WORK_DIR / "versions"

WORK_DIR.mkdir(exist_ok=True)
AUTOSAVE_DIR.mkdir(exist_ok=True)
VERSIONS_DIR.mkdir(exist_ok=True)

CURRENT_FILE = WORK_DIR / "current_draft.md"
AUTOSAVE_FILE = AUTOSAVE_DIR / "current_draft.autosave.md"
SOUL_FILE = APP_DIR / "soul.md"

DEFAULT_SOUL = """
# Co-writer Soul

You are Co-writer, a local LLM writing assistant.

Your job:
- Help the user write, revise, expand, clarify, and organize text.
- Preserve the user's voice.
- Never overwrite meaning unless directly asked.
- Treat selected text as the active writing surface.
- Treat the chat box as the user's instruction.
- Use line numbers only as temporary references from the current snapshot.
- Give practical writing help, not generic encouragement.
- Prefer useful prose over explanation.
- When editing selected text, return only replacement text between:
<<<REPLACEMENT>>>
and
<<<END_REPLACEMENT>>>
- When generating a full draft preview, return the complete revised document between:
<<<REVISED_DOCUMENT>>>
and
<<<END_REVISED_DOCUMENT>>>

Style:
- Thoughtful.
- Precise.
- Grounded.
- Not over-polished.
- Not corporate.
- Not melodramatic.
"""

if not SOUL_FILE.exists():
    SOUL_FILE.write_text(DEFAULT_SOUL, encoding="utf-8")


def load_soul():
    return SOUL_FILE.read_text(encoding="utf-8", errors="replace")


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def make_numbered_snapshot(text):
    lines = text.splitlines()
    numbered = "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))
    return lines, numbered


class LineNumbers(tk.Canvas):
    def __init__(self, master, text_widget, **kwargs):
        super().__init__(master, width=55, highlightthickness=0, **kwargs)
        self.text_widget = text_widget

    def redraw(self, *args):
        self.delete("all")
        i = self.text_widget.index("@0,0")

        while True:
            dline = self.text_widget.dlineinfo(i)
            if dline is None:
                break

            y = dline[1]
            line_num = str(i).split(".")[0]
            self.create_text(48, y, anchor="ne", text=line_num, fill="#888")
            i = self.text_widget.index(f"{i}+1line")


class CoWriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Co-writer v3")
        self.root.geometry("1250x820")

        self.dark_mode = True
        self.chat_history = []
        self.pending_selection = None

        self.build_ui()
        self.apply_theme()
        self.load_current_file()
        self.schedule_autosave()
        self.schedule_line_number_update()

    def build_ui(self):
        self.style = ttk.Style()
        self.style.theme_use("clam")

        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        editor_frame = ttk.Frame(main)
        chat_frame = ttk.Frame(main)

        main.add(editor_frame, weight=3)
        main.add(chat_frame, weight=2)

        toolbar = ttk.Frame(editor_frame)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(toolbar, text="Save Draft", command=self.save_current_file).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(toolbar, text="Save Version", command=self.save_version).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(toolbar, text="Toggle Theme", command=self.toggle_theme).pack(side=tk.LEFT, padx=2, pady=2)

        selection_bar = ttk.Frame(editor_frame)
        selection_bar.pack(fill=tk.X)

        ttk.Button(selection_bar, text="Edit Selection", command=self.edit_selection).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(selection_bar, text="Ask About Selection", command=self.ask_about_selection).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(selection_bar, text="Help Me Write", command=self.help_me_write).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(selection_bar, text="Generate Preview Draft", command=self.generate_preview_draft).pack(side=tk.LEFT, padx=2, pady=2)

        ttk.Label(
            selection_bar,
            text="Select text, type instruction in chat box, then click Edit Selection."
        ).pack(side=tk.LEFT, padx=8)

        editor_area = ttk.Frame(editor_frame)
        editor_area.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            editor_area,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 12),
            padx=10,
            pady=10,
            insertbackground="white",
            selectbackground="#3a5f8a",
            selectforeground="#ffffff"
        )

        self.line_numbers = LineNumbers(editor_area, self.text)

        yscroll = ttk.Scrollbar(editor_area, orient=tk.VERTICAL, command=self.on_scroll)
        self.text.configure(yscrollcommand=yscroll.set)

        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.text.bind("<KeyRelease>", self.on_text_change)
        self.text.bind("<MouseWheel>", self.on_text_change)
        self.text.bind("<ButtonRelease-1>", self.on_text_change)

        ttk.Label(chat_frame, text="LLM Output").pack(anchor="w", padx=4, pady=(4, 0))

        self.chat_output = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 11),
            height=30,
            padx=10,
            pady=10,
            insertbackground="white",
            selectbackground="#3a5f8a",
            selectforeground="#ffffff"
        )
        self.chat_output.pack(fill=tk.BOTH, expand=True, padx=4, pady=4)

        ttk.Label(chat_frame, text="Chat / Instruction").pack(anchor="w", padx=4)

        self.chat_input = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            height=5,
            font=("Segoe UI", 11),
            padx=10,
            pady=10,
            insertbackground="white",
            selectbackground="#3a5f8a",
            selectforeground="#ffffff"
        )
        self.chat_input.pack(fill=tk.X, padx=4, pady=4)

        button_row = ttk.Frame(chat_frame)
        button_row.pack(fill=tk.X)

        ttk.Button(button_row, text="Ask", command=self.ask_llm).pack(side=tk.LEFT, padx=2, pady=2)
        ttk.Button(button_row, text="Clear Chat", command=self.clear_chat).pack(side=tk.LEFT, padx=2, pady=2)

        self.status = ttk.Label(self.root, text="Ready")
        self.status.pack(fill=tk.X)

    def apply_theme(self):
        if self.dark_mode:
            bg = "#151515"
            panel = "#202020"
            fg = "#e8e8e8"
            button = "#2a2a2a"
            button_active = "#3a3a3a"
            line_bg = "#111111"
            insert = "#ffffff"
        else:
            bg = "#ffffff"
            panel = "#f3f3f3"
            fg = "#111111"
            button = "#e5e5e5"
            button_active = "#d5d5d5"
            line_bg = "#eeeeee"
            insert = "#111111"

        self.root.configure(bg=bg)

        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TButton", background=button, foreground=fg, borderwidth=1, padding=5)
        self.style.map("TButton", background=[("active", button_active)])
        self.style.configure("TPanedwindow", background=bg)
        self.style.configure("Vertical.TScrollbar", background=button, troughcolor=bg)

        self.text.configure(bg=bg, fg=fg, insertbackground=insert)
        self.chat_output.configure(bg=panel, fg=fg, insertbackground=insert)
        self.chat_input.configure(bg=bg, fg=fg, insertbackground=insert)
        self.line_numbers.configure(bg=line_bg)
        self.status.configure(background=bg, foreground=fg)

    def toggle_theme(self):
        self.dark_mode = not self.dark_mode
        self.apply_theme()

    def on_scroll(self, *args):
        self.text.yview(*args)
        self.line_numbers.redraw()

    def on_text_change(self, event=None):
        self.line_numbers.redraw()

    def schedule_line_number_update(self):
        self.line_numbers.redraw()
        self.root.after(300, self.schedule_line_number_update)

    def get_document_text(self):
        return self.text.get("1.0", tk.END).rstrip("\n")

    def set_document_text(self, content):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.line_numbers.redraw()

    def get_selected_text_info(self):
        try:
            start_index = self.text.index(tk.SEL_FIRST)
            end_index = self.text.index(tk.SEL_LAST)
            selected = self.text.get(start_index, end_index)
            return start_index, end_index, selected
        except tk.TclError:
            return None, None, None

    def load_current_file(self):
        if CURRENT_FILE.exists():
            self.set_document_text(CURRENT_FILE.read_text(encoding="utf-8"))
        else:
            self.set_document_text("# Untitled Draft\n\nStart writing here.")
            self.save_current_file()

    def open_file(self):
        path = filedialog.askopenfilename(
            initialdir=WORK_DIR,
            filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")]
        )
        if not path:
            return

        content = Path(path).read_text(encoding="utf-8", errors="replace")
        self.set_document_text(content)
        self.append_chat("System", f"Opened file: {path}")
        self.save_current_file()

    def save_current_file(self):
        CURRENT_FILE.write_text(self.get_document_text(), encoding="utf-8")
        self.status.config(text=f"Saved draft: {CURRENT_FILE}")

    def autosave(self):
        AUTOSAVE_FILE.write_text(self.get_document_text(), encoding="utf-8")
        self.status.config(text=f"Autosaved: {datetime.now().strftime('%H:%M:%S')}")

    def schedule_autosave(self):
        self.autosave()
        self.root.after(3000, self.schedule_autosave)

    def save_version(self):
        path = VERSIONS_DIR / f"draft_version_{timestamp()}.md"
        path.write_text(self.get_document_text(), encoding="utf-8")
        self.append_chat("System", f"Saved version: {path}")

    def append_chat(self, speaker, message):
        self.chat_output.configure(state=tk.NORMAL)
        self.chat_output.insert(tk.END, f"\n{speaker}:\n{message}\n")
        self.chat_output.see(tk.END)
        self.chat_output.configure(state=tk.DISABLED)

    def stream_to_chat(self, chunk):
        self.chat_output.configure(state=tk.NORMAL)
        self.chat_output.insert(tk.END, chunk)
        self.chat_output.see(tk.END)
        self.chat_output.configure(state=tk.DISABLED)

    def clear_chat(self):
        self.chat_output.configure(state=tk.NORMAL)
        self.chat_output.delete("1.0", tk.END)
        self.chat_output.configure(state=tk.DISABLED)
        self.chat_history = []

    def call_ollama_stream(self, prompt, callback=None):
        messages = [{"role": "system", "content": load_soul()}]
        messages.extend(self.chat_history[-8:])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {
                "temperature": 0.7
            }
        }

        response_text = ""

        try:
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=180) as r:
                r.raise_for_status()

                for line in r.iter_lines():
                    if not line:
                        continue

                    data = json.loads(line.decode("utf-8"))

                    if "message" in data and "content" in data["message"]:
                        chunk = data["message"]["content"]
                        response_text += chunk
                        self.root.after(0, self.stream_to_chat, chunk)

                    if data.get("done"):
                        break

        except Exception as e:
            response_text = f"Error talking to Ollama: {e}"
            self.root.after(0, self.append_chat, "System", response_text)

        self.chat_history.append({"role": "user", "content": prompt})
        self.chat_history.append({"role": "assistant", "content": response_text})

        if callback:
            self.root.after(0, callback, response_text)

    def ask_llm(self):
        user_message = self.chat_input.get("1.0", tk.END).strip()
        if not user_message:
            return

        self.chat_input.delete("1.0", tk.END)

        document = self.get_document_text()
        _, numbered = make_numbered_snapshot(document)

        prompt = f"""
Current numbered snapshot:

{numbered}

User message:
{user_message}

Remember: line numbers refer only to this exact snapshot.
"""

        self.append_chat("You", user_message)
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt,),
            daemon=True
        ).start()

    def edit_selection(self):
        start_index, end_index, selected = self.get_selected_text_info()

        if not selected:
            messagebox.showinfo("No selection", "Select text in the editor first.")
            return

        instruction = self.chat_input.get("1.0", tk.END).strip()
        if not instruction:
            instruction = "Improve this selected text while preserving my voice."

        document = self.get_document_text()
        _, numbered = make_numbered_snapshot(document)

        prompt = f"""
Current numbered snapshot:

{numbered}

The user selected this text:

{selected}

Instruction:
{instruction}

Return only the replacement text between:
<<<REPLACEMENT>>>
and
<<<END_REPLACEMENT>>>

Do not include line numbers inside the replacement.
"""

        self.pending_selection = {
            "start": start_index,
            "end": end_index,
            "original": selected
        }

        self.chat_input.delete("1.0", tk.END)
        self.append_chat("You", f"Edit selected text: {instruction}")
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt, self.extract_selection_preview),
            daemon=True
        ).start()

    def ask_about_selection(self):
        _, _, selected = self.get_selected_text_info()

        if not selected:
            messagebox.showinfo("No selection", "Select text in the editor first.")
            return

        user_message = self.chat_input.get("1.0", tk.END).strip()
        if not user_message:
            user_message = "Give me useful feedback on this selected text."

        document = self.get_document_text()
        _, numbered = make_numbered_snapshot(document)

        prompt = f"""
Current numbered snapshot:

{numbered}

Selected text:

{selected}

User question:
{user_message}

Give focused feedback on the selected text.
Refer to line numbers from the snapshot when helpful.
"""

        self.chat_input.delete("1.0", tk.END)
        self.append_chat("You", f"Ask about selected text: {user_message}")
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt,),
            daemon=True
        ).start()

    def extract_selection_preview(self, response_text):
        start_tag = "<<<REPLACEMENT>>>"
        end_tag = "<<<END_REPLACEMENT>>>"

        if start_tag not in response_text or end_tag not in response_text:
            self.append_chat("System", "No replacement block found.")
            return

        start = response_text.index(start_tag) + len(start_tag)
        end = response_text.index(end_tag)

        replacement = response_text[start:end].strip()
        self.show_selection_preview(replacement)

    def show_selection_preview(self, replacement):
        win = tk.Toplevel(self.root)
        win.title("Preview Selection Edit")
        win.geometry("850x600")

        box = tk.Text(
            win,
            wrap=tk.WORD,
            font=("Consolas", 12),
            bg="#151515" if self.dark_mode else "#ffffff",
            fg="#e8e8e8" if self.dark_mode else "#111111",
            insertbackground="white" if self.dark_mode else "black",
            padx=10,
            pady=10
        )
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", replacement)

        ttk.Button(
            win,
            text="Accept Replacement Into Draft",
            command=lambda: self.accept_selection_preview(win, box)
        ).pack(fill=tk.X)

    def accept_selection_preview(self, win, box):
        if not self.pending_selection:
            return

        replacement = box.get("1.0", tk.END).rstrip("\n")

        before_path = VERSIONS_DIR / f"before_selection_edit_{timestamp()}.md"
        before_path.write_text(self.get_document_text(), encoding="utf-8")

        start = self.pending_selection["start"]
        end = self.pending_selection["end"]

        self.text.delete(start, end)
        self.text.insert(start, replacement)

        self.save_current_file()

        after_path = VERSIONS_DIR / f"after_selection_edit_{timestamp()}.md"
        after_path.write_text(self.get_document_text(), encoding="utf-8")

        self.append_chat("System", "Accepted selection edit. Saved before/after versions.")

        self.pending_selection = None
        win.destroy()

    def generate_preview_draft(self):
        user_message = self.chat_input.get("1.0", tk.END).strip()
        if not user_message:
            user_message = "Consolidate the edits discussed in chat into a complete revised preview draft."

        document = self.get_document_text()
        _, numbered = make_numbered_snapshot(document)

        recent_chat = "\n\n".join(
            f"{item['role'].upper()}:\n{item['content']}"
            for item in self.chat_history[-8:]
        )

        prompt = f"""
Current numbered snapshot:

{numbered}

Recent chat context:

{recent_chat}

User instruction:
{user_message}

Create a full revised preview draft that consolidates the relevant edits discussed in chat.

Return the complete revised document only between:
<<<REVISED_DOCUMENT>>>
and
<<<END_REVISED_DOCUMENT>>>

Do not include line numbers inside the revised document.
"""

        self.chat_input.delete("1.0", tk.END)
        self.append_chat("You", f"Generate preview draft: {user_message}")
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt, self.extract_full_preview),
            daemon=True
        ).start()

    def extract_full_preview(self, response_text):
        start_tag = "<<<REVISED_DOCUMENT>>>"
        end_tag = "<<<END_REVISED_DOCUMENT>>>"

        if start_tag not in response_text or end_tag not in response_text:
            self.append_chat("System", "No revised document block found.")
            return

        start = response_text.index(start_tag) + len(start_tag)
        end = response_text.index(end_tag)

        revised = response_text[start:end].strip()

        preview_path = VERSIONS_DIR / f"full_preview_{timestamp()}.md"
        preview_path.write_text(revised, encoding="utf-8")

        self.show_full_preview(revised, preview_path)

    def show_full_preview(self, revised, preview_path):
        win = tk.Toplevel(self.root)
        win.title("Preview Full Draft")
        win.geometry("950x700")

        box = tk.Text(
            win,
            wrap=tk.WORD,
            font=("Consolas", 12),
            bg="#151515" if self.dark_mode else "#ffffff",
            fg="#e8e8e8" if self.dark_mode else "#111111",
            insertbackground="white" if self.dark_mode else "black",
            padx=10,
            pady=10
        )
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", revised)

        ttk.Button(
            win,
            text="Accept Preview as New Working Draft",
            command=lambda: self.accept_full_preview(win, box)
        ).pack(fill=tk.X)

        self.append_chat("System", f"Full preview saved separately: {preview_path}")

    def accept_full_preview(self, win, box):
        revised = box.get("1.0", tk.END).rstrip("\n")

        before_path = VERSIONS_DIR / f"before_full_preview_accept_{timestamp()}.md"
        before_path.write_text(self.get_document_text(), encoding="utf-8")

        accepted_path = VERSIONS_DIR / f"accepted_full_preview_{timestamp()}.md"
        accepted_path.write_text(revised, encoding="utf-8")

        self.set_document_text(revised)
        self.save_current_file()

        self.append_chat("System", f"Accepted full preview as new working draft. Saved version: {accepted_path}")
        win.destroy()

    def help_me_write(self):
        document = self.get_document_text()
        lines, _ = make_numbered_snapshot(document)
        tail = "\n".join(lines[-25:])

        prompt = f"""
The user wants a small continuation.

Last part of the current draft:

{tail}

Write only 2 to 4 sentences that could continue from here.
Preserve the user's voice.
Do not explain.
"""

        self.append_chat("You", "Help me write.")
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt,),
            daemon=True
        ).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = CoWriterApp(root)
    root.mainloop()