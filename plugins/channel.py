# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import re
import logging
import asyncio
from datetime import datetime
from collections import defaultdict
from io import BytesIO
from PIL import Image, ImageDraw, ImageFont, ImageOps
from plugins.Roaroicfutures.Imdbposter import get_movie_detailsx, fetch_image, get_movie_details
from database.users_chats_db import db
from pyrogram import Client, filters, enums
from info import CHANNELS, MOVIE_UPDATE_CHANNEL, LINK_PREVIEW, ABOVE_PREVIEW, BAD_WORDS, LANDSCAPE_POSTER, TMDB_POSTER, ADMINS
from Script import script
from database.ia_filterdb import save_file
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from utils import temp
from pymongo.errors import PyMongoError, DuplicateKeyError
from pyrogram.errors import MessageIdInvalid, MessageNotModified, FloodWait
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

# Precomputed sets for faster lookups
IGNORE_WORDS = {
    "rarbg", "dub", "sub", "sample", "mkv", "aac", "combined",
    "action", "adventure", "animation", "biography", "comedy", "crime", 
    "documentary", "drama", "family", "fantasy", "film-noir", "history", 
    "horror", "music", "musical", "mystery", "romance", "sci-fi", "sport", 
    "thriller", "war", "western", "hdcam", "hdtc", "camrip", "ts", "tc", 
    "telesync", "dvdscr", "dvdrip", "predvd", "webrip", "web-dl", "tvrip", 
    "hdtv", "web dl", "webdl", "bluray", "brrip", "bdrip", "360p", "480p", 
    "720p", "1080p", "2160p", "4k", "1440p", "540p", "240p", "140p", "hevc", 
    "hdrip", "hin", "hindi", "tam", "tamil", "kan", "kannada", "tel", "telugu", 
    "mal", "malayalam", "eng", "english", "pun", "punjabi", "ben", "bengali", 
    "mar", "marathi", "guj", "gujarati", "urd", "urdu", "kor", "korean", "jpn", 
    "japanese", "nf", "netflix", "sonyliv", "sony", "sliv", "amzn", "prime", 
    "primevideo", "hotstar", "zee5", "jio", "jhs", "aha", "hbo", "paramount", 
    "apple", "hoichoi", "sunnxt", "viki"
}|BAD_WORDS

# Constants
CAPTION_LANGUAGES = {
    "hin": "Hindi", "hindi": "Hindi",
    "tam": "Tamil", "tamil": "Tamil",
    "kan": "Kannada", "kannada": "Kannada",
    "tel": "Telugu", "telugu": "Telugu",
    "mal": "Malayalam", "malayalam": "Malayalam",
    "eng": "English", "english": "English",
    "pun": "Punjabi", "punjabi": "Punjabi",
    "ben": "Bengali", "bengali": "Bengali",
    "mar": "Marathi", "marathi": "Marathi",
    "guj": "Gujarati", "gujarati": "Gujarati",
    "urd": "Urdu", "urdu": "Urdu",
    "kor": "Korean", "korean": "Korean",
    "jpn": "Japanese", "japanese": "Japanese",
}

OTT_PLATFORMS = {
    "nf": "Netflix", "netflix": "Netflix",
    "sonyliv": "SonyLiv", "sony": "SonyLiv", "sliv": "SonyLiv",
    "amzn": "Amazon Prime Video", "prime": "Amazon Prime Video", "primevideo": "Amazon Prime Video",
    "hotstar": "Disney+ Hotstar", "zee5": "Zee5",
    "jio": "JioHotstar", "jhs": "JioHotstar",
    "aha": "Aha", "hbo": "HBO Max", "paramount": "Paramount+",
    "apple": "Apple TV+", "hoichoi": "Hoichoi", "sunnxt": "Sun NXT", "viki": "Viki"
}

STANDARD_GENRES = {
    'Action', 'Adventure', 'Animation', 'Biography', 'Comedy', 'Crime', 'Documentary',
    'Drama', 'Family', 'Fantasy', 'Film-Noir', 'History', 'Horror', 'Music',
    'Musical', 'Mystery', 'Romance', 'Sci-Fi', 'Sport', 'Thriller', 'War', 'Western'
}

