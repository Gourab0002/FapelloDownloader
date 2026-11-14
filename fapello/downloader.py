import os
import re
from urllib.parse import urlparse
import requests
from concurrent.futures import ThreadPoolExecutor
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3

# Suppress SSL certificate warnings for CDNs with expired certs
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

class Downloader:
    def __init__(self, output_dir, max_workers=16):
        """
        Initialize the multi-threaded downloader.
        
        Args:
            output_dir (str): Destination folder for downloaded files
            max_workers (int): Maximum concurrent download threads
        """
        self.output_dir = output_dir
        self.max_workers = max_workers
        self.session = self._create_session()
        self.ensure_dir()

    def _create_session(self):
        """Create a resilient HTTP session with connection pooling and retries."""
        session = requests.Session()
        retries = Retry(
            total=4,
            backoff_factor=0.5,
            status_forcelist=[408, 429, 500, 502, 503, 504],
            raise_on_status=False
        )
        adapter = HTTPAdapter(
            max_retries=retries,
            pool_connections=self.max_workers,
            pool_maxsize=self.max_workers
        )
        session.mount('https://', adapter)
        session.mount('http://', adapter)
        session.verify = False
        session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://fapello.com/"
        })
        return session

    def ensure_dir(self):
        """Ensure the target destination directory exists."""
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    def _get_candidate_urls(self, url):
        """
        Generate candidate mirror URLs for a given media link.
        Handles mirror migration (fapello.com <-> n1.fapello.com <-> cdn-n1.fapello.com)
        and media format fallback (.jpg <-> .mp4).
        """
        candidates = [url]

        # Host mirror fallbacks for fapello.com
        if "n1.fapello.com" in url:
            candidates.append(url.replace("n1.fapello.com", "fapello.com"))
        elif "fapello.com" in url and "n1.fapello.com" not in url and "cdn-n1" not in url:
            candidates.append(url.replace("fapello.com", "n1.fapello.com"))

        if "cdn-n1.fapello.com" in url:
            candidates.append(url.replace("cdn-n1.fapello.com", "fapello.com"))
            candidates.append(url.replace("cdn-n1.fapello.com", "n1.fapello.com"))

        # Format fallbacks (e.g. video mistakenly detected as jpg or vice-versa)
        if url.endswith(".jpg") or url.endswith(".jpeg"):
            candidates.append(url.replace(".jpg", ".mp4").replace(".jpeg", ".mp4")
                                 .replace("n1.fapello.com", "cdn-n1.fapello.com")
                                 .replace("fapello.com", "cdn-n1.fapello.com"))
        elif url.endswith(".mp4"):
            candidates.append(url.replace(".mp4", ".jpg")
                                 .replace("cdn-n1.fapello.com", "n1.fapello.com")
                                 .replace("fapello.com", "n1.fapello.com"))

        # Deduplicate while preserving priority order
        seen = set()
        result = []
        for c in candidates:
            if c not in seen:
                seen.add(c)
                result.append(c)
        return result

    def download_image(self, url, progress_callback=None):
        """
        Download a single media file with mirror fallback and atomic disk writing.
        
        Args:
            url (str): Source media URL
            progress_callback (function): Optional progress update callback
            
        Returns:
            str: 'downloaded' | 'skipped' | 'failed'
        """
        status = 'failed'
        part_filepath = None

        try:
            candidates = self._get_candidate_urls(url)

            for target_url in candidates:
                try:
                    parsed = urlparse(target_url)
                    raw_filename = os.path.basename(parsed.path)
                    if not raw_filename:
                        raw_filename = f"{abs(hash(target_url))}.jpg"

                    # Clean filename for Windows/POSIX safety
                    clean_filename = re.sub(r'[\\/*?:"<>|]', "", raw_filename).strip('. ')
                    if not clean_filename:
                        clean_filename = f"media_{abs(hash(target_url))}.jpg"
                    filepath = os.path.join(self.output_dir, clean_filename)

                    # Skip if already downloaded and not empty
                    if os.path.exists(filepath) and os.path.getsize(filepath) > 0:
                        status = 'skipped'
                        return status

                    # Stream download to conserve memory for large videos
                    with self.session.get(target_url, timeout=(10, 30), stream=True, allow_redirects=True) as response:
                        if response.status_code == 200:
                            content_type = response.headers.get("content-type", "").lower()
                            # Reject HTML block or error pages
                            if "text/html" in content_type:
                                continue

                            part_filepath = filepath + ".part"
                            with open(part_filepath, 'wb') as f:
                                for chunk in response.iter_content(chunk_size=65536):
                                    if chunk:
                                        f.write(chunk)

                            # Verify that downloaded file has content
                            if os.path.exists(part_filepath) and os.path.getsize(part_filepath) > 0:
                                os.replace(part_filepath, filepath)
                                part_filepath = None
                                status = 'downloaded'
                                break
                            else:
                                if os.path.exists(part_filepath):
                                    os.remove(part_filepath)
                                    part_filepath = None
                except Exception:
                    if part_filepath and os.path.exists(part_filepath):
                        try:
                            os.remove(part_filepath)
                        except OSError:
                            pass
                        part_filepath = None
                    continue

        except Exception:
            status = 'failed'
        finally:
            if part_filepath and os.path.exists(part_filepath):
                try:
                    os.remove(part_filepath)
                except OSError:
                    pass
            if progress_callback:
                progress_callback(1)

        return status

    def download_all(self, urls, progress_task_id, progress_object):
        """
        Concurrently download a batch of media URLs.
        
        Args:
            urls (list): List of media URLs to download
            progress_task_id: Rich progress task ID
            progress_object: Rich progress instance
            
        Returns:
            dict: Download statistics
        """
        self.ensure_dir()

        def callback(completed_count):
            progress_object.update(progress_task_id, advance=completed_count)

        stats = {
            "total": len(urls),
            "downloaded": 0,
            "skipped": 0,
            "failed": 0
        }

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            futures = [executor.submit(self.download_image, url, callback) for url in urls]
            for future in futures:
                res = future.result()
                if res in stats:
                    stats[res] += 1
                else:
                    stats['failed'] += 1

        return stats
