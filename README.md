# Co-writer v3

A local writing assistant that integrates with Ollama to help you write, edit, and refine text.

## 📝 Overview

Co-writer is a desktop application built with Python and Tkinter that provides an integrated writing environment with AI assistance. It allows you to:
- Write and edit text in a dedicated editor
- Ask questions or request help from an AI assistant (via Ollama)
- Edit selected text directly using AI suggestions
- Preview full drafts or revisions before accepting them
- Save versions of your work for tracking progress

The application works locally, meaning it doesn't send your writing to external servers — all processing happens on your machine.

---

## 🧠 Features

### ✍️ Writing Environment
- **Text Editor with Line Numbers**: Real-time line numbers for reference.
- **Undo/Redo Support**: Built-in text editing controls.
- **Auto-Save**: Automatically saves every 3 seconds to prevent data loss.
- **File Management**: Open, save, and version control of drafts.

### 💬 AI Assistant
- **Chat Interface**: Communicate with an LLM (default: `gemma3:12b`) via Ollama.
- **Context-Aware Responses**: Uses current document content for context.
- **Preview Revisions**: Request full preview rewrites or targeted edits to selected text.

### 🔧 Editing Tools
- **Selection Editing**: Edit only part of your document using AI suggestions.
- **Preview Windows**: See proposed changes before applying them.
- **Theme Toggle**: Switch between light and dark themes.

### 🗂️ Version Control
- Save snapshots of your work at any time.
- Track revisions and see how your writing evolves over time.

---

## 🧰 Requirements

- Python 3.7+
- [Ollama](https://ollama.com/) installed locally
- `requests` library (`pip install requests`)
- Standard Python libraries: `tkinter`, `threading`, `json`, `pathlib`, `datetime`

> ⚠️ Make sure you have a model pulled in Ollama before running the app. For example:
```bash
ollama pull gemma3:12b
```

---

## 🚀 Getting Started

### 1. Clone or Download the Script

Save the script as `cowriter-v3.2.py`.

### 2. Run the Application

```bash
python cowriter-v3.2.py
```

### 3. Start Writing!

- Type in the editor.
- Ask questions or request help in the chat box.
- Select text and click “Edit Selection” to get AI-generated replacements.
- Use “Generate Preview Draft” for a complete revised version.

---

## 📁 File Structure

The app creates a `workspace/` folder in its directory:

```
workspace/
├── current_draft.md         # Current working draft
├── autosaves/
│   └── current_draft.autosave.md  # Auto-saved versions
└── versions/
    ├── draft_version_20250405_123456.md
    ├── full_preview_20250405_123457.md
    └── ... (other saved versions)
```

---

## 🤖 AI Prompting Guide

### System Prompt (`soul.md`)
The system prompt defines how Co-writer behaves. It's located at `soul.md` and includes:

- Role: Local writing assistant.
- Instructions for editing, rewriting, and preserving the user’s voice.
- Format expectations (e.g., use `<<<REPLACEMENT>>>` or `<<<REVISED_DOCUMENT>>>` tags).

> You can customize this file to change how Co-writer responds.

---

## 🛠️ Usage Tips

### Selecting Text
1. Highlight text in the editor.
2. Type an instruction in the chat box.
3. Click **Edit Selection** to generate a replacement.

### Generating Preview Drafts
1. Type a request in the chat box.
2. Click **Generate Preview Draft**.
3. Review and accept the preview if satisfied.

### Saving Versions
- Use “Save Draft” to save the current state.
- Use “Save Version” to create a snapshot with timestamp.

---

## 🧪 Example Workflow

1. Start typing in the editor.
2. Ask: *"Improve clarity of paragraph 3."*
3. Click **Ask** → AI gives feedback or edits.
4. Select text and click **Edit Selection** → AI proposes a replacement.
5. Accept or reject the edit.
6. Use **Generate Preview Draft** to get a full rewrite.
7. Save final version using **Save Version**.

---

## 📦 Future Enhancements (Planned)

- Syntax highlighting for Markdown files
- Export to PDF/DOCX
- Undo/redo of AI suggestions
- Support for multiple LLM models
- Chat history persistence

---

## 🔒 Privacy Notice

This tool runs entirely locally. No data leaves your machine unless you explicitly share it.

---

## 📬 Feedback & Support

If you encounter issues or want to contribute:
- Open an issue on GitHub
- Submit a PR with improvements

---

## License

MIT License

--- 

*Co-writer v3 – Your Local Writing Companion*