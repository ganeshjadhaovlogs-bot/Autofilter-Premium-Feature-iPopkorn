# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import re
import logging
from pyrogram import Client, filters
from info import DELETE_CHANNELS, CHANNELS
from database.ia_filterdb import Media, Media2, unpack_new_file_id
logger = logging.getLogger(__name__)

media_filter = filters.document | filters.video | filters.audio


@Client.on_message(filters.chat(DELETE_CHANNELS) & media_filter)
async def deletemultiplemedia(bot, message):
    """Delete Multiple files from database"""

    # A source/database upload channel must never be treated as a delete channel.
    # If the same chat ID is configured in both lists, preserve new uploads.
    if message.chat and message.chat.id in CHANNELS:
        logger.info(
            "Ignoring delete-channel handler for source upload channel %s",
            message.chat.id
        )
        return

    for file_type in ("document", "video", "audio"):
        media = getattr(message, file_type, None)
        if media is not None:
            break
    else:
        return

    file_id, file_ref = unpack_new_file_id(media.file_id)
    if await Media.count_documents({'file_id': file_id}):
        result = await Media.collection.delete_one({
            '_id': file_id,
        })
    else:
        result = await Media2.collection.delete_one({
            '_id': file_id,
        })
    if result.deleted_count:
        logger.info('File is successfully deleted from database.')
    else:
        file_name = re.sub(r"(_|\-|\.|\+)", " ", str(media.file_name))
        result = await Media.collection.delete_many({
            'file_name': file_name,
            'file_size': media.file_size,
            'mime_type': media.mime_type
            })
        if result.deleted_count:
            logger.info('File is successfully deleted from database.')
        else:
            result = await Media2.collection.delete_many({
                'file_name': file_name,
                'file_size': media.file_size,
                'mime_type': media.mime_type
                })
            if result.deleted_count:
                logger.info('File is successfully deleted from database.')
            else:
                result = await Media.collection.delete_many({
                    'file_name': media.file_name,
                    'file_size': media.file_size,
                    'mime_type': media.mime_type
                })
                if result.deleted_count:
                    logger.info('File is successfully deleted from database.')
                else:
                    result = await Media2.collection.delete_many({
                        'file_name': media.file_name,
                        'file_size': media.file_size,
                        'mime_type': media.mime_type
                    })
                    if result.deleted_count:
                        logger.info('File is successfully deleted from database.')
                    else:
                        logger.info('File not found in database.')

    # Keep the public movie announcement in sync with database deletions.
    # If other qualities remain, update the existing post; if none remain,
    # delete that movie's channel post and its tracking document.
    if result.deleted_count:
        try:
            from plugins.channel import sync_movie_updates_after_file_delete
            await sync_movie_updates_after_file_delete(bot, [media.file_name])
        except Exception:
            logger.exception("Could not sync movie channel after database-channel deletion")