# Precompiled regex patterns
CLEAN_PATTERN = re.compile(r'@[^ \n\r\t\.,:;!?()\[\]{}<>\\/"\'=_%]+|\bwww\.[^\s\]\)]+|\([\@^]+\)|\[[\@^]+\]')
NORMALIZE_PATTERN = re.compile(r"[._]+|[()\[\]{}:;'–!,.?_]")
QUALITY_PATTERN = re.compile(
    r"\b(?:HDCam|HDTC|CamRip|TS|TC|TeleSync|DVDScr|DVDRip|PreDVD|"
    r"WEBRip|WEB-DL|TVRip|HDTV|WEB DL|WebDl|BluRay|BRRip|BDRip|"
    r"360p|480p|720p|1080p|2160p|4K|1440p|540p|240p|140p|HEVC|HDRip)\b", 
    re.IGNORECASE
)
YEAR_PATTERN = re.compile(r"(?<![A-Za-z0-9])(?:19|20)\d{2}(?![A-Za-z0-9])")
RANGE_REGEX = re.compile(r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,2})\s*(?:to|-)\s*(?:E(?:p(?:isode)?)?)?0*(\d{1,2})',re.IGNORECASE)
SINGLE_REGEX = re.compile(r'\bS(\d{1,2})[^\w\n\r]*E(?:p(?:isode)?)?0*(\d{1,3})', re.IGNORECASE)
NAMED_REGEX = re.compile(r'Season\s*0*(\d{1,2})[\s\-,:]*Ep(?:isode)?\s*0*(\d{1,3})', re.IGNORECASE)
EP_ONLY_RANGE = re.compile(r'\b(?:EP|Episode)0*(\d{1,3})\s*-\s*0*(\d{1,3})\b',re.IGNORECASE)


MEDIA_FILTER = filters.document | filters.video | filters.audio
locks = defaultdict(asyncio.Lock)
pending_updates = {}


def clean_mentions_links(text: str) -> str:
    return CLEAN_PATTERN.sub("", text or "").strip()

def normalize(s: str) -> str:
    s = NORMALIZE_PATTERN.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()

def remove_ignored_words(text: str) -> str:
    IGNORE_WORDS_LOWER = {w.lower() for w in IGNORE_WORDS}
    return " ".join(word for word in text.split() if word.lower() not in IGNORE_WORDS_LOWER)

def get_qualities(text: str) -> str:
    qualities = QUALITY_PATTERN.findall(text)
    return ", ".join(qualities) if qualities else "N/A"

def extract_ott_platform(text: str) -> str:
    text = text.lower()
    platforms = {plat for key, plat in OTT_PLATFORMS.items() if key in text}
    return " | ".join(platforms) if platforms else "N/A"

def extract_season_episode(filename: str) -> Tuple[Optional[int], Optional[str]]:
    if m := EP_ONLY_RANGE.search(filename):
        return 1, f"{int(m.group(1))}-{int(m.group(2))}"
    for pattern in (RANGE_REGEX, SINGLE_REGEX, NAMED_REGEX):
        if m := pattern.search(filename):
            season = int(m.group(1))
            if pattern == RANGE_REGEX:
                ep = f"{m.group(2)}-{m.group(3)}"
            else:
                ep = m.group(2)
            return season, ep
    return None, None

def schedule_update(bot, base_name, delay=5):
    if handle := pending_updates.get(base_name):
        if not handle.cancelled():
            handle.cancel()
    
    loop = asyncio.get_event_loop()
    pending_updates[base_name] = loop.call_later(
        delay,
        lambda: asyncio.create_task(update_movie_message(bot, base_name))
    )

def extract_media_info(filename: str, caption: str):
    filename = normalize(clean_mentions_links(filename).title())
    caption_clean = clean_mentions_links(caption).lower() if caption else ""
    unified = f"{caption_clean} {filename.lower()}".strip()

    season = episode = year = None
    tag = "#MOVIE"
    processed_raw = base_raw = filename
    quality = get_qualities(caption_clean) or get_qualities(filename.lower()) or "N/A"
    ott_platform = extract_ott_platform(f"{filename} {caption_clean}")

    lang_keys = {k for k in CAPTION_LANGUAGES if k in caption_clean or k in filename.lower()}
    language = ", ".join(sorted({CAPTION_LANGUAGES[k] for k in lang_keys})) if lang_keys else "N/A"

    season, episode = extract_season_episode(filename)
    if season is not None:
        tag = "#SERIES"
        if m := (RANGE_REGEX.search(filename) or SINGLE_REGEX.search(filename) or NAMED_REGEX.search(filename) or EP_ONLY_RANGE.search(filename)):
            match_str = m.group(0)
            start_idx = filename.lower().find(match_str.lower())
            end_idx = start_idx + len(match_str)
            processed_raw = filename[:end_idx]
            base_raw = filename[:start_idx]
            if year_match := YEAR_PATTERN.search(filename.lower()[end_idx:]):
                y = year_match.group(0)
                yi = filename.lower().find(y, end_idx)
                if yi != -1:
                    processed_raw = filename[:yi+4]
                    base_raw += f" {y}"
    else:
        if year_match := YEAR_PATTERN.search(unified):
            year = year_match.group(0)
            year_idx = filename.lower().find(year.lower())
            if year_idx != -1:
                processed_raw = filename[:year_idx + 4]
                base_raw = processed_raw
        else:
            if qual_match := QUALITY_PATTERN.search(unified):
                qual_str = qual_match.group(0)
                qual_idx = filename.lower().find(qual_str.lower())
                if qual_idx != -1:
                    processed_raw = filename[:qual_idx]
                    base_raw = processed_raw

    base_name = normalize(remove_ignored_words(normalize(base_raw)))
    if year and year not in base_name:
        base_name += f" {year}"

    if base_name.endswith(")"):
        base_name = re.sub(r"\s+\(\d{4}\)$", "", base_name)
        if year:
            base_name += f" ({year})"

    return {
        "processed": normalize(processed_raw),
        "base_name": base_name,
        "tag": tag,
        "season": season,
        "episode": episode,
        "year": year,
        "quality": quality,
        "ott_platform": ott_platform,
        "language": language
    }

@Client.on_message(filters.chat(CHANNELS) & MEDIA_FILTER)
async def media_handler(bot, message):
    media = next(
        (getattr(message, ft) for ft in ("document", "video", "audio")
         if getattr(message, ft, None)),
        None
    )
    if not media:
        return

    media.file_type = next(ft for ft in ("document", "video", "audio") if hasattr(message, ft))
    media.caption = message.caption or ""
    success, info = await save_file(media)
    if not success:
        return

    try:
        if await db.movie_update_status(bot.me.id):
            await process_and_send_update(bot, media.file_name, media.caption)
    except Exception:
        logger.exception("Error processing media")

async def process_and_send_update(bot, filename, caption):
    try:
        media_info = extract_media_info(filename, caption)
        base_name = media_info["base_name"]
        processed = media_info["processed"]

        lock = locks[base_name]
        async with lock:
            await _process_with_lock(bot, filename, caption, media_info, base_name, processed)
    except PyMongoError as e:
        logger.error("Database error: %s", e)
    except Exception as e:
        logger.exception("Processing failed: %s", e)

error_tmdb = False

