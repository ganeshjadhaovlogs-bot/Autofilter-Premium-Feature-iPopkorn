# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
#Join Telegram Channel - @roaroic0

from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest
from database.users_chats_db import db
from info import ADMINS, AUTH_REQ_CHANNELS, AUTH_CHANNELS
from pyrogram.filters import create

def is_auth_req_channel(_, __, update):
    return update.chat.id in set(AUTH_REQ_CHANNELS + AUTH_CHANNELS)

@Client.on_chat_join_request(create(is_auth_req_channel))
async def join_reqs(client, message: ChatJoinRequest):
    await db.add_join_req(message.from_user.id, message.chat.id)

@Client.on_chat_member_updated(create(is_auth_req_channel))
async def clear_join_req_on_membership_change(client, update):
    # Approval and leaving both generate a chat-member update. Clear the
    # pending-request marker so an old request can never grant later access.
    try:
        member = update.new_chat_member
        if member and member.user:
            await db.remove_join_req(member.user.id, update.chat.id)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning(
            f"Could not clear join-request record after membership update: {e}"
        )


@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    await db.del_join_req()    
    await message.reply("<b>⚙ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴄʜᴀɴɴᴇʟ ʟᴇғᴛ ᴜꜱᴇʀꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
