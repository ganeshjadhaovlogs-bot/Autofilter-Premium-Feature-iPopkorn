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
    # from_user is the actor (which can be an admin), not always the
    # member whose status changed. Reset the affected user's complete
    # access state as soon as Telegram reports a leave or removal.
    new_member = update.new_chat_member
    if not new_member or not new_member.user:
        return

    if new_member.status in (enums.ChatMemberStatus.LEFT, enums.ChatMemberStatus.BANNED):
        user_id = new_member.user.id
        try:
            await db.clear_user_access_data(user_id)
            print(f"[FORCE JOIN] Cleared all access data for user {user_id} after leaving {update.chat.id}")
        except Exception as e:
            print(f"[FORCE JOIN] Failed to clear access data for user {user_id}: {e}")

@Client.on_message(filters.command("delreq") & filters.private & filters.user(ADMINS))
async def del_requests(client, message):
    await db.del_join_req()    
    await message.reply("<b>⚙ ꜱᴜᴄᴄᴇꜱꜱғᴜʟʟʏ ᴄʜᴀɴɴᴇʟ ʟᴇғᴛ ᴜꜱᴇʀꜱ ᴅᴇʟᴇᴛᴇᴅ</b>")
