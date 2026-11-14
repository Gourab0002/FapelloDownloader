from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.prompt import Prompt, Confirm
from .api import get_model_info, get_image_links
from .downloader import Downloader
import os
import re

console = Console()

def get_windows_clipboard():
    """Safely read text from the Windows system clipboard using ctypes (no dependencies)."""
    if os.name != 'nt':
        return None
    try:
        import ctypes
        u32 = ctypes.windll.user32
        k32 = ctypes.windll.kernel32
        CF_UNICODETEXT = 13
        u32.OpenClipboard.argtypes = [ctypes.c_void_p]
        u32.CloseClipboard.argtypes = []
        u32.GetClipboardData.argtypes = [ctypes.c_uint]
        u32.GetClipboardData.restype = ctypes.c_void_p
        k32.GlobalLock.argtypes = [ctypes.c_void_p]
        k32.GlobalLock.restype = ctypes.c_void_p
        k32.GlobalUnlock.argtypes = [ctypes.c_void_p]

        if u32.OpenClipboard(None):
            try:
                handle = u32.GetClipboardData(CF_UNICODETEXT)
                if handle:
                    ptr = k32.GlobalLock(handle)
                    if ptr:
                        try:
                            text = ctypes.c_wchar_p(ptr).value
                            if text:
                                clean = text.strip()
                                if clean and len(clean) < 200 and "\n" not in clean:
                                    return clean
                        finally:
                            k32.GlobalUnlock(handle)
            finally:
                u32.CloseClipboard()
    except Exception:
        pass
    return None

def enable_windows_quickedit():
    """Ensure QuickEdit and paste shortcuts are enabled in Windows console."""
    if os.name != 'nt':
        return
    try:
        import ctypes
        kernel32 = ctypes.windll.kernel32
        hIn = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_ulong()
        if kernel32.GetConsoleMode(hIn, ctypes.byref(mode)):
            # ENABLE_QUICK_EDIT_MODE (0x40) | ENABLE_EXTENDED_FLAGS (0x80) | ENABLE_INSERT_MODE (0x20)
            new_mode = mode.value | 0x0040 | 0x0080 | 0x0020
            kernel32.SetConsoleMode(hIn, new_mode)
    except Exception:
        pass

def print_banner():
    """Display the application banner."""
    banner = """
    [bold magenta]Fapello Downloader[/bold magenta]
    [cyan]Fast, Resilient & Multi-threaded Media Downloader[/cyan]
    """
    console.print(Panel(banner, border_style="magenta"))

def run_interactive():
    """Run the interactive command-line interface."""
    enable_windows_quickedit()
    print_banner()

    # Detect clipboard content to offer as quick default if it resembles a target
    clip_text = get_windows_clipboard()
    default_hint = None
    if clip_text and ("fapello." in clip_text or "/" in clip_text or clip_text.isdigit()):
        default_hint = clip_text

    prompt_msg = "[bold cyan]Enter target username, model ID, or profile URL[/bold cyan]"

    try:
        if default_hint:
            user_input = Prompt.ask(prompt_msg, default=default_hint)
        else:
            user_input = Prompt.ask(prompt_msg)
    except (KeyboardInterrupt, EOFError):
        console.print("\n[yellow]Operation cancelled by user.[/yellow]")
        return

    # Handle Ctrl+V in legacy CMD where it sends literal ASCII \x16 or ^V
    if user_input and ("\x16" in user_input or user_input == "^V"):
        if clip_text:
            user_input = clip_text
        else:
            user_input = user_input.replace("\x16", "").replace("^V", "").strip()

    if not user_input or not user_input.strip():
        console.print("[yellow]No input provided. Exiting.[/yellow]")
        return
    user_input = user_input.strip()

    # 2. Resolve model info
    info = None
    with console.status(f"[bold yellow]Resolving '{user_input}'...[/bold yellow]", spinner="dots"):
        info = get_model_info(user_input)

    if not info or info.get('media_count', 0) <= 0:
        console.print(f"[bold red]Error: User '{user_input}' not found or has no available media.[/bold red]")
        return

    model_id = info['id']
    target_name = info['name']
    media_count = info['media_count']
    site = info.get('site', 'fapello.com')

    console.print(Panel(f"""
    [bold cyan]Target Found[/bold cyan]
    Model Name: [green]{target_name}[/green]
    Model ID:   [green]{model_id}[/green]
    Estimated Media: [green]{media_count}[/green]
    Source Site:     [green]{site}[/green]
    """, border_style="green"))

    # 3. Confirmation prompt
    confirmed = Confirm.ask("[bold yellow]Start scanning and downloading?[/bold yellow]", default=True)
    if not confirmed:
        console.print("[yellow]Operation cancelled by user.[/yellow]")
        return

    # 4. Scan for media links
    all_urls = []
    per_page = 32 if site == "fapello.com" else 12
    total_pages_est = (media_count // per_page) + 1 if media_count else None

    console.print("[yellow]Scanning pages for media links...[/yellow]")

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed} Pages"),
        console=console
    ) as scan_progress:
        scan_task = scan_progress.add_task("[cyan]Scanning Pages[/cyan]", total=total_pages_est)

        def update_scan_status(page_num):
            scan_progress.update(scan_task, completed=page_num)

        all_urls = get_image_links(info, update_scan_status)

    if not all_urls:
        console.print("[bold red]Error: No media links could be retrieved.[/bold red]")
        return

    console.print(f"[bold green]Scan Complete! Found {len(all_urls)} media files.[/bold green]")

    # 5. Set up destination folder
    folder_slug = info.get('slug')
    if not folder_slug:
        folder_slug = re.sub(r'[\\/*?:"<>|]', "", target_name).strip()
    if not folder_slug:
        folder_slug = f"model_{model_id}"
    safe_folder = folder_slug[:60].rstrip('. ')
    output_dir = os.path.join(os.getcwd(), "downloads", safe_folder)

    console.print(f"Destination: [underline]{output_dir}[/underline]")

    # 6. Begin multi-threaded download
    downloader = Downloader(output_dir)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeRemainingColumn(),
        console=console
    ) as progress:
        task_id = progress.add_task("[cyan]Downloading Media[/cyan]", total=len(all_urls))
        stats = downloader.download_all(all_urls, task_id, progress)

    console.print(f"\n[bold green]All Done! Files saved to: {output_dir}[/bold green]")
    console.print(f"Summary: Downloaded [green]{stats.get('downloaded', 0)}[/green] | "
                  f"Skipped [yellow]{stats.get('skipped', 0)}[/yellow] | "
                  f"Failed [red]{stats.get('failed', 0)}[/red]")

    if stats.get('failed', 0) > 0:
        console.print(f"[yellow]Notice: {stats['failed']} file(s) could not be downloaded.[/yellow]")
