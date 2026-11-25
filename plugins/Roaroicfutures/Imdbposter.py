# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import re
import json
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

                source = Image.open(BytesIO(data)).convert("RGB")
                target_w, target_h = size
                aspect_ratio = source.width / max(source.height, 1)

                if aspect_ratio >= 1.35:
                    # TMDB landscape backdrops (e.g. 1200x675) are already
                    # channel thumbnails. Show the complete image edge-to-edge:
                    # no portrait overlay, no blurred side panels.
                    img = ImageOps.contain(
                        source, size, method=Image.Resampling.LANCZOS
                    )
                    canvas = Image.new("RGB", size, (0, 0, 0))
                    x = (target_w - img.width) // 2
                    y = (target_h - img.height) // 2
                    canvas.paste(img, (x, y))
                    img = canvas
                else:
                    # Keep the existing portrait-poster treatment only when
                    # TMDB has no landscape backdrop available.
                    background = ImageOps.fit(
                        source, size, method=Image.Resampling.LANCZOS
                    ).filter(ImageFilter.GaussianBlur(radius=24))
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

async def _get_imdb_online_metadata(query, year=None, imdb_id=None):
    """Read core metadata from IMDb's title JSON-LD when IMDb permits the request."""
    try:
        raw_query = str(query or "").strip()
        title = re.sub(r"\s*\(?((?:19|20)\d{2})\)?\s*$", "", raw_query).strip()
        year_match = re.search(r"\b((?:19|20)\d{2})\b", raw_query)
        year = str(year or (year_match.group(1) if year_match else "")) or None

        def norm(value):
            return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

        if not imdb_id:
            suggestion_url = f"https://v3.sg.media-imdb.com/suggestion/titles/x/{quote(title.lower(), safe='')}.json"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
                "Accept": "application/json,text/plain,*/*",
                "Referer": "https://www.imdb.com/"
            }
            async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as session:
                async with session.get(suggestion_url) as response:
                    if response.status != 200:
                        return None
                    payload = await response.json(content_type=None)
                items = [
                    item for item in payload.get("d", [])
                    if str(item.get("id", "")).startswith("tt")
                    and item.get("qid") in (None, "movie", "tvSeries", "tvMiniSeries", "tvMovie", "tvEpisode")
                ]
                exact = [item for item in items if norm(item.get("l")) == norm(title)]
                if year:
                    exact_year = [item for item in exact if str(item.get("y", "")) == year]
                    if exact_year:
                        exact = exact_year
                    elif exact:
                        return None
                if exact:
                    chosen = exact[0]
                else:
                    ranked = sorted(
                        ((difflib.SequenceMatcher(None, norm(title), norm(item.get("l"))).ratio(), item)
                         for item in items),
                        key=lambda pair: pair[0], reverse=True
                    )
                    if not ranked or ranked[0][0] < 0.90:
                        return None
                    chosen = ranked[0][1]
                    if year and str(chosen.get("y", "")) != year:
                        return None
                imdb_id = chosen.get("id")
        else:
            imdb_id = str(imdb_id)
            if not imdb_id.startswith("tt"):
                imdb_id = f"tt{imdb_id}"

        if not imdb_id:
            return None

        page_url = f"https://www.imdb.com/title/{imdb_id}/"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0 Safari/537.36",
            "Accept": "text/html,application/xhtml+xml,*/*",
            "Referer": "https://www.imdb.com/"
        }
        async with aiohttp.ClientSession(headers=headers, timeout=aiohttp.ClientTimeout(total=18)) as session:
            async with session.get(page_url, allow_redirects=True) as response:
                if response.status != 200:
                    logger.warning("IMDb title metadata HTTP %s for %s", response.status, imdb_id)
                    return None
                html = await response.text(errors="ignore")

        scripts = re.findall(
            r"<script[^>]+type=['\"]application/ld\+json['\"][^>]*>(.*?)</script>",
            html, flags=re.I | re.S
        )
        objects = []
        for raw in scripts:
            try:
                parsed = json.loads(raw.strip())
                objects.extend(parsed if isinstance(parsed, list) else [parsed])
            except (ValueError, TypeError):
                continue

        def find_title_object(value):
            if isinstance(value, dict):
                kind = value.get("@type")
                kinds = kind if isinstance(kind, list) else [kind]
                if any(k in ("Movie", "TVSeries", "TVEpisode", "TVMiniSeries") for k in kinds):
                    return value
                for child in value.values():
                    found = find_title_object(child)
                    if found:
                        return found
            elif isinstance(value, list):
                for child in value:
                    found = find_title_object(child)
                    if found:
                        return found
            return None

        data = next((find_title_object(item) for item in objects if find_title_object(item)), None)
        if not data:
            logger.warning("IMDb title JSON-LD metadata unavailable for %s", imdb_id)
            return None

        duration = data.get("duration") or ""
        duration_match = re.fullmatch(r"PT(?:(\d+)H)?(?:(\d+)M)?", duration)
        runtime = None
        if duration_match:
            hours = int(duration_match.group(1) or 0)
            minutes = int(duration_match.group(2) or 0)
            runtime = f"{hours}h {minutes}m" if hours and minutes else (
                f"{hours}h" if hours else f"{minutes}m" if minutes else None
            )

        aggregate = data.get("aggregateRating") or {}
        rating = aggregate.get("ratingValue") if isinstance(aggregate, dict) else None
        genres = data.get("genre") or []
        if isinstance(genres, str):
            genres = [genres]
        languages = data.get("inLanguage") or []
        if isinstance(languages, str):
            languages = [languages]

        result = {
            "imdb_id": imdb_id,
            "url": page_url,
            "title": data.get("name"),
            "genres": ", ".join(str(item) for item in genres if item) or None,
            "rating": str(round(float(rating), 1)) if rating else None,
            "runtime": runtime,
            "languages": ", ".join(str(item) for item in languages if item) or None,
            "poster_url": data.get("image")
        }
        logger.info("IMDb online metadata parsed for %s: genres=%s rating=%s runtime=%s",
                    imdb_id, bool(result["genres"]), result["rating"], result["runtime"])
        return {key: value for key, value in result.items() if value not in (None, "", [])}
    except Exception as error:
        logger.warning("IMDb online metadata lookup failed for %r: %s", query, error)
        return None