async def _process_with_lock(bot, filename, caption, media_info, base_name, processed):
    if not hasattr(db, 'movie_updates'):
        db.movie_updates = db.db.movie_updates

    movie_doc = await db.movie_updates.find_one({"_id": base_name})
    global error_tmdb
    error_tmdb=False
    file_data = {
        "filename": filename,
        "processed": processed,
        "quality": media_info["quality"],
        "language": media_info["language"],
        "ott_platform": media_info["ott_platform"],
        "timestamp": datetime.now(),
        "tag": media_info["tag"],
        "season": media_info["season"],
        "episode": media_info["episode"]
    }

    if not movie_doc:
        # IMDb is the primary source for title details and artwork.
        imdb_details = await get_movie_details(base_name) or {}
        logger.info(
            "IMDb lookup for '%s': %s",
            base_name,
            "matched " + str(imdb_details.get("imdb_id")) if imdb_details else "no match"
        )
        # Query TMDB as a second source even when IMDb returns partial metadata.
        tmdb_details = await get_movie_detailsx(base_name) or {}
        logger.info(
            "TMDB lookup for '%s': %s",
            base_name,
            "matched " + str(tmdb_details.get("tmdb_id")) if tmdb_details.get("tmdb_id") else tmdb_details.get("error", "no match")
        )

        # IMDb has priority; TMDB fills every field IMDb does not provide.
        details = dict(tmdb_details)
        for key, value in imdb_details.items():
            if value not in (None, "", [], "N/A"):
                details[key] = value

        imdb_poster = imdb_details.get("poster_url")
        tmdb_poster = (
            tmdb_details.get("backdrop_url")
            if LANDSCAPE_POSTER and tmdb_details.get("backdrop_url")
            else tmdb_details.get("poster_url")
        )
        poster_url = imdb_poster or tmdb_poster
        backup_poster_url = tmdb_poster if imdb_poster else None

        raw_genres = details.get("genres", "N/A")
        if isinstance(raw_genres, str):
            genres = ", ".join(g.strip() for g in raw_genres.split(",") if g.strip()) or "N/A"
        elif isinstance(raw_genres, (list, tuple, set)):
            genres = ", ".join(str(g).strip() for g in raw_genres if str(g).strip()) or "N/A"
        else:
            genres = "N/A"

        movie_doc = {
            "_id": base_name,
            "title": details.get("title") or imdb_details.get("title") or base_name,
            "files": [file_data],
            "poster_url": poster_url,
            "backup_poster_url": backup_poster_url,
            "is_landscape": True,
            "genres": genres,
            "rating": details.get("rating") or "N/A",
            "runtime": details.get("runtime") or "N/A",
            "imdb_url": imdb_details.get("url") or (
                f"https://www.imdb.com/title/{imdb_details.get('imdb_id')}"
                if imdb_details.get("imdb_id") else
                details.get("tmdb_url") or ""
            ),
            "year": media_info["year"] or imdb_details.get("year") or tmdb_details.get("year"),
            "tag": media_info["tag"],
            "ott_platform": details.get("ott_platform") or media_info["ott_platform"],
            "online_languages": (
                details.get("languages")
                if isinstance(details.get("languages"), str)
                else ", ".join(details.get("languages") or [])
            ),
            "message_id": None,
            "is_photo": False
        }
        try:
            await db.movie_updates.insert_one(movie_doc)
            await send_movie_update(bot, base_name)
            movie_doc = await db.movie_updates.find_one({"_id": base_name})
        except DuplicateKeyError:
            movie_doc = await db.movie_updates.find_one({"_id": base_name})
            if movie_doc:
                if any(f["filename"] == filename for f in movie_doc["files"]):
                    return
                await db.movie_updates.update_one(
                    {"_id": base_name},
                    {"$push": {"files": file_data}}
                )
                movie_doc["files"].append(file_data)
                schedule_update(bot, base_name)
    else:
        if any(f["filename"] == filename for f in movie_doc["files"]):
            return
        await db.movie_updates.update_one(
            {"_id": base_name},
            {"$push": {"files": file_data}}
        )
        movie_doc["files"].append(file_data)

        # Repair older movie records that were created without IMDb artwork/details.
        if (
            not movie_doc.get("poster_url")
            or movie_doc.get("genres") in (None, "", "N/A")
            or movie_doc.get("rating") in (None, "", "N/A")
            or movie_doc.get("runtime") in (None, "", "N/A")
            or movie_doc.get("ott_platform") in (None, "", "N/A")
            or movie_doc.get("online_languages") in (None, "", "N/A")
        ):
            imdb_details = await get_movie_details(base_name) or {}
            # Retry both providers for old database records missing poster/details.
            tmdb_details = await get_movie_detailsx(base_name) or {}

            tmdb_poster = (
                tmdb_details.get("backdrop_url")
                if LANDSCAPE_POSTER and tmdb_details.get("backdrop_url")
                else tmdb_details.get("poster_url")
            )
            # Prefer a newly verified IMDb/TMDB URL over a stale URL already
            # stored in the database; a stale URL can prevent poster recovery.
            poster_url = (
                imdb_details.get("poster_url")
                or tmdb_poster
                or movie_doc.get("poster_url")
            )
            updates = {}
            if poster_url:
                updates["poster_url"] = poster_url
                updates["backup_poster_url"] = (
                    tmdb_details.get("poster_url")
                    if imdb_details.get("poster_url") and tmdb_details.get("poster_url")
                    else movie_doc.get("backup_poster_url")
                )
            title_candidate = imdb_details.get("title") or tmdb_details.get("title")
            if title_candidate and not movie_doc.get("title"):
                updates["title"] = title_candidate
            for field in ("genres", "rating", "runtime", "year"):
                current = movie_doc.get(field)
                candidate = imdb_details.get(field) or tmdb_details.get(field)
                if candidate and current in (None, "", "N/A"):
                    if field == "genres" and not isinstance(candidate, str):
                        candidate = ", ".join(str(item) for item in candidate)
                    updates[field] = candidate

            online_languages = tmdb_details.get("languages") or []
            if online_languages and movie_doc.get("online_languages") in (None, "", "N/A"):
                updates["online_languages"] = ", ".join(str(item) for item in online_languages)
            online_ott = tmdb_details.get("ott_platform")
            if online_ott and movie_doc.get("ott_platform") in (None, "", "N/A"):
                updates["ott_platform"] = online_ott

            if imdb_details.get("url"):
                updates["imdb_url"] = imdb_details["url"]

            if updates:
                await db.movie_updates.update_one(
                    {"_id": base_name},
                    {"$set": updates}
                )
                movie_doc.update(updates)

                # Replace the old fallback-only post with the real IMDb poster.
                if poster_url and movie_doc.get("message_id"):
                    try:
                        await bot.delete_messages(
                            chat_id=MOVIE_UPDATE_CHANNEL,
                            message_ids=movie_doc["message_id"]
                        )
                        await db.movie_updates.update_one(
                            {"_id": base_name},
                            {"$set": {"message_id": None, "is_photo": False}}
                        )
                        movie_doc["message_id"] = None
                        await send_movie_update(bot, base_name)
                    except Exception:
                        logger.exception(
                            "Could not refresh old movie post with IMDb artwork: %s",
                            base_name
                        )

        schedule_update(bot, base_name)

