import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import requests
import json
import time
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


SYSTEM_PROMPT = """
You are Co-writer, a local writing assistant.

You help the user write, revise, and think through text.

Rules:
- Refer to the user's document by line number when helpful.
- Do not overwrite the user's voice.
- Suggest concrete edits.
- When asked for a preview rewrite, return the complete revised document between:
<<<REVISED_DOCUMENT>>>
and
<<<END_REVISED_DOCUMENT>>>
- Never claim you saved a file unless the app says it saved a file.
- Preserve meaning unless the user asks for transformation.
"""


def timestamp():
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def number_lines(text):
    lines = text.splitlines()
    return "\n".join(f"{i+1}: {line}" for i, line in enumerate(lines))


class LineNumbers(tk.Canvas):
    def __init__(self, master, text_widget, **kwargs):
        super().__init__(master, width=50, **kwargs)
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
            self.create_text(45, y, anchor="ne", text=line_num, fill="#777")

            i = self.text_widget.index(f"{i}+1line")


class CoWriterApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Co-writer - Local LLM Writing Assistant")
        self.root.geometry("1200x800")

        self.preview_text = None
        self.chat_history = []

        self.build_ui()
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
        ttk.Button(toolbar, text="Accept Preview as New Version", command=self.accept_preview).pack(side=tk.LEFT)

        editor_area = ttk.Frame(editor_frame)
        editor_area.pack(fill=tk.BOTH, expand=True)

        self.text = tk.Text(
            editor_area,
            wrap=tk.NONE,
            undo=True,
            font=("Consolas", 12),
            padx=6,
            pady=6
        )

        self.line_numbers = LineNumbers(editor_area, self.text, bg="#f0f0f0")

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
            height=30
        )
        self.chat_output.pack(fill=tk.BOTH, expand=True)

        ttk.Label(chat_frame, text="Chat with Co-writer").pack(anchor="w")

        self.chat_input = tk.Text(
            chat_frame,
            wrap=tk.WORD,
            height=5,
            font=("Segoe UI", 11)
        )
        self.chat_input.pack(fill=tk.X)

        button_row = ttk.Frame(chat_frame)
        button_row.pack(fill=tk.X)

        ttk.Button(button_row, text="Ask", command=self.ask_llm).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Preview Rewrite", command=self.preview_rewrite).pack(side=tk.LEFT)
        ttk.Button(button_row, text="Clear Chat", command=self.clear_chat).pack(side=tk.LEFT)

        self.status = ttk.Label(self.root, text="Ready")
        self.status.pack(fill=tk.X)

    def on_scroll(self, *args):
        self.text.yview(*args)
        self.line_numbers.redraw()

    def on_text_change(self, event=None):
        self.line_numbers.redraw()

    def schedule_line_number_update(self):
        self.line_numbers.redraw()
        self.root.after(300, self.schedule_line_number_update)

    def get_document_text(self):
        return self.text.get("1.0", tk.END).rstrip()

    def set_document_text(self, content):
        self.text.delete("1.0", tk.END)
        self.text.insert("1.0", content)
        self.line_numbers.redraw()

    def load_current_file(self):
        if CURRENT_FILE.exists():
            self.set_document_text(CURRENT_FILE.read_text(encoding="utf-8"))
        else:
            self.set_document_text("# Untitled Draft\n\nStart writing here.\n")
            self.save_current_file()

    def open_file(self):
        path = filedialog.askopenfilename(
            initialdir=WORK_DIR,
            filetypes=[("Text files", "*.txt *.md"), ("All files", "*.*")]
        )
        if not path:
            return

        path = Path(path)
        content = path.read_text(encoding="utf-8", errors="replace")
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

    def clear_chat(self):
        self.chat_output.configure(state=tk.NORMAL)
        self.chat_output.delete("1.0", tk.END)
        self.chat_output.configure(state=tk.DISABLED)
        self.chat_history = []

    def build_context_prompt(self, user_message, preview_mode=False):
        document = self.get_document_text()
        numbered = number_lines(document)

        if preview_mode:
            mode_instruction = """
The user wants a preview rewrite.

Return the complete revised document only inside:

<<<REVISED_DOCUMENT>>>
[full revised document here]
<<<END_REVISED_DOCUMENT>>>

After that, you may briefly explain what changed.
"""
        else:
            mode_instruction = """
Respond conversationally. Use line numbers when useful. Suggest edits, explain issues, or help brainstorm.
"""

        return f"""
Current document with line numbers:

{numbered}

User message:
{user_message}

{mode_instruction}
"""

    def call_ollama_stream(self, prompt, preview_mode=False):
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]

        for item in self.chat_history[-8:]:
            messages.append(item)

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
            with requests.post(OLLAMA_URL, json=payload, stream=True, timeout=120) as r:
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

        if preview_mode:
            self.root.after(0, self.extract_preview, response_text)

    def stream_to_chat(self, chunk):
        self.chat_output.configure(state=tk.NORMAL)
        self.chat_output.insert(tk.END, chunk)
        self.chat_output.see(tk.END)
        self.chat_output.configure(state=tk.DISABLED)

    def ask_llm(self):
        user_message = self.chat_input.get("1.0", tk.END).strip()
        if not user_message:
            return

        self.chat_input.delete("1.0", tk.END)
        self.append_chat("You", user_message)
        self.append_chat("Co-writer", "")

        prompt = self.build_context_prompt(user_message, preview_mode=False)

        thread = threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt, False),
            daemon=True
        )
        thread.start()

    def preview_rewrite(self):
        user_message = self.chat_input.get("1.0", tk.END).strip()

        if not user_message:
            user_message = "Create a clean revised draft of the current document while preserving my voice."

        self.chat_input.delete("1.0", tk.END)
        self.append_chat("You", f"[Preview request] {user_message}")
        self.append_chat("Co-writer", "")

        prompt = self.build_context_prompt(user_message, preview_mode=True)

        thread = threading.Thread(
            target=self.call_ollama_stream,
            args=(prompt, True),
            daemon=True
        )
        thread.start()

    def extract_preview(self, response_text):
        start_tag = "<<<REVISED_DOCUMENT>>>"
        end_tag = "<<<END_REVISED_DOCUMENT>>>"

        if start_tag not in response_text or end_tag not in response_text:
            self.append_chat("System", "No preview document block found.")
            return

        start = response_text.index(start_tag) + len(start_tag)
        end = response_text.index(end_tag)

        revised = response_text[start:end].strip()
        self.preview_text = revised

        preview_path = VERSIONS_DIR / f"preview_{timestamp()}.md"
        preview_path.write_text(revised, encoding="utf-8")

        self.append_chat("System", f"Preview saved separately: {preview_path}")
        self.show_preview_window(revised)

    def show_preview_window(self, revised):
        win = tk.Toplevel(self.root)
        win.title("Preview Rewrite")
        win.geometry("900x700")

        preview_box = tk.Text(win, wrap=tk.WORD, font=("Consolas", 12))
        preview_box.pack(fill=tk.BOTH, expand=True)
        preview_box.insert("1.0", revised)

        ttk.Button(
            win,
            text="Load Preview Into Editor as New Working Draft",
            command=lambda: self.load_preview_into_editor(win, preview_box)
        ).pack(fill=tk.X)

    def load_preview_into_editor(self, win, preview_box):
        self.preview_text = preview_box.get("1.0", tk.END).rstrip()
        self.accept_preview()
        win.destroy()

    def accept_preview(self):
        if not self.preview_text:
            messagebox.showinfo("No preview", "There is no preview to accept.")
            return

        version_path = VERSIONS_DIR / f"accepted_preview_{timestamp()}.md"
        version_path.write_text(self.preview_text, encoding="utf-8")

        self.set_document_text(self.preview_text)

        # Save current working draft too, but the accepted preview remains separately versioned.
        self.save_current_file()

        self.append_chat("System", f"Accepted preview as new version: {version_path}")
        self.preview_text = None


if __name__ == "__main__":
    root = tk.Tk()
    app = CoWriterApp(root)
    root.mainloop()