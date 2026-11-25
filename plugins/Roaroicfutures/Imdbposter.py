# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import re
import difflib
import aiohttp
import warnings
import logging
from io import BytesIO
from urllib.parse import quote
from PIL import Image, ImageOps, ImageFilter
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

                # Preserve the full source poster. Portrait IMDb posters were
                # previously center-cropped into 16:9, cutting off artwork and text.
                source = Image.open(BytesIO(data)).convert("RGB")
                target_w, target_h = size
                if source.width / max(source.height, 1) > 1.45:
                    img = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
                else:
                    background = ImageOps.fit(source, size, method=Image.Resampling.LANCZOS)
                    background = background.filter(ImageFilter.GaussianBlur(radius=24))
                    foreground = ImageOps.contain(
                        source,
                        (int(target_w * 0.62), int(target_h * 0.92)),
                        method=Image.Resampling.LANCZOS
                    )
                    x = (target_w - foreground.width) // 2
                    y = (target_h - foreground.height) // 2
                    background.paste(foreground, (x, y))
                    img = background
                out = BytesIO()
                img.save(out, format="JPEG", quality=96, subsampling=0)
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

            results = ia.search_movie(title, results=30)
            if not results:
                logger.warning("IMDb found no results for title: %s", title)
                return None

            def norm_title(value):
                return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

            candidates = [
                item for item in results
                if item.get("kind") in ("movie", "tv series", "tv mini series", "tv movie", "tv short")
            ]
            if not candidates:
                candidates = results

            target = norm_title(title)
            exact = [item for item in candidates if norm_title(item.get("title")) == target]
            if year:
                exact_year = [item for item in exact if str(item.get("year", "")) == year]
                if exact_year:
                    exact = exact_year
                elif exact:
                    logger.warning("IMDb title matched but requested year %s did not; refusing ambiguous match for %s", year, title)
                    return None

            if exact:
                chosen = exact[0]
            else:
                scored = sorted(
                    ((difflib.SequenceMatcher(None, target, norm_title(item.get("title"))).ratio(), item)
                     for item in candidates),
                    key=lambda pair: pair[0],
                    reverse=True
                )
                if not scored or scored[0][0] < 0.88:
                    logger.warning("IMDb has no confident title match for %r", title)
                    return None
                best_score, chosen = scored[0]
                if year and str(chosen.get("year", "")) != year:
                    logger.warning("IMDb close title match has wrong year for %r; refusing poster/details", title)
                    return None
                logger.info("IMDb accepted close title match %r (score %.2f) for %r", chosen.get("title"), best_score, title)

            movie_id = chosen.movieID
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
    """Return artwork only for a confident IMDb title/year match."""
    try:
        raw_query = str(query or "").strip()
        year_match = re.search(r"\b([12]\d{3})\b\s*\)?$", raw_query)
        if not year and year_match:
            year = year_match.group(1)
        title = re.sub(r"\s*\(?[12]\d{3}\)?$", "", raw_query).strip()
        if not title:
            return None

        url = f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote(title.lower(), safe='')}.json"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept": "application/json,text/plain,*/*",
            "Referer": "https://www.imdb.com/"
        }
        timeout = aiohttp.ClientTimeout(total=12, connect=6)
        async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
            async with session.get(url, params={"includeVideos": "0"}) as response:
                if response.status != 200:
                    logger.warning("IMDb suggestion lookup HTTP %s for %s", response.status, title)
                    return None
                payload = await response.json(content_type=None)

        def norm_title(value):
            return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

        target = norm_title(title)
        items = payload.get("d", []) if isinstance(payload, dict) else []
        candidates = []
        for item in items:
            if not str(item.get("id", "")).startswith("tt"):
                continue
            if item.get("qid") not in (None, "movie", "tvSeries", "tvMiniSeries", "tvMovie", "tvEpisode"):
                continue
            image = item.get("i")
            if isinstance(image, list):
                image = {"imageUrl": image[0] if image else None}
            if not isinstance(image, dict) or not image.get("imageUrl"):
                continue
            candidates.append(item)

        exact = [item for item in candidates if norm_title(item.get("l")) == target]
        if year:
            exact_year = [item for item in exact if str(item.get("y", "")) == str(year)]
            if exact_year:
                exact = exact_year
            elif exact:
                logger.warning("IMDb suggestion title year mismatch for %s (%s)", title, year)
                return None

        if exact:
            chosen = exact[0]
        else:
            scored = sorted(
                ((difflib.SequenceMatcher(None, target, norm_title(item.get("l"))).ratio(), item)
                 for item in candidates),
                key=lambda pair: pair[0],
                reverse=True
            )
            if not scored or scored[0][0] < 0.90:
                logger.warning("IMDb suggestion has no confident exact-title match for %r", title)
                return None
            score, chosen = scored[0]
            if year and str(chosen.get("y", "")) != str(year):
                logger.warning("IMDb suggestion close match has wrong year for %r", title)
                return None
            logger.info("IMDb suggestion accepted close match %r (%.2f)", chosen.get("l"), score)

        image_url = chosen["i"]["imageUrl"]
        # IMDb image CDN accepts the V1 original-size form; avoid the tiny
        # autocomplete thumbnail when the original asset is available.
        image_url = re.sub(r"\._V1_[^./]*(?:_[^./]*)*(?=\.(?:jpg|jpeg|png|webp)(?:$|\?))", "._V1_", image_url, flags=re.I)
        logger.info("IMDb poster matched %r (%s)", chosen.get("l"), chosen.get("id"))
        return image_url
    except Exception as e:
        logger.warning("IMDb suggestion poster lookup failed for %r: %s", query, e)
        return None