async def send_movie_update(bot, base_name):
    max_retries = 3
    base_delay = 5
    for attempt in range(max_retries):
        try:
            movie_doc = await db.movie_updates.find_one({"_id": base_name})
            if not movie_doc:
                return None

            text = generate_movie_message(movie_doc, base_name)
            buttons = InlineKeyboardMarkup([[
                InlineKeyboardButton(
                    'ɢᴇᴛ ғɪʟᴇs',
                    url=f"https://t.me/{temp.U_NAME}?start=getfile-{base_name.replace(' ', '-')}"
                )
            ]])

            resized_poster = None
            # Try the IMDb image first, then TMDB artwork if the IMDb URL fails.
            poster_urls = [
                movie_doc.get("poster_url"),
                movie_doc.get("backup_poster_url")
            ]
            for poster_url in poster_urls:
                if not poster_url:
                    continue
                logger.info("Trying announcement artwork for '%s': %s", base_name, poster_url[:180])
                resized_poster = await fetch_image(
                    poster_url,
                    size=(1280, 720)
                )
                if resized_poster:
                    logger.info("Announcement artwork downloaded successfully for '%s'", base_name)
                    break
                logger.warning("Announcement artwork URL failed for '%s': %s", base_name, poster_url[:180])

            # fetch_image already returns 16:9; normalize once more for safety.
            if resized_poster:
                source_image = Image.open(resized_poster).convert("RGB")
                landscape_image = ImageOps.fit(
                    source_image, (1280, 720),
                    method=Image.Resampling.LANCZOS,
                    centering=(0.5, 0.5)
                )
                output = BytesIO()
                landscape_image.save(output, format="JPEG", quality=92)
                output.seek(0)
                output.name = "movie_landscape.jpg"
                resized_poster = output
            else:
                logger.warning("IMDb/TMDB poster unavailable for '%s'; using branded fallback.", base_name)
                resized_poster = generate_fallback_poster(movie_doc, base_name)

            msg = await bot.send_photo(
                chat_id=MOVIE_UPDATE_CHANNEL,
                photo=resized_poster,
                caption=text,
                reply_markup=buttons,
                parse_mode=enums.ParseMode.HTML
            )
            is_photo = True

            await db.movie_updates.update_one(
                {"_id": base_name},
                {"$set": {"message_id": msg.id, "is_photo": is_photo}}
            )
            return msg
        except FloodWait as e:
            wait_time = e.value + 2
            await asyncio.sleep(wait_time)
        except Exception as e:
            logger.error(f"Failed to send movie update: {e}")
            break
    return None

async def update_movie_message(bot, base_name):
    try:
        movie_doc = await db.movie_updates.find_one({"_id": base_name})
        if not movie_doc:
            return

        text = generate_movie_message(movie_doc, base_name)
        buttons = InlineKeyboardMarkup([[
            InlineKeyboardButton(
                'ɢᴇᴛ ғɪʟᴇs',
                url=f"https://t.me/{temp.U_NAME}?start=getfile-{base_name.replace(' ', '-')}"
            )
        ]])

        message_id = movie_doc.get("message_id")
        is_photo = movie_doc.get("is_photo", False)

        if not message_id:
            await send_movie_update(bot, base_name)
            return

        try:
            if is_photo:
                await bot.edit_message_caption(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_id=message_id,
                    caption=text,
                    reply_markup=buttons,
                    parse_mode=enums.ParseMode.HTML
                )
                return
            # Upgrade an older text-only notification to a photo post.
            await bot.delete_messages(
                chat_id=MOVIE_UPDATE_CHANNEL,
                message_ids=message_id
            )
            await db.movie_updates.update_one(
                {"_id": base_name},
                {"$set": {"message_id": None, "is_photo": False}}
            )
            await send_movie_update(bot, base_name)
            return
        except (MessageIdInvalid, MessageNotModified):
            pass
        except Exception:
            try:
                await bot.delete_messages(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_ids=message_id
                )
                await db.movie_updates.update_one(
                    {"_id": base_name},
                    {"$set": {"message_id": None, "is_photo": False}}
                )
            except Exception:
                pass
            await send_movie_update(bot, base_name)
    except Exception as e:
        logger.error(f"Failed to update movie message: {e}")


