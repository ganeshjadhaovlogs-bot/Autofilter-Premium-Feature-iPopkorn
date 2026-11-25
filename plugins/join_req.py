# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
#Join Telegram Channel - @roaroic0

from pyrogram import Client, filters, enums
from pyrogram.types import ChatJoinRequest, ChatMemberUpdated
from database.users_chats_db import db
from info import ADMINS, AUTH_REQ_CHANNELS, AUTH_CHANNELS
from pyrogram.filters import create

def is_auth_req_channel(_, __, update):
    return update.chat.id in set(AUTH_REQ_CHANNELS + AUTH_CHANNELS)

@Client.on_chat_join_request(create(is_auth_req_channel))
async def join_reqs(client, message: ChatJoinRequest):
    await db.add_join_req(message.from_user.id, message.chat.id)



@Client.on_chat_member_updated(filters.chat(AUTH_REQ_CHANNELS + AUTH_CHANNELS))
async def clear_request_when_user_leaves(client, update: ChatMemberUpdated):
    # Remove old pending-request access when a user leaves or is banned.
    new_status = update.new_chat_member.status
    if new_status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
        await db.del_join_req(update.from_user.id, update.chat.id)

@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    await db.del_join_req()    
    await message.reply("<b>⚙ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴄʜᴀɴɴᴇʟ ʟᴇғᴛ ᴜꜱᴇʀꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
