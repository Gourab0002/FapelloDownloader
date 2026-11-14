import os
import re
from time import sleep
from urllib.parse import quote, urlparse
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from bs4 import BeautifulSoup
import urllib3

# Suppress insecure HTTPS request warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# Browser headers
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://fapello.com/"
}

# Known system routes on fapello.com that should never be treated as model profiles
SYSTEM_ROUTES = {
    'search', 'search_v2', 'search_by_photo', 'hot', 'new', 'trending', 'popular',
    'forum', 'tags', 'welcome', 'upload', 'login', 'signup', 'posts', 'videos',
    'random', 'top-uploaders', 'top-likes', 'top-followers', 'discussion', 'a',
    'contact', 'dmca', 'terms', 'privacy'
}

def create_api_session(referer="https://fapello.com/"):
    """Create a persistent HTTP session with retry logic and connection pooling."""
    session = requests.Session()
    retries = Retry(
        total=3,
        backoff_factor=0.3,
        status_forcelist=[408, 429, 500, 502, 503, 504],
        raise_on_status=False
    )
    adapter = HTTPAdapter(max_retries=retries, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    session.headers.update(HEADERS)
    session.headers["Referer"] = referer
    session.verify = False
    return session

def _extract_url_info(query):
    """
    Parse an input string to identify whether it is a URL and extract the domain and path.
    """
    q = query.strip()
    if q.startswith("fapello.") or q.startswith("www.fapello."):
        q = "https://" + q

    if "fapello." in q:
        m = re.search(r'fapello\.(\w+)/(.*)', q)
        if m:
            tld = m.group(1).lower()
            path = m.group(2).strip('/')
            return tld, path

    return None, None

def get_fapello_com_info(slug_or_query):
    """
    Retrieve model information from fapello.com.
    Supports direct profile URLs, search queries, and common typo correction.
    """
    session = create_api_session("https://fapello.com/")
    clean = re.sub(r'[^a-zA-Z0-9_-]', '', slug_or_query.strip('/')).lower()
    if not clean or clean in SYSTEM_ROUTES:
        return None

    def _fetch_profile(slug):
        if slug in SYSTEM_ROUTES:
            return None
        profile_url = f"https://fapello.com/{slug}/"
        try:
            r = session.get(profile_url, timeout=10, allow_redirects=True)
            if r.status_code == 200 and r.url.rstrip('/') == profile_url.rstrip('/'):
                soup = BeautifulSoup(r.text, "html.parser")
                title = soup.find('title')
                title_text = title.get_text(strip=True) if title else slug
                if "Page Not Found" in title_text or "Fapello" not in title_text:
                    return None

                media_count = 0
                media_div = soup.find(lambda tag: tag.name in ['div', 'span', 'strong'] and 'Media' in tag.get_text())
                if media_div:
                    m = re.search(r'(\d+)\s*Media', media_div.get_text())
                    if m:
                        media_count = int(m.group(1))

                # Count media tiles on page if media counter is absent
                tiles = [a for a in soup.find_all('a', href=True) if re.search(rf'/{slug}/\d+/?', a['href'])]
                if media_count == 0 and tiles:
                    media_count = len(tiles)

                # A valid model profile must have at least 1 media item
                if media_count == 0:
                    return None

                name = slug
                h2 = soup.find('h2')
                if h2 and h2.get_text(strip=True) and "Select your language" not in h2.get_text():
                    name = h2.get_text(strip=True)
                elif "Nude" in title_text:
                    name = title_text.split("Nude")[0].strip()

                return {
                    "id": slug,
                    "name": name,
                    "media_count": media_count,
                    "site": "fapello.com",
                    "slug": slug
                }
        except Exception:
            pass
        return None

    # 1. Try direct profile access
    info = _fetch_profile(clean)
    if info:
        return info

    # 2. Try common phonetic/spelling variants (e.g. naturalbody -> naturabody)
    variants = []
    if "natural" in clean:
        variants.append(clean.replace("natural", "natura"))
    if "natura" in clean and "natural" not in clean:
        variants.append(clean.replace("natura", "natural"))

    for v in variants:
        info = _fetch_profile(v)
        if info:
            return info

    # 3. Search endpoint (strictly match model cards with content avatar images)
    for q_term in [clean] + variants:
        search_url = f"https://fapello.com/search/{quote(q_term)}/"
        try:
            r = session.get(search_url, timeout=10)
            if r.status_code == 200:
                soup = BeautifulSoup(r.text, "html.parser")
                main = soup.find('div', class_='main_content') or soup
                for a in main.find_all('a', href=True):
                    href = a['href'].strip()
                    m = re.match(r'https?://fapello\.com/([a-zA-Z0-9_-]+)/?$', href)
                    if m:
                        found_slug = m.group(1).lower()
                        if found_slug in SYSTEM_ROUTES:
                            continue
                        img = a.find('img')
                        # Genuine model cards have thumbnails hosted under /content/
                        if img and '/content/' in img.get('src', ''):
                            info = _fetch_profile(found_slug)
                            if info and info['media_count'] > 0:
                                return info
        except Exception:
            pass

    return None

def get_fapello_to_info(query):
    """
    Retrieve model information from fapello.to.
    """
    session = create_api_session("https://fapello.to/")
    q = query.strip()
    model_id = None
    model_name = None

    if "/model/" in q:
        match = re.search(r'/model/(\d+)', q)
        if match:
            model_id = match.group(1)
    elif q.isdigit():
        model_id = q

    if not model_id:
        clean_q = q
        if "fapello.to/" in clean_q:
            clean_q = clean_q.split("fapello.to/")[-1].strip('/')
        clean_q = re.sub(r'[-_]+', ' ', clean_q).strip()

        search_url = f"https://fapello.to/search/{quote(clean_q)}"
        try:
            response = session.get(search_url, timeout=12)
            if response.status_code == 200:
                soup = BeautifulSoup(response.text, "html.parser")
                result_items = soup.find_all(class_="girlfound")
                if result_items:
                    for item in result_items:
                        link = item.find("a", href=re.compile(r'/model/\d+'))
                        if link:
                            match = re.search(r'/model/(\d+)', link["href"])
                            if match:
                                model_id = match.group(1)
                                text = link.get_text(strip=True)
                                if text:
                                    model_name = text
                                break
        except Exception:
            return None

    if not model_id:
        return None

    profile_url = f"https://fapello.to/model/{model_id}"
    media_count = 0
    slug = f"model_{model_id}"
    try:
        profile_resp = session.get(profile_url, timeout=12)
        if profile_resp.status_code == 200:
            p_soup = BeautifulSoup(profile_resp.text, "html.parser")
            try:
                count_el = p_soup.select_one('a[href*="/media/"] span.font-bold')
                if count_el:
                    media_count = int(re.sub(r'\D', '', count_el.get_text(strip=True)) or 0)
            except Exception:
                pass

            if not model_name:
                try:
                    h1_el = p_soup.find("h1")
                    if h1_el and h1_el.get_text(strip=True):
                        model_name = h1_el.get_text(strip=True)
                except Exception:
                    pass
    except Exception:
        pass

    if model_name:
        slug = re.sub(r'[\\/*?:"<>|]', "", model_name).strip()

    return {
        "id": model_id,
        "name": model_name if model_name else query,
        "media_count": media_count,
        "site": "fapello.to",
        "slug": slug
    }

def get_model_info(username_query):
    """
    Unified entry point: automatically resolves query across fapello.com and fapello.to.
    """
    if not username_query:
        return None

    query = str(username_query).strip()
    tld, path = _extract_url_info(query)

    if tld == "com":
        slug = path.split('/')[0] if path else ""
        return get_fapello_com_info(slug)
    elif tld == "to":
        return get_fapello_to_info(query)
    elif query.isdigit():
        return get_fapello_to_info(query)
    else:
        # If no domain is specified, check fapello.to first, then fallback to fapello.com
        info = get_fapello_to_info(query)
        if info and info.get('media_count', 0) > 0:
            return info
        return get_fapello_com_info(query)

def get_fapello_com_media_links(username, status_callback=None):
    """
    Scan fapello.com to extract all media (full-size photos and videos) links.
    """
    session = create_api_session("https://fapello.com/")
    profile_url = f"https://fapello.com/{username}/"
    page = 1
    all_media = []
    seen = set()

    while True:
        if page == 1:
            url = profile_url
        else:
            url = f"https://fapello.com/{username}/page-{page}/"

        if status_callback:
            status_callback(page)

        try:
            r = session.get(url, timeout=12, allow_redirects=True)
            if r.status_code != 200:
                break
            # If redirected back to profile on page > 1, all pages have been scanned
            if page > 1 and r.url.rstrip('/') == profile_url.rstrip('/'):
                break

            soup = BeautifulSoup(r.text, "html.parser")
            tiles = [a for a in soup.find_all('a', href=True) if re.search(rf'/{username}/\d+/?', a['href'])]
            if not tiles:
                break

            new_found = 0
            for tile in tiles:
                img = tile.find('img')
                if not img or not img.get('src'):
                    continue
                thumb = img['src']
                if '_300px' not in thumb and '_500px' not in thumb and '_1000' not in thumb:
                    continue

                is_video = 'icon-play' in str(tile) or tile.find(class_=re.compile(r'play|video', re.I)) is not None
                path = thumb.split("fapello.com")[-1]

                # Strip thumbnail dimension indicators (_300px, etc.)
                clean_path = re.sub(r'_\d+px\.', '.', path)

                if is_video:
                    media_url = f"https://cdn-n1.fapello.com{re.sub(r'\.\w+$', '.mp4', clean_path)}"
                else:
                    media_url = f"https://n1.fapello.com{re.sub(r'\.\w+$', '.jpg', clean_path)}"

                if media_url not in seen:
                    seen.add(media_url)
                    all_media.append(media_url)
                    new_found += 1

            if new_found == 0:
                break

            next_link = soup.find('a', href=re.compile(rf'page-{page+1}'))
            if not next_link:
                break

            page += 1
        except Exception:
            break

    return all_media

def get_fapello_to_media_links(model_id, status_callback=None):
    """
    Query the fapello.to API to retrieve all direct media links.
    """
    page = 1
    all_urls = []
    seen_urls = set()
    session = create_api_session("https://fapello.to/")
    api_template = "https://fapello.to/api/media/{}/{}/1/1"
    consecutive_empty_pages = 0

    while True:
        url = api_template.format(model_id, page)
        try:
            if status_callback:
                status_callback(page)

            response = session.get(url, timeout=12)
            if response.status_code != 200:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 3:
                    break
                page += 1
                continue

            try:
                data = response.json()
            except Exception:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 3:
                    break
                page += 1
                continue

            if not data or not isinstance(data, list):
                break

            count_in_page = 0
            for item in data:
                target_url = item.get('newUrl') or item.get('url')
                if target_url and target_url.strip():
                    clean_url = target_url.strip()
                    if clean_url not in seen_urls:
                        seen_urls.add(clean_url)
                        all_urls.append(clean_url)
                        count_in_page += 1

            if count_in_page == 0:
                consecutive_empty_pages += 1
                if consecutive_empty_pages >= 3:
                    break
            else:
                consecutive_empty_pages = 0

            page += 1
            if page % 10 == 0:
                sleep(0.2)

        except Exception:
            consecutive_empty_pages += 1
            if consecutive_empty_pages >= 3:
                break
            page += 1
            sleep(0.5)

    return all_urls

def get_image_links(model_id_or_info, status_callback=None):
    """
    Retrieve all media download links for a given model (supporting fapello.com and fapello.to).
    """
    site = None
    target_id = None

    if isinstance(model_id_or_info, dict):
        site = model_id_or_info.get("site")
        if site == "fapello.com":
            target_id = model_id_or_info.get("slug") or model_id_or_info.get("id")
        else:
            target_id = model_id_or_info.get("id")
    else:
        target_id = str(model_id_or_info)
        site = "fapello.to" if target_id.isdigit() else "fapello.com"

    if site == "fapello.com":
        return get_fapello_com_media_links(target_id, status_callback)
    else:
        return get_fapello_to_media_links(target_id, status_callback)
