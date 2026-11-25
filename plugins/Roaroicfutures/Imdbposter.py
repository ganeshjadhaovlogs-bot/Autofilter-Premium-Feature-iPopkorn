# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import re
import aiohttp
import warnings
import logging
from io import BytesIO
from urllib.parse import quote
from PIL import Image, ImageOps
from info import ROAROIC_IMAGE_FETCH, TMDB_API_KEY
from imdb import Cinemagoer


logger = logging.getLogger(__name__)
ia = Cinemagoer()
LONG_IMDB_DESCRIPTION = False

def list_to_str(lst):
    if lst:
        return ", ".join(map(str, lst))
    return ""





Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter("ignore", Image.DecompressionBombWarning)
async def fetch_image(url, size=(860, 1200)):
    # Channel announcements require artwork; do not let a stale env toggle
    # silently disable IMDb/TMDB poster downloads.
    if not url:
        return None

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        "Referer": "https://www.imdb.com/"
    }
    try:
        timeout = aiohttp.ClientTimeout(total=25, connect=10)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url, allow_redirects=True) as response:
                if response.status != 200:
                    logger.error("Poster download failed: HTTP %s (%s)", response.status, url[:180])
                    return None
                content_type = response.headers.get("Content-Type", "").lower()
                data = await response.read()
                if not data:
                    logger.error("Poster URL returned an empty response: %s", url[:180])
                    return None

                # Some image CDNs label valid image bytes as application/octet-stream.
                # Let Pillow verify the actual payload instead of trusting Content-Type.
                img = Image.open(BytesIO(data)).convert("RGB")
                # Crop/resize without stretching so the final channel artwork stays 16:9.
                img = ImageOps.fit(img, size, method=Image.LANCZOS, centering=(0.5, 0.5))
                out = BytesIO()
                img.save(out, format="JPEG", quality=92)
                out.seek(0)
                out.name = "imdb_movie_poster.jpg"
                return out

    except aiohttp.ClientError as e:
        logger.error("Poster HTTP request error: %s", e)
    except (IOError, OSError) as e:
        logger.error("Poster image decode error: %s", e)
    except Exception as e:
        logger.exception("Unexpected poster fetch error: %s", e)

    return None


def _get_movie_details_sync(query, id=False, file=None):
    """Run Cinemagoer synchronously in a worker thread."""
    try:
        if not id:
            raw_query = str(query or "").strip()
            year_match = re.search(r'\b([12]\d{3})\)?$', raw_query)
            year = year_match.group(1) if year_match else None
            title = re.sub(r'\s*\(?[12]\d{3}\)?$', '', raw_query).strip()
            if not year and file:
                file_year = re.search(r'\b([12]\d{3})\b', str(file))
                year = file_year.group(1) if file_year else None
            if not title:
                title = raw_query

            results = ia.search_movie(title, results=15)
            if not results:
                logger.warning("IMDb found no results for title: %s", title)
                return None

            candidates = [
                item for item in results
                if item.get("kind") in ("movie", "tv series", "tv mini series", "tv movie")
            ] or results
            if year:
                year_matches = [item for item in candidates if str(item.get("year", "")) == year]
                if year_matches:
                    candidates = year_matches
            movie_id = candidates[0].movieID
        else:
            movie_id = str(query).removeprefix("tt")

        movie = ia.get_movie(movie_id)
        ia.update(movie, info=["main", "vote details"])
        plot = movie.get("plot") or movie.get("plot outline")
        if isinstance(plot, list):
            plot = plot[0] if plot else None
        if plot and len(plot) > 800:
            plot = plot[:800] + "..."

        imdb_id = str(movie.get("imdbID") or movie_id)
        return {
            "title": movie.get("title"),
            "votes": movie.get("votes"),
            "aka": list_to_str(movie.get("akas")),
            "seasons": movie.get("number of seasons"),
            "box_office": movie.get("box office"),
            "localized_title": movie.get("localized title"),
            "kind": movie.get("kind"),
            "imdb_id": f"tt{imdb_id}",
            "cast": list_to_str(movie.get("cast")),
            "runtime": list_to_str(movie.get("runtimes")),
            "countries": list_to_str(movie.get("countries")),
            "certificates": list_to_str(movie.get("certificates")),
            "languages": list_to_str(movie.get("languages")),
            "director": list_to_str(movie.get("director")),
            "writer": list_to_str(movie.get("writer")),
            "producer": list_to_str(movie.get("producer")),
            "composer": list_to_str(movie.get("composer")),
            "cinematographer": list_to_str(movie.get("cinematographer")),
            "music_team": list_to_str(movie.get("music department")),
            "distributors": list_to_str(movie.get("distributors")),
            "release_date": movie.get("original air date") or movie.get("year") or "N/A",
            "year": movie.get("year"),
            "genres": list_to_str(movie.get("genres")),
            "poster_url": movie.get("full-size cover url") or movie.get("cover url"),
            "plot": plot,
            "rating": str(movie.get("rating") or "N/A"),
            "url": f"https://www.imdb.com/title/tt{imdb_id}"
        }
    except Exception as e:
        logger.exception("IMDb lookup failed for %r: %s", query, e)
        return None