async def get_movie_details(query, id=False, file=None):
    """IMDb metadata lookup; always try IMDb's own suggestion service for artwork."""
    import asyncio

    details = await asyncio.to_thread(_get_movie_details_sync, query, id, file)
    lookup_title = (details or {}).get("title") or query
    lookup_year = (details or {}).get("year")

    # IMDb's current title page JSON-LD supplies live genres, rating and runtime.
    online_details = await _get_imdb_online_metadata(
        lookup_title, lookup_year, (details or {}).get("imdb_id")
    )
    suggestion_poster = await _get_imdb_suggestion_poster(lookup_title, lookup_year)

    if not details:
        details = {"title": str(query)} if (online_details or suggestion_poster) else None
    if not details:
        logger.warning("IMDb metadata and poster unavailable for %r", query)
        return None

    if online_details:
        for key, value in online_details.items():
            if value not in (None, "", [], "N/A"):
                details[key] = value

    if suggestion_poster and not details.get("poster_url"):
        details["poster_url"] = suggestion_poster
    if suggestion_poster:
        logger.info("IMDb suggestion poster found for %r", query)
    return details


TMDB_API = "https://api.themoviedb.org/3"
TMDB_IMG = "https://image.tmdb.org/t/p"


def _tmdb_auth():
    """Support TMDB v3 API keys and v4 read access tokens."""
    key = (TMDB_API_KEY or "").strip()
    if key.startswith("eyJ"):
        return {"Authorization": f"Bearer {key}", "accept": "application/json"}, {}
    return {"accept": "application/json"}, {"api_key": key}


async def _tmdb_get(session, path, **params):
    headers, auth_params = _tmdb_auth()
    params.update(auth_params)
    async with session.get(
        f"{TMDB_API}{path}",
        params=params,
        headers=headers,
        timeout=aiohttp.ClientTimeout(total=20)
    ) as response:
        if response.status != 200:
            body = await response.text()
            logger.error("TMDB request failed [%s] %s: %s", response.status, path, body[:200])
            return None
        return await response.json()