async def sync_movie_updates_after_file_delete(bot, deleted_filenames):
    """Remove deleted database files from movie announcements and clean empty posts."""
    deleted_keys = {
        re.sub(r"[^a-z0-9]+", " ", str(name).lower()).strip()
        for name in deleted_filenames if name
    }
    if not deleted_keys:
        return

    async for movie_doc in db.movie_updates.find({}):
        movie_files = movie_doc.get("files", [])
        remaining_files = [
            item for item in movie_files
            if re.sub(
                r"[^a-z0-9]+", " ",
                str(item.get("filename", "")).lower()
            ).strip() not in deleted_keys
        ]
        if len(remaining_files) == len(movie_files):
            continue

        base_name = movie_doc["_id"]
        pending = pending_updates.pop(base_name, None)
        if pending and not pending.cancelled():
            pending.cancel()

        if remaining_files:
            await db.movie_updates.update_one(
                {"_id": base_name},
                {"$set": {"files": remaining_files}}
            )
            await update_movie_message(bot, base_name)
            logger.info("Updated channel announcement after file deletion: %s", base_name)
            continue

        message_id = movie_doc.get("message_id")
        if message_id:
            try:
                await bot.delete_messages(
                    chat_id=MOVIE_UPDATE_CHANNEL,
                    message_ids=message_id
                )
            except MessageIdInvalid:
                pass
            except Exception:
                logger.exception(
                    "Could not delete channel announcement for %s", base_name
                )
                continue

        await db.movie_updates.delete_one({"_id": base_name})
        logger.info("Deleted empty movie announcement: %s", base_name)

