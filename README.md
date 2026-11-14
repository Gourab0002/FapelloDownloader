# Fapello Downloader

A high-performance, resilient, and multi-threaded Python command-line utility to download all full-resolution photos and videos from **Fapello** (`fapello.com` and `fapello.to`).

---

## ✨ Features

- **Multi-Domain Support**: Seamlessly works with both `fapello.com` and `fapello.to`.
- **Flexible Input Resolution**: Accepts profile URLs (e.g. `https://fapello.com/naturabody/` or `fapello.com/naturabody/`), numeric model IDs (e.g. `713`), or handles/usernames.
- **Typo & Variant Tolerance**: Automatically resolves common phonetic typos and slug variations (e.g. `naturalbody` ➔ `naturabody`).
- **Full Media Support**: Downloads both original full-resolution photos and `.mp4` video files.
- **Smart Mirror Fallback**: Automatically tries live CDN servers and archive mirrors (`n1.fapello.com`, `fapello.com`, `cdn-n1.fapello.com`) to prevent download failures on newly posted or archived media.
- **Memory-Safe Streaming**: Video and large image downloads are streamed in chunks, maintaining low memory usage even across high thread counts.
- **Atomic File Writing**: Downloads to `.part` temporary files and renames upon full completion, preventing corrupted or incomplete files.
- **Fast Multi-threading**: Concurrently downloads media with connection pooling and exponential backoff retry.
- **Modern CLI**: Clean terminal interface with progress bars and summary metrics powered by `Rich` and `Questionary`.

---

## 📦 Installation

1. Ensure you have **Python 3.8+** installed.
2. Clone or open this repository.
3. Install dependencies:

```bash
pip install -r requirements.txt
```

---

## 🚀 Usage

### Option 1: Double-Click (Windows)
Simply double-click **`run.bat`** in the project folder.

### Option 2: Command Line
Run the tool from your terminal:

```bash
python main.py
```
*(On Windows, you can also use `py main.py`)*

### Input Examples:
- **Profile URL**: `https://fapello.com/merve-damla/` or `fapello.com/naturabody/`
- **Username / Handle**: `naturabody`, `merve-damla`, `mikaela`
- **Model ID**: `713`

The tool will:
1. Resolve the model profile and verify the media count.
2. Ask for confirmation to proceed.
3. Rapidly scan all pages for direct photo and video download links.
4. Concurrently download all media to `downloads/<model_name>/` with live progress bars.

---

## 🛠️ Project Structure

```text
FapelloDownloader/
├── main.py            # CLI entry point
├── requirements.txt   # Dependencies
└── fapello/           # Core package
    ├── __init__.py    # Package definition
    ├── api.py         # Multi-site scraping and API interaction logic
    ├── downloader.py  # Multi-threaded streaming downloader with mirror fallback
    └── ui.py          # Interactive terminal user interface
```