def _img(path, size="original"):
    return f"{TMDB_IMG}/{size}{path}" if path else None


def _pick_image(items, language):
    if not items:
        return None
    for wanted in ("en", language, None):
        for item in items:
            if item.get("iso_639_1") == wanted and item.get("file_path"):
                return item["file_path"]
    return next((item.get("file_path") for item in items if item.get("file_path")), None)


async def get_movie_detailsx(query, id=False, file=None):
    """Fetch verified movie/series metadata and India streaming-provider data from TMDB."""
    if not TMDB_API_KEY or str(TMDB_API_KEY).startswith("http"):
        return {"error": "TMDB_API_KEY is not configured"}

    raw_query = str(query or "").strip()
    title = raw_query
    year = None

    if not id:
        year_match = re.search(r"\b((?:19|20)\d{2})\b", raw_query)
        if year_match:
            year = year_match.group(1)
            title = re.sub(r"\s*\(?((?:19|20)\d{2})\)?\s*$", "", raw_query).strip()
        elif file:
            file_year = re.search(r"\b((?:19|20)\d{2})\b", str(file))
            if file_year:
                year = file_year.group(1)
        title = title or raw_query

    try:
        async with aiohttp.ClientSession() as session:
            media_type = None
            tmdb_id = None

            if id:
                if raw_query.startswith("tt"):
                    found = await _tmdb_get(session, f"/find/{raw_query}", external_source="imdb_id")
                    if found:
                        for kind, key in (("movie", "movie_results"), ("tv", "tv_results")):
                            if found.get(key):
                                media_type = kind
                                tmdb_id = found[key][0].get("id")
                                break
                elif raw_query.isdigit():
                    tmdb_id = int(raw_query)
                    media_type = "movie"
            else:
                search = await _tmdb_get(
                    session, "/search/multi",
                    query=title, include_adult="false"
                )
                results = [
                    item for item in (search or {}).get("results", [])
                    if item.get("media_type") in ("movie", "tv")
                ]
                if not results:
                    return {"error": f"No TMDB result for {title}"}

                def normalize_title(value):
                    return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

                target = normalize_title(title)
                ranked = []
                for item in results:
                    names = (
                        item.get("title"), item.get("name"),
                        item.get("original_title"), item.get("original_name")
                    )
                    score = max(
                        (difflib.SequenceMatcher(None, target, normalize_title(name)).ratio()
                         for name in names if name),
                        default=0
                    )
                    date_value = item.get("release_date") or item.get("first_air_date") or ""
                    item_year = date_value[:4] if len(date_value) >= 4 else ""
                    ranked.append((score, item_year == str(year) if year else True, item))

                exact = [
                    entry for entry in ranked
                    if any(normalize_title(name) == target for name in (
                        entry[2].get("title"), entry[2].get("name"),
                        entry[2].get("original_title"), entry[2].get("original_name")
                    ) if name)
                ]
                exact_year = [entry for entry in exact if entry[1]]

                if exact_year:
                    chosen = exact_year[0][2]
                elif exact and not year:
                    chosen = exact[0][2]
                elif not year and ranked:
                    ranked.sort(key=lambda entry: (entry[0], int(entry[2].get("vote_count") or 0)), reverse=True)
                    chosen = ranked[0][2] if ranked[0][0] >= 0.92 else None
                else:
                    ranked.sort(key=lambda entry: (entry[1], entry[0]), reverse=True)
                    chosen = ranked[0][2] if ranked and ranked[0][1] and ranked[0][0] >= 0.92 else None

                if not chosen:
                    logger.warning("TMDB refused an uncertain title/year match for %r", raw_query)
                    return {"error": "No confident TMDB title/year match"}

                media_type = chosen.get("media_type")
                tmdb_id = chosen.get("id")
                logger.info(
                    "TMDB matched %r (%s) for %r",
                    chosen.get("title") or chosen.get("name"),
                    chosen.get("release_date") or chosen.get("first_air_date"),
                    raw_query
                )

            if not tmdb_id or not media_type:
                return {"error": f"TMDB id not found for {raw_query}"}

            append = "credits,images,external_ids"
            append += ",release_dates" if media_type == "movie" else ",content_ratings"
            data = await _tmdb_get(
                session,
                f"/{media_type}/{tmdb_id}",
                append_to_response=append,
                include_image_language="en,null,hi"
            )
            if not data:
                return {"error": f"TMDB details unavailable for {raw_query}"}

            # Streaming availability is region-specific; use India as the bot's
            # configured audience region. Only streaming/free/ad providers are listed.
            watch_data = await _tmdb_get(session, f"/{media_type}/{tmdb_id}/watch/providers")
    except Exception as error:
        logger.exception("TMDB lookup failed for %r: %s", raw_query, error)
        return {"error": str(error)}

    credits = data.get("credits") or {}
    crew = credits.get("crew") or []
    is_movie = media_type == "movie"
    release_date = data.get("release_date") if is_movie else data.get("first_air_date")
    year_value = int(release_date[:4]) if release_date and release_date[:4].isdigit() else None
    runtime_value = data.get("runtime") if is_movie else (data.get("episode_run_time") or [None])[0]

    spoken_languages = [
        language.get("english_name") or language.get("name")
        for language in data.get("spoken_languages", [])
        if language.get("english_name") or language.get("name")
    ]

    # Show only actual streaming/subscription services in India.
    # Rent/buy marketplaces such as YouTube Movies are not OTT subscriptions
    # and must not be shown as the title's OTT platform.
    provider_results = (watch_data or {}).get("results") or {}
    providers = provider_results.get("IN") or {}
    ott_names = sorted({
        provider.get("provider_name")
        for category in ("flatrate", "free", "ads")
        for provider in providers.get(category, [])
        if provider.get("provider_name")
        and provider.get("provider_name").strip().lower() not in {
            "youtube", "youtube movies", "google play movies"
        }
    })
    if not providers:
        logger.info("TMDB has no India watch-provider data for %r", raw_query)
    elif not ott_names:
        logger.info("TMDB has no India streaming/rent/buy providers for %r", raw_query)

    images = data.get("images") or {}
    language_code = data.get("original_language")
    poster_path = _pick_image(images.get("posters"), language_code) or data.get("poster_path")
    backdrop_path = _pick_image(images.get("backdrops"), language_code) or data.get("backdrop_path")

    certification = None
    if is_movie:
        for country in (data.get("release_dates") or {}).get("results", []):
            if country.get("iso_3166_1") == "IN":
                certification = next(
                    (entry.get("certification") for entry in country.get("release_dates", [])
                     if entry.get("certification")),
                    None
                )
                if certification:
                    break
    else:
        certification = next(
            (entry.get("rating") for entry in (data.get("content_ratings") or {}).get("results", [])
             if entry.get("iso_3166_1") == "IN" and entry.get("rating")),
            None
        )

    return {
        "title": data.get("title") or data.get("name"),
        "localized_title": data.get("original_title") or data.get("original_name"),
        "year": year_value,
        "release_date": release_date,
        "rating": round(float(data["vote_average"]), 1) if data.get("vote_average") else None,
        "votes": int(data.get("vote_count") or 0),
        "runtime": f"{runtime_value} min" if runtime_value else None,
        "certificates": certification,
        "tmdb_url": f"https://www.themoviedb.org/{media_type}/{tmdb_id}",
        "genres": [genre.get("name") for genre in data.get("genres", []) if genre.get("name")],
        "languages": spoken_languages,
        "ott_platform": ", ".join(ott_names) if ott_names else None,
        "countries": [country.get("name") for country in data.get("production_countries", []) if country.get("name")],
        "director": [person.get("name") for person in crew if person.get("job") == "Director" and person.get("name")],
        "writer": [person.get("name") for person in crew if person.get("job") in ("Writer", "Screenplay", "Story") and person.get("name")],
        "cast": [person.get("name") for person in (credits.get("cast") or [])[:10] if person.get("name")],
        "plot": data.get("overview"),
        "tagline": data.get("tagline"),
        "seasons": data.get("number_of_seasons"),
        "imdb_id": (data.get("external_ids") or {}).get("imdb_id") or data.get("imdb_id"),
        "tmdb_id": tmdb_id,
        "poster_url": _img(poster_path),
        "backdrop_url": _img(backdrop_path)
    }