def generate_fallback_poster(movie_doc, base_name):
    """Create a branded poster when TMDB/IMDb has no usable artwork."""
    width, height = 1280, 720
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)

    # Deep blue/purple vertical gradient with subtle geometric decoration.
    top = (12, 18, 38)
    bottom = (48, 20, 68)
    for y in range(height):
        ratio = y / max(height - 1, 1)
        color = tuple(int(top[k] * (1 - ratio) + bottom[k] * ratio) for k in range(3))
        draw.line((0, y, width, y), fill=color)
    draw.ellipse((width - 310, 90, width + 160, 560), outline=(91, 75, 130), width=5)
    draw.ellipse((-190, 760, 300, 1250), outline=(75, 61, 112), width=5)
    draw.rounded_rectangle((42, 42, width - 42, height - 42), radius=28,
                           outline=(145, 125, 185), width=3)

    try:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        small_font = ImageFont.truetype(font_path, 28)
        title_font = ImageFont.truetype(font_path, 58)
        footer_font = ImageFont.truetype(font_path, 26)
    except Exception:
        small_font = title_font = footer_font = ImageFont.load_default()

    is_series = any(f.get("tag") == "#SERIES" for f in movie_doc.get("files", []))
    label = "NEW SERIES" if is_series else "NEW MOVIE"
    draw.text((width // 2, 145), label, font=small_font, fill=(230, 205, 255), anchor="mm")

    title = str(base_name or "Untitled").strip()
    words = title.split()
    lines, line = [], ""
    for word in words:
        candidate = (line + " " + word).strip()
        if draw.textbbox((0, 0), candidate, font=title_font)[2] <= width - 130:
            line = candidate
        else:
            if line:
                lines.append(line)
            line = word
    if line:
        lines.append(line)
    if not lines:
        lines = ["Untitled"]
    # Keep long titles readable and inside the poster.
    if len(lines) > 5:
        lines = lines[:5]
        lines[-1] = lines[-1][:24] + "…"

    line_height = 76
    y = height // 2 - (len(lines) * line_height) // 2
    for title_line in lines:
        draw.text((width // 2, y), title_line, font=title_font,
                  fill=(255, 255, 255), anchor="mm", stroke_width=1,
                  stroke_fill=(30, 20, 45))
        y += line_height

    draw.line((300, 555, width - 300, 555), fill=(170, 145, 205), width=3)
    draw.text((width // 2, 615), "FILMS CHOR", font=footer_font,
              fill=(230, 205, 255), anchor="mm")
    output = BytesIO()
    image.save(output, format="JPEG", quality=92)
    output.seek(0)
    output.name = "movie_poster.jpg"
    return output


def generate_movie_message(movie_doc, base_name):
    all_qualities = set()
    all_languages = set()
    all_ott_platforms = set()
    all_tags = set()
    episodes_by_season = defaultdict(set)

    for file in movie_doc["files"]:
        if file["quality"] != "N/A":
            all_qualities.update(q.strip() for q in file["quality"].split(",") if q.strip())
        if file["language"] != "N/A":
            all_languages.update(l.strip() for l in file["language"].split(",") if l.strip())
        if file["ott_platform"] != "N/A":
            platforms = [p.strip() for p in file["ott_platform"].split("|") if p.strip()]
            all_ott_platforms.update(platforms)
        if file["tag"]:
            all_tags.add(file["tag"])
        if file.get("season") and file.get("episode"):
            season = file["season"]
            episode = file["episode"]
            episodes_by_season[season].add(episode)

    primary_tag = "#SERIES" if "#SERIES" in all_tags else "#MOVIE"
    epi_block = ""
    if episodes_by_season:
        episode_lines = []
        for season, episodes in sorted(episodes_by_season.items(), key=lambda x: int(x[0])):
            singles = []
            ranges = []

            for ep in episodes:
                if "-" in ep:
                    ranges.append(ep)
                else:
                    try:
                        singles.append(int(ep))
                    except ValueError:
                        ranges.append(ep)

            singles.sort()
            collapsed = []
            start = end = None
            for num in singles:
                if start is None:
                    start = end = num
                elif num == end + 1:
                    end = num
                else:
                    collapsed.append(str(start) if start == end else f"{start}-{end}")
                    start = end = num
            if start is not None:
                collapsed.append(str(start) if start == end else f"{start}-{end}")

            all_ep_parts = collapsed + sorted(ranges, key=lambda s: int(s.split("-")[0]))
            episode_lines.append(f"S{int(season)}: {', '.join(all_ep_parts)}")

        epi_str = "\n".join(episode_lines)
        if epi_str:
            epi_block = f"📺 ᴇᴘɪsᴏᴅᴇs : <b>\n{epi_str}</b>"

    genres = movie_doc.get("genres", "N/A")
    runtime = str(movie_doc.get("runtime") or "N/A")
    if runtime != "N/A":
        runtime = runtime.replace(" minutes", "m").replace(" minute", "m").replace(" min", "m")
        if runtime.isdigit():
            runtime += "m"
    quality_str = ", ".join(sorted(all_qualities)) if all_qualities else "N/A"
    language_str = ", ".join(sorted(all_languages)) if all_languages else "N/A"
    ott_str = ", ".join(sorted(all_ott_platforms)) if all_ott_platforms else (
        movie_doc.get("ott_platform") or "N/A"
    )
    if not all_languages:
        online_languages = movie_doc.get("online_languages")
        if online_languages:
            language_str = online_languages

    display_title = movie_doc.get("title") or base_name
    year = movie_doc.get("year")
    if year and str(year) not in str(display_title):
        display_title = f"{display_title} ({year})"

    return script.MOVIE_UPDATE_NOTIFY_TXT.format(
        poster_url=movie_doc.get("poster_url", ""),
        imdb_url=movie_doc.get("imdb_url", ""),
        filename=display_title,
        tag=primary_tag,
        genres=genres,
        runtime=runtime,
        ott=ott_str,
        quality=quality_str,
        language=language_str,
        episodes=epi_block,
        rating=movie_doc.get("rating", "N/A"),
        search_link=temp.B_LINK
    )


# Refresh task controls. The stop command leaves the current movie intact.
refresh_running = False
refresh_stop_requested = False


@Client.on_message(filters.command("refreshmovies") & filters.user(ADMINS))
async def refresh_all_movie_metadata(bot, message):
    """Admin utility: re-fetch IMDb/TMDB details and refresh existing channel posts."""
    global refresh_running, refresh_stop_requested

    if refresh_running:
        await message.reply_text("<b>⚠️ Refresh pehle se chal raha hai. Use /stoprefresh to stop it.</b>")
        return

    refresh_running = True
    refresh_stop_requested = False
    status = await message.reply_text(
        "<b>🔄 IMDb/TMDB se purani movies ki details aur posters refresh ho rahe hain...</b>"
    )
    if not hasattr(db, "movie_updates"):
        db.movie_updates = db.db.movie_updates

    checked = updated = posted = 0
    stopped = False
    try:
        async for movie_doc in db.movie_updates.find({}):
            if refresh_stop_requested:
                stopped = True
                break

            base_name = movie_doc.get("_id")
            if not base_name:
                continue

            try:
                imdb_details = await get_movie_details(base_name) or {}
                tmdb_details = await get_movie_detailsx(base_name) or {}

                # Stop before writing/posting this movie if cancellation was requested
                # while the metadata providers were being queried.
                if refresh_stop_requested:
                    stopped = True
                    break

                details = dict(tmdb_details)
                for key, value in imdb_details.items():
                    if value not in (None, "", [], "N/A"):
                        details[key] = value

                tmdb_poster = (
                    tmdb_details.get("backdrop_url")
                    if LANDSCAPE_POSTER and tmdb_details.get("backdrop_url")
                    else tmdb_details.get("poster_url")
                )
                # Only use fresh artwork from a verified title/year match.
                # Do not keep an old unrelated poster when both providers fail.
                poster_url = imdb_details.get("poster_url") or tmdb_poster
                raw_genres = details.get("genres")
                if isinstance(raw_genres, (list, tuple, set)):
                    genres = ", ".join(str(g) for g in raw_genres if g)
                elif isinstance(raw_genres, str):
                    genres = raw_genres
                else:
                    genres = "N/A"

                updates = {
                    "title": details.get("title") or base_name,
                    "genres": genres or "N/A",
                    "rating": details.get("rating") or "N/A",
                    "runtime": details.get("runtime") or "N/A",
                    "year": details.get("year") or movie_doc.get("year"),
                    "poster_url": poster_url,
                    "backup_poster_url": tmdb_poster if poster_url and poster_url != tmdb_poster else None,
                    "imdb_url": imdb_details.get("url") or movie_doc.get("imdb_url") or (
                        f"https://www.imdb.com/title/{imdb_details['imdb_id']}"
                        if imdb_details.get("imdb_id") else details.get("tmdb_url", "")
                    )
                }
                await db.movie_updates.update_one(
                    {"_id": base_name},
                    {"$set": updates}
                )
                movie_doc.update(updates)
                checked += 1
                updated += 1

                if refresh_stop_requested:
                    stopped = True
                    break

                old_message_id = movie_doc.get("message_id")
                if old_message_id and poster_url:
                    try:
                        await bot.delete_messages(
                            chat_id=MOVIE_UPDATE_CHANNEL,
                            message_ids=old_message_id
                        )
                        await db.movie_updates.update_one(
                            {"_id": base_name},
                            {"$set": {"message_id": None, "is_photo": False}}
                        )
                        movie_doc["message_id"] = None
                        await send_movie_update(bot, base_name)
                        posted += 1
                    except Exception:
                        logger.exception("Could not replace old movie post during refresh: %s", base_name)
                        await update_movie_message(bot, base_name)
                else:
                    await update_movie_message(bot, base_name)

                if refresh_stop_requested:
                    stopped = True
                    break
                await asyncio.sleep(1)
            except Exception:
                checked += 1
                logger.exception("Metadata refresh failed for %s", base_name)

        if refresh_stop_requested:
            stopped = True

        if stopped:
            await status.edit_text(
                f"<b>⏹️ Refresh stopped.\n\n"
                f"Movies checked: {checked}\n"
                f"Metadata updated: {updated}\n"
                f"Channel posts refreshed: {posted}</b>"
            )
        else:
            await status.edit_text(
                f"<b>✅ Refresh complete!\n\n"
                f"Movies checked: {checked}\n"
                f"Metadata updated: {updated}\n"
                f"Channel posts refreshed: {posted}</b>"
            )
    finally:
        refresh_running = False
        refresh_stop_requested = False


@Client.on_message(filters.command("stoprefresh") & filters.user(ADMINS))
async def stop_refresh_all_movie_metadata(bot, message):
    global refresh_stop_requested

    if not refresh_running:
        await message.reply_text("<b>ℹ️ Abhi koi movie refresh nahi chal raha.</b>")
        return

    refresh_stop_requested = True
    await message.reply_text(
        "<b>⏹️ Stop request mil gayi. Current movie ka kaam complete hote hi refresh ruk jayega.</b>"
    )