async def _get_imdb_suggestion_poster(query, year=None):
    """Get the poster image URL from IMDb's public title-suggestion response."""
    try:
        title = re.sub(r'\\s*\\(?[12]\\d{3}\\)?

TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"


def _tmdb_auth():
    """Supports both TMDB v3 API key and v4 'Read Access Token' (starts with eyJ)."""
    key = (TMDB_API_KEY or "").strip()
    if key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}", "accept": "application/json"}, {}
    return {"accept": "application/json"}, {"api_key": key}


async def _tmdb_get(session, path, **params):
    headers, auth_params = _tmdb_auth()
    params.update(auth_params)
    async with session.get(f"{TMDB_API}{path}", params=params, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            text = await resp.text()
            logger.error(f"TMDB request failed [{resp.status}] {path}: {text[:200]}")
            return None
        return await resp.json()


def _img(path, size="original"):
    return f"{TMDB_IMG}/{size}{path}" if path else None


def _pick_image(items, lang):
    """Best image path: preferred language first, then language-less, then anything."""
    if not items:
        return None
    for want in ("en", lang, None):
        for it in items:
            if it.get("iso_639_1") == want and it.get("file_path"):
                return it["file_path"]
    return items[0].get("file_path")


async def get_movie_detailsx(query, id=False, file=None):
    """
    Fetch details + poster/backdrop straight from the official TMDB API.
    ALWAYS returns a dict. On failure -> {"error": "..."} (never None),
    so callers can safely fall back to IMDb.
    """
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("http"):
        return {"error": "TMDB_API_KEY is not set (get one from https://www.themoviedb.org/settings/api)"}

    q = str(query).strip()
    try:
        async with aiohttp.ClientSession() as session:
            media_type, tmdb_id = None, None

            if id:
                if q.startswith("tt"):
                    found = await _tmdb_get(session, f"/find/{q}", external_source="imdb_id")
                    if found:
                        for kind, key in (("movie", "movie_results"), ("tv", "tv_results")):
                            if found.get(key):
                                media_type, tmdb_id = kind, found[key][0]["id"]
                                break
                elif q.isdigit():
                    tmdb_id = int(q)
                    media_type = "movie" if await _tmdb_get(session, f"/movie/{q}") else "tv"
            else:
                title = q.lower()
                year = None
                m = re.search(r'\b([12]\d{3})\b\s*$', title)
                if m:
                    year = m.group(1)
                    title = title[:m.start()].strip()
                elif file:
                    m = re.search(r'\b([12]\d{3})\b', file)
                    if m:
                        year = m.group(1)
                if not title:
                    title = q.lower()

                res = await _tmdb_get(session, "/search/multi", query=title, include_adult="false")
                results = [r for r in (res or {}).get("results", []) if r.get("media_type") in ("movie", "tv")]
                if not results:
                    return {"error": f"No TMDB result for '{q}'"}
                chosen = results[0]
                if year:
                    for r in results:
                        d = r.get("release_date") or r.get("first_air_date") or ""
                        if d.startswith(year):
                            chosen = r
                            break
                media_type, tmdb_id = chosen["media_type"], chosen["id"]

            if not tmdb_id or not media_type:
                return {"error": f"TMDB id not found for '{q}'"}

            extra = "credits,images,external_ids," + ("release_dates" if media_type == "movie" else "content_ratings")
            data = await _tmdb_get(session, f"/{media_type}/{tmdb_id}",
                                   append_to_response=extra,
                                   include_image_language="en,null,hi")
            if not data:
                return {"error": f"TMDB details failed for id {tmdb_id}"}
    except Exception as e:
        logger.error(f"An error occurred in get_movie_detailsx: {e}")
        return {"error": str(e)}

    credits = data.get("credits") or {}
    crew = credits.get("crew") or []

    def crew_of(*jobs):
        return [c["name"] for c in crew if c.get("job") in jobs and c.get("name")]

    is_movie = media_type == "movie"
    date = data.get("release_date") if is_movie else data.get("first_air_date")
    year_val = int(date[:4]) if date and date[:4].isdigit() else None
    runtime = data.get("runtime") if is_movie else (data.get("episode_run_time") or [None])[0]

    cert = None
    try:
        if is_movie:
            for c in (data.get("release_dates") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US"):
                    for r in c.get("release_dates", []):
                        if r.get("certification"):
                            cert = r["certification"]
                            break
                if cert:
                    break
        else:
            for c in (data.get("content_ratings") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US") and c.get("rating"):
                    cert = c["rating"]
                    break
    except Exception:
        pass

    lang = data.get("original_language")
    images = data.get("images") or {}
    poster_path = _pick_image(images.get("posters"), lang) or data.get("poster_path")
    backdrop_path = _pick_image(images.get("backdrops"), lang) or data.get("backdrop_path")

    return {
        "title": data.get("title") or data.get("name"),
        "localized_title": data.get("original_title") or data.get("original_name"),
        "year": year_val,
        "release_date": date,
        "rating": round(float(data["vote_average"]), 1) if data.get("vote_average") else None,
        "votes": int(data.get("vote_count") or 0),
        "runtime": f"{runtime} min" if runtime else None,
        "certificates": cert,
        "tmdb_url": f"https://www.themoviedb.org/{media_type}/{tmdb_id}",
        "genres": [g["name"] for g in data.get("genres", [])],
        "languages": [l.get("english_name") or l.get("name") for l in data.get("spoken_languages", [])],
        "countries": [c["name"] for c in data.get("production_countries", [])] if is_movie
                     else list(data.get("origin_country") or []),
        "director": crew_of("Director") if is_movie else [c["name"] for c in data.get("created_by", [])],
        "writer": crew_of("Writer", "Screenplay", "Story"),
        "producer": crew_of("Producer", "Executive Producer"),
        "composer": crew_of("Original Music Composer", "Composer"),
        "cinematographer": crew_of("Director of Photography"),
        "cast": [c["name"] for c in (credits.get("cast") or [])[:10] if c.get("name")],
        "plot": data.get("overview"),
        "tagline": data.get("tagline"),
        "box_office": data.get("revenue") or None,
        "seasons": data.get("number_of_seasons"),
        "distributors": [c["name"] for c in data.get("production_companies", [])],
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id"),
        "tmdb_id": tmdb_id,
        "poster_url": _img(poster_path),
        "backdrop_url": _img(backdrop_path),
    }
, '', str(query or '')).strip()
        if not title:
            return None
        url = f"https://v2.sg.media-imdb.com/suggestion/x/{quote(title, safe='')}.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.imdb.com/"
        }
        timeout = aiohttp.ClientTimeout(total=12, connect=6)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url) as response:
                if response.status != 200:
                    logger.warning("IMDb suggestion lookup returned HTTP %s for %s", response.status, title)
                    return None
                payload = await response.json(content_type=None)

        items = payload.get("d", []) if isinstance(payload, dict) else []
        title_key = re.sub(r'[^a-z0-9]+', '', title.lower())
        candidates = [
            item for item in items
            if str(item.get("id", "")).startswith("tt") and item.get("i", {}).get("imageUrl")
        ]
        if year:
            year_matches = [item for item in candidates if str(item.get("y", "")) == str(year)]
            if year_matches:
                candidates = year_matches
        exact = [
            item for item in candidates
            if re.sub(r'[^a-z0-9]+', '', str(item.get("l", "")).lower()) == title_key
        ]
        selected = (exact or candidates)
        return selected[0]["i"]["imageUrl"] if selected else None
    except Exception as e:
        logger.warning("IMDb suggestion poster lookup failed for %r: %s", query, e)
        return None


