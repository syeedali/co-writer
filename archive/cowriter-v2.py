import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import json
from pathlib import Path
from datetime import datetime
import re


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


SYSTEM_PROMPT = """
You are Co-writer, a local writing assistant.

You help the user write, revise, and think through text.

Important rules:
- Line numbers refer only to the numbered snapshot provided in the current request.
- When suggesting edits, quote line numbers from that snapshot.
- Preserve the user's voice.
- Do not overwrite meaning unless asked.
- For targeted edits, return only replacement text between:
<<<REPLACEMENT>>>
and
<<<END_REPLACEMENT>>>
"""


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
            self.create_text(48, y, anchor="ne", text=line_num, fill="#777")
            i = self.text_widget.index(f"{i}+1line")


class CoWriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Co-writer v2")
        self.root.geometry("1250x820")

        self.dark_mode = True
        self.preview_replacement = None
        self.preview_range = None
        self.chat_history = []

        self.build_ui()
        self.apply_theme()
        self.load_current_file()
        self.schedule_autosave()
        self.schedule_line_number_update()

    def build_ui(self):
        main = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        main.pack(fill=tk.BOTH, expand=True)

        editor_frame = ttk.Frame(main)
        chat_frame = ttk.Frame(main)
        main.add(editor_frame, weight=3)
        main.add(chat_frame, weight=2)

        toolbar = ttk.Frame(editor_frame)
        toolbar.pack(fill=tk.X)

        ttk.Button(toolbar, text="Open", command=self.open_file).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Save Draft", command=self.save_current_file).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Save Version", command=self.save_version).pack(side=tk.LEFT)
        ttk.Button(toolbar, text="Toggle Theme", command=self.toggle_theme).pack(side=tk.LEFT)

        target_bar = ttk.Frame(editor_frame)
        target_bar.pack(fill=tk.X)

        ttk.Label(target_bar, text="Target lines:").pack(side=tk.LEFT)
        self.target_entry = ttk.Entry(target_bar, width=12)
        self.target_entry.pack(side=tk.LEFT, padx=4)
        self.target_entry.insert(0, "1-3")

        ttk.Button(target_bar, text="Targeted Edit", command=self.targeted_edit).pack(side=tk.LEFT)

        self.help_instruction = ttk.Entry(target_bar)
        self.help_instruction.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.help_instruction.insert(0, "Make this clearer while preserving my voice.")

        editor_area = ttk.Frame(editor_frame)
        editor_area.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            editor_area,
            wrap=tk.WORD,
            undo=True,
            font=("Consolas", 12),
            padx=8,
            pady=8,
            insertbackground="white"
        )

        self.line_numbers = LineNumbers(editor_area, self.text)

        yscroll = ttk.Scrollbar(editor_area, orient=tk.VERTICAL, command=self.on_scroll)
        xscroll = ttk.Scrollbar(editor_frame, orient=tk.HORIZONTAL, command=self.text.xview)

        self.text.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)

        self.line_numbers.pack(side=tk.LEFT, fill=tk.Y)
        self.text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        yscroll.pack(side=tk.RIGHT, fill=tk.Y)
        xscroll.pack(fill=tk.X)

        self.text.bind("<KeyRelease>", self.on_text_change)
        self.text.bind("<MouseWheel>", self.on_text_change)
        self.text.bind("<ButtonRelease-1>", self.on_text_change)

        ttk.Label(chat_frame, text="LLM Output").pack(anchor="w")

        self.chat_output = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 11),
            height=30,
            padx=8,
            pady=8
        )
        self.chat_output.pack(fill=tk.BOTH, expand=True)

        ttk.Label(chat_frame, text="Chat with Co-writer").pack(anchor="w")

        self.chat_input = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            height=5,
            font=("Segoe UI", 11),
            padx=8,
            pady=8
        )
        self.chat_input.pack(fill=tk.X)

        button_row = ttk.Frame(chat_frame)
        button_row.pack(fill=tk.X)

        ttk.Button(button_row, text="Ask", command=self.ask_llm).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Help Me Write", command=self.help_me_write).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Clear Chat", command=self.clear_chat).pack(side=tk.LEFT)

        self.status = ttk.Label(self.root, text="Ready")
        self.status.pack(fill=tk.X)

    def apply_theme(self):
        if self.dark_mode:
            bg = "#151515"
            panel = "#202020"
            fg = "#e8e8e8"
            insert = "#ffffff"
            line_bg = "#111111"
        else:
            bg = "#ffffff"
            panel = "#f3f3f3"
            fg = "#111111"
            insert = "#111111"
            line_bg = "#eeeeee"

        self.root.configure(bg=bg)
        self.text.configure(bg=bg, fg=fg, insertbackground=insert)
        self.chat_output.configure(bg=panel, fg=fg, insertbackground=insert)
        self.chat_input.configure(bg=bg, fg=fg, insertbackground=insert)
        self.line_numbers.configure(bg=line_bg)

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

    def parse_line_range(self):
        raw = self.target_entry.get().strip()
        match = re.match(r"^(\d+)\s*-\s*(\d+)$", raw)

        if not match:
            single = re.match(r"^(\d+)$", raw)
            if single:
                start = end = int(single.group(1))
            else:
                raise ValueError("Use a line range like 12-18 or a single line like 12.")
        else:
            start = int(match.group(1))
            end = int(match.group(2))

        if start < 1 or end < start:
            raise ValueError("Invalid line range.")

        return start, end

    def get_selected_text_info(self):
        try:
            start_index = self.text.index(tk.SEL_FIRST)
            end_index = self.text.index(tk.SEL_LAST)
            selected = self.text.get(start_index, end_index)
            return start_index, end_index, selected
        except tk.TclError:
            return None, None, None

    def call_ollama_stream(self, prompt, callback=None):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(self.chat_history[-8:])
        messages.append({"role": "user", "content": prompt})

        payload = {
            "model": OLLAMA_MODEL,
            "messages": messages,
            "stream": True,
            "options": {"temperature": 0.7}
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

        threading.Thread(target=self.call_ollama_stream, args=(prompt,), daemon=True).start()

    def targeted_edit(self):
        try:
            start, end = self.parse_line_range()
        except ValueError as e:
            messagebox.showerror("Line range error", str(e))
            return

        instruction = self.help_instruction.get().strip()
        if not instruction:
            instruction = "Improve this passage while preserving the user's voice."

        document = self.get_document_text()
        lines, numbered = make_numbered_snapshot(document)

        if end > len(lines):
            messagebox.showerror("Line range error", f"Document only has {len(lines)} lines.")
            return

        selected = "\n".join(lines[start - 1:end])

        prompt = f"""
Current numbered snapshot:

{numbered}

Targeted edit request:
Edit lines {start}-{end}.

Selected text:
{selected}

Instruction:
{instruction}

Return only the replacement text between:
<<<REPLACEMENT>>>
and
<<<END_REPLACEMENT>>>

Do not include line numbers inside the replacement.
"""

        self.preview_range = (start, end)
        self.append_chat("You", f"Targeted edit lines {start}-{end}: {instruction}")
        self.append_chat("Co-writer", "")

        threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt, self.extract_replacement_preview),
            daemon=True
        ).start()

    def extract_replacement_preview(self, response_text):
        start_tag = "<<<REPLACEMENT>>>"
        end_tag = "<<<END_REPLACEMENT>>>"

        if start_tag not in response_text or end_tag not in response_text:
            self.append_chat("System", "No replacement block found.")
            return

        start = response_text.index(start_tag) + len(start_tag)
        end = response_text.index(end_tag)

        replacement = response_text[start:end].strip()
        self.preview_replacement = replacement

        path = VERSIONS_DIR / f"targeted_preview_{timestamp()}.md"
        path.write_text(replacement, encoding="utf-8")

        self.show_targeted_preview(replacement)

    def show_targeted_preview(self, replacement):
        if not self.preview_range:
            return

        start, end = self.preview_range

        win = tk.Toplevel(self.root)
        win.title(f"Preview Targeted Edit: Lines {start}-{end}")
        win.geometry("850x600")

        box = tk.Text(win, wrap=tk.WORD, font=("Consolas", 12), bg="#151515", fg="#e8e8e8", insertbackground="white")
        box.pack(fill=tk.BOTH, expand=True)
        box.insert("1.0", replacement)

        ttk.Button(
            win,
            text="Accept Replacement Into Draft",
            command=lambda: self.accept_targeted_preview(win, box)
        ).pack(fill=tk.X)

    def accept_targeted_preview(self, win, box):
        replacement = box.get("1.0", tk.END).rstrip("\n")

        if not self.preview_range:
            return

        start, end = self.preview_range

        before_path = VERSIONS_DIR / f"before_targeted_edit_{timestamp()}.md"
        before_path.write_text(self.get_document_text(), encoding="utf-8")

        lines = self.get_document_text().splitlines()
        new_lines = lines[:start - 1] + replacement.splitlines() + lines[end:]

        self.set_document_text("\n".join(new_lines))
        self.save_current_file()

        after_path = VERSIONS_DIR / f"after_targeted_edit_{timestamp()}.md"
        after_path.write_text(self.get_document_text(), encoding="utf-8")

        self.append_chat("System", f"Accepted targeted edit. Saved before/after versions.")
        self.preview_range = None
        self.preview_replacement = None
        win.destroy()

    def help_me_write(self):
        document = self.get_document_text()
        lines, numbered = make_numbered_snapshot(document)
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

        threading.Thread(target=self.call_ollama_stream, args=(prompt,), daemon=True).start()


if __name__ == "__main__":
    root = tk.Tk()
    app = CoWriterApp(root)
    root.mainloop()