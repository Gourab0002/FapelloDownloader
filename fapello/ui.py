from rich.console import Console
from rich.progress import Progress, SpinnerColumn, BarColumn, TextColumn, TimeRemainingColumn
from rich.panel import Panel
from .api import get_model_info, get_image_links
from .downloader import Downloader
import os
import questionary
import re

console = Console()

def print_banner():
    """Display the application banner."""
    banner = """
    [bold magenta]Fapello Downloader[/bold magenta]
    [cyan]Fast, Resilient & Multi-threaded Media Downloader[/cyan]
    """
    console.print(Panel(banner, border_style="magenta"))

def run_interactive():
    """Run the interactive command-line interface."""
    print_banner()

    # 1. Prompt for username, model ID, or profile URL
    user_input = questionary.text(
        "[Enter target username, numeric model ID, or profile URL]:",
        qmark=""
    ).ask()

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
    confirmed = questionary.confirm("Start scanning and downloading?", default=True, qmark="").ask()
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
    # Truncate overly long directory names on Windows to prevent path overflow
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