async def get_movie_details(query, id=False, file=None):
    """IMDb metadata lookup; always try IMDb's own suggestion service for artwork."""
    import asyncio

    details = await asyncio.to_thread(_get_movie_details_sync, query, id, file)
    lookup_title = (details or {}).get("title") or query
    lookup_year = (details or {}).get("year")

    # This lookup is independent: it still runs when Cinemagoer cannot find a title.
    suggestion_poster = await _get_imdb_suggestion_poster(lookup_title, lookup_year)
    if not details:
        if suggestion_poster:
            logger.info("IMDb suggestion poster found for %r", query)
            return {"title": str(query), "poster_url": suggestion_poster}
        logger.warning("IMDb metadata and suggestion poster both unavailable for %r", query)
        return None

    if suggestion_poster:
        details["poster_url"] = suggestion_poster
        logger.info("IMDb suggestion poster found for %r", query)
    elif details.get("poster_url"):
        logger.info("IMDb Cinemagoer poster found for %r", query)
    else:
        logger.warning("IMDb returned metadata but no poster for %r", query)
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
                m = re.search(r'\b([12]\d{3})\b\)?\s*
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
                def norm_title(value):
                    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

                target = norm_title(title)
                ranked = []
                for item in results:
                    candidate_titles = [
                        item.get("title"), item.get("name"),
                        item.get("original_title"), item.get("original_name")
                    ]
                    score = max(
                        (difflib.SequenceMatcher(None, target, norm_title(value)).ratio()
                         for value in candidate_titles if value),
                        default=0
                    )
                    date_value = item.get("release_date") or item.get("first_air_date") or ""
                    item_year = date_value[:4] if len(date_value) >= 4 else ""
                    ranked.append((score, item_year == str(year) if year else True, item))
                ranked.sort(key=lambda entry: (entry[1], entry[0]), reverse=True)

                exact = [
                    entry for entry in ranked
                    if any(norm_title(value) == target for value in (
                        entry[2].get("title"), entry[2].get("name"),
                        entry[2].get("original_title"), entry[2].get("original_name")
                    ) if value)
                ]
                exact_year = [entry for entry in exact if entry[1]]
                if exact_year:
                    chosen_entry = exact_year[0]
                elif exact:
                    logger.warning("TMDB exact title found but year mismatch for %r (%s); refusing unrelated match", title, year)
                    return {"error": "TMDB title year mismatch"}
                elif ranked and ranked[0][0] >= 0.90 and ranked[0][1]:
                    chosen_entry = ranked[0]
                else:
                    logger.warning("TMDB has no confident title/year match for %r", q)
                    return {"error": "TMDB title match not confident"}

                chosen = chosen_entry[2]
                logger.info(
                    "TMDB accepted title %r year %s for query %r",
                    chosen.get("title") or chosen.get("name"),
                    chosen.get("release_date") or chosen.get("first_air_date"),
                    q
                )
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
, title)
                if m:
                    year = m.group(1)
                    title = re.sub(r'\s*\(?[12]\d{3}\)?\s*
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
                def norm_title(value):
                    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

                target = norm_title(title)
                ranked = []
                for item in results:
                    candidate_titles = [
                        item.get("title"), item.get("name"),
                        item.get("original_title"), item.get("original_name")
                    ]
                    score = max(
                        (difflib.SequenceMatcher(None, target, norm_title(value)).ratio()
                         for value in candidate_titles if value),
                        default=0
                    )
                    date_value = item.get("release_date") or item.get("first_air_date") or ""
                    item_year = date_value[:4] if len(date_value) >= 4 else ""
                    ranked.append((score, item_year == str(year) if year else True, item))
                ranked.sort(key=lambda entry: (entry[1], entry[0]), reverse=True)

                exact = [
                    entry for entry in ranked
                    if any(norm_title(value) == target for value in (
                        entry[2].get("title"), entry[2].get("name"),
                        entry[2].get("original_title"), entry[2].get("original_name")
                    ) if value)
                ]
                exact_year = [entry for entry in exact if entry[1]]
                if exact_year:
                    chosen_entry = exact_year[0]
                elif exact:
                    logger.warning("TMDB exact title found but year mismatch for %r (%s); refusing unrelated match", title, year)
                    return {"error": "TMDB title year mismatch"}
                elif ranked and ranked[0][0] >= 0.90 and ranked[0][1]:
                    chosen_entry = ranked[0]
                else:
                    logger.warning("TMDB has no confident title/year match for %r", q)
                    return {"error": "TMDB title match not confident"}

                chosen = chosen_entry[2]
                logger.info(
                    "TMDB accepted title %r year %s for query %r",
                    chosen.get("title") or chosen.get("name"),
                    chosen.get("release_date") or chosen.get("first_air_date"),
                    q
                )
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
, '', title).strip()
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
                def norm_title(value):
                    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

                target = norm_title(title)
                ranked = []
                for item in results:
                    candidate_titles = [
                        item.get("title"), item.get("name"),
                        item.get("original_title"), item.get("original_name")
                    ]
                    score = max(
                        (difflib.SequenceMatcher(None, target, norm_title(value)).ratio()
                         for value in candidate_titles if value),
                        default=0
                    )
                    date_value = item.get("release_date") or item.get("first_air_date") or ""
                    item_year = date_value[:4] if len(date_value) >= 4 else ""
                    ranked.append((score, item_year == str(year) if year else True, item))
                ranked.sort(key=lambda entry: (entry[1], entry[0]), reverse=True)

                exact = [
                    entry for entry in ranked
                    if any(norm_title(value) == target for value in (
                        entry[2].get("title"), entry[2].get("name"),
                        entry[2].get("original_title"), entry[2].get("original_name")
                    ) if value)
                ]
                exact_year = [entry for entry in exact if entry[1]]
                if exact_year:
                    chosen_entry = exact_year[0]
                elif exact:
                    logger.warning("TMDB exact title found but year mismatch for %r (%s); refusing unrelated match", title, year)
                    return {"error": "TMDB title year mismatch"}
                elif ranked and ranked[0][0] >= 0.90 and ranked[0][1]:
                    chosen_entry = ranked[0]
                else:
                    logger.warning("TMDB has no confident title/year match for %r", q)
                    return {"error": "TMDB title match not confident"}

                chosen = chosen_entry[2]
                logger.info(
                    "TMDB accepted title %r year %s for query %r",
                    chosen.get("title") or chosen.get("name"),
                    chosen.get("release_date") or chosen.get("first_air_date"),
                    q
                )
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