async def get_movie_details(query, id=False, file=None):
    """Async IMDb lookup with a second IMDb-native poster lookup as fallback."""
    import asyncio
    details = await asyncio.to_thread(_get_movie_details_sync, query, id, file)
    if not details:
        return details

    # Prefer the poster returned by IMDb's suggestion service; Cinemagoer remains
    # the source for the rest of the metadata.
    suggestion_poster = await _get_imdb_suggestion_poster(
        details.get("title") or query,
        details.get("year")
    )
    if suggestion_poster:
        details["poster_url"] = suggestion_poster
    return details


TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"


def _tmdb_auth():
    """Supports both TMDB v3 API key and v4 'Read Access Token' (starts with eyJ)."""
    key = (TMDB_API_KEY or "").strip()
    if key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}", "accept": "application/json"}, {}
    return {"accept": "application/json"}, {"api_key": key}


async def _tmdb_get(session, path, **params):
    headers, auth_params = _tmdb_auth()
    params.update(auth_params)
    async with session.get(f"{TMDB_API}{path}", params=params, headers=headers,
                           timeout=aiohttp.ClientTimeout(total=20)) as resp:
        if resp.status != 200:
            text = await resp.text()
            logger.error(f"TMDB request failed [{resp.status}] {path}: {text[:200]}")
            return None
        return await resp.json()


def _img(path, size="original"):
    return f"{TMDB_IMG}/{size}{path}" if path else None


def _pick_image(items, lang):
    """Best image path: preferred language first, then language-less, then anything."""
    if not items:
        return None
    for want in ("en", lang, None):
        for it in items:
            if it.get("iso_639_1") == want and it.get("file_path"):
                return it["file_path"]
    return items[0].get("file_path")


async def get_movie_detailsx(query, id=False, file=None):
    """
    Fetch details + poster/backdrop straight from the official TMDB API.
    ALWAYS returns a dict. On failure -> {"error": "..."} (never None),
    so callers can safely fall back to IMDb.
    """
    if not TMDB_API_KEY or TMDB_API_KEY.startswith("http"):
        return {"error": "TMDB_API_KEY is not set (get one from https://www.themoviedb.org/settings/api)"}

    q = str(query).strip()
    try:
        async with aiohttp.ClientSession() as session:
            media_type, tmdb_id = None, None

            if id:
                if q.startswith("tt"):
                    found = await _tmdb_get(session, f"/find/{q}", external_source="imdb_id")
                    if found:
                        for kind, key in (("movie", "movie_results"), ("tv", "tv_results")):
                            if found.get(key):
                                media_type, tmdb_id = kind, found[key][0]["id"]
                                break
                elif q.isdigit():
                    tmdb_id = int(q)
                    media_type = "movie" if await _tmdb_get(session, f"/movie/{q}") else "tv"
            else:
                title = q.lower()
                year = None
                m = re.search(r'\b([12]\d{3})\b\s*$', title)
                if m:
                    year = m.group(1)
                    title = title[:m.start()].strip()
                elif file:
                    m = re.search(r'\b([12]\d{3})\b', file)
                    if m:
                        year = m.group(1)
                if not title:
                    title = q.lower()

                res = await _tmdb_get(session, "/search/multi", query=title, include_adult="false")
                results = [r for r in (res or {}).get("results", []) if r.get("media_type") in ("movie", "tv")]
                if not results:
                    return {"error": f"No TMDB result for '{q}'"}
                chosen = results[0]
                if year:
                    for r in results:
                        d = r.get("release_date") or r.get("first_air_date") or ""
                        if d.startswith(year):
                            chosen = r
                            break
                media_type, tmdb_id = chosen["media_type"], chosen["id"]

            if not tmdb_id or not media_type:
                return {"error": f"TMDB id not found for '{q}'"}

            extra = "credits,images,external_ids," + ("release_dates" if media_type == "movie" else "content_ratings")
            data = await _tmdb_get(session, f"/{media_type}/{tmdb_id}",
                                   append_to_response=extra,
                                   include_image_language="en,null,hi")
            if not data:
                return {"error": f"TMDB details failed for id {tmdb_id}"}
    except Exception as e:
        logger.error(f"An error occurred in get_movie_detailsx: {e}")
        return {"error": str(e)}

    credits = data.get("credits") or {}
    crew = credits.get("crew") or []

    def crew_of(*jobs):
        return [c["name"] for c in crew if c.get("job") in jobs and c.get("name")]

    is_movie = media_type == "movie"
    date = data.get("release_date") if is_movie else data.get("first_air_date")
    year_val = int(date[:4]) if date and date[:4].isdigit() else None
    runtime = data.get("runtime") if is_movie else (data.get("episode_run_time") or [None])[0]

    cert = None
    try:
        if is_movie:
            for c in (data.get("release_dates") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US"):
                    for r in c.get("release_dates", []):
                        if r.get("certification"):
                            cert = r["certification"]
                            break
                if cert:
                    break
        else:
            for c in (data.get("content_ratings") or {}).get("results", []):
                if c.get("iso_3166_1") in ("IN", "US") and c.get("rating"):
                    cert = c["rating"]
                    break
    except Exception:
        pass

    lang = data.get("original_language")
    images = data.get("images") or {}
    poster_path = _pick_image(images.get("posters"), lang) or data.get("poster_path")
    backdrop_path = _pick_image(images.get("backdrops"), lang) or data.get("backdrop_path")

    return {
        "title": data.get("title") or data.get("name"),
        "localized_title": data.get("original_title") or data.get("original_name"),
        "year": year_val,
        "release_date": date,
        "rating": round(float(data["vote_average"]), 1) if data.get("vote_average") else None,
        "votes": int(data.get("vote_count") or 0),
        "runtime": f"{runtime} min" if runtime else None,
        "certificates": cert,
        "tmdb_url": f"https://www.themoviedb.org/{media_type}/{tmdb_id}",
        "genres": [g["name"] for g in data.get("genres", [])],
        "languages": [l.get("english_name") or l.get("name") for l in data.get("spoken_languages", [])],
        "countries": [c["name"] for c in data.get("production_countries", [])] if is_movie
                     else list(data.get("origin_country") or []),
        "director": crew_of("Director") if is_movie else [c["name"] for c in data.get("created_by", [])],
        "writer": crew_of("Writer", "Screenplay", "Story"),
        "producer": crew_of("Producer", "Executive Producer"),
        "composer": crew_of("Original Music Composer", "Composer"),
        "cinematographer": crew_of("Director of Photography"),
        "cast": [c["name"] for c in (credits.get("cast") or [])[:10] if c.get("name")],
        "plot": data.get("overview"),
        "tagline": data.get("tagline"),
        "box_office": data.get("revenue") or None,
        "seasons": data.get("number_of_seasons"),
        "distributors": [c["name"] for c in data.get("production_companies", [])],
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id"),
        "tmdb_id": tmdb_id,
        "poster_url": _img(poster_path),
        "backdrop_url": _img(backdrop_path),
    }
