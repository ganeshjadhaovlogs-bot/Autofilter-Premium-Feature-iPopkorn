# ─────────────────────────────────────────────
# Powered by Roaroic | Developer Channel: @roaroic0
# https://t.me/roaroic0
# ─────────────────────────────────────────────
import sys
import glob
import importlib
from pathlib import Path
from pyrogram import Client, idle, __version__
from pyrogram.raw.all import layer
import time
from pyrogram.errors import FloodWait
import asyncio
from datetime import date, datetime
import pytz
from aiohttp import web
import aiohttp
from database.ia_filterdb import Media, Media2
from database.users_chats_db import db
from info import *
from utils import temp
from Script import script
from plugins import web_server, check_expired_premium, keep_alive
from roaroicbot.Bot import roaroicbot
from roaroicbot.util.keepalive import ping_server
from roaroicbot.Bot.clients import initialize_clients
from PIL import Image
Image.MAX_IMAGE_PIXELS = 500_000_000

import logging
import logging.config

logging.config.fileConfig('logging.conf')
logging.getLogger().setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.ERROR)
logging.getLogger("imdbpy").setLevel(logging.ERROR)
logging.getLogger("aiohttp").setLevel(logging.ERROR)
logging.getLogger("aiohttp.web").setLevel(logging.ERROR)
logging.getLogger("pymongo").setLevel(logging.WARNING)

botStartTime = time.time()
ppath = "plugins/*.py"
files = glob.glob(ppath)

async def roaroicbot_start():
    print('\n\nInitalizing RoaroicBot')
    print(DEV_CREDIT)
    await roaroicbot.start()

    # Keep Telegram's bot menu set to the registered command list.
    try:
        bot_commands = [
            {"command": command, "description": str(description).strip()[:256]}
            for command, description in Bot_cmds.items()
        ]
        async with aiohttp.ClientSession() as session:
            commands_response = await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setMyCommands",
                json={"commands": bot_commands}
            )
            commands_result = await commands_response.json()
            if not commands_result.get("ok"):
                logging.warning("Could not register Telegram bot commands: %s", commands_result)

            # Explicitly reset the DEFAULT menu button to Commands (never a Web App/URL).
            menu_response = await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
                json={
                    "scope": {"type": "default"},
                    "menu_button": {"type": "commands"}
                }
            )
            menu_result = await menu_response.json()
            if menu_result.get("ok"):
                logging.info("Telegram Menu Button set to Commands.")
            else:
                logging.warning("Could not set Telegram Menu Button to Commands: %s", menu_result)
    except Exception:
        logging.exception("Failed to configure Telegram command menu.")

    bot_info = await roaroicbot.get_me()
    roaroicbot.username = bot_info.username
    await initialize_clients()
    for name in files:
        with open(name) as a:
            patt = Path(a.name)
            plugin_name = patt.stem.replace(".py", "")
            plugins_dir = Path(f"plugins/{plugin_name}.py")
            import_path = "plugins.{}".format(plugin_name)
            spec = importlib.util.spec_from_file_location(import_path, plugins_dir)
            load = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(load)
            sys.modules["plugins." + plugin_name] = load
            print("Roaroic Imported => " + plugin_name)

    # Re-assert the default Commands menu after every plugin has initialized.
    # This overrides any default URL/Web App menu-button setting at startup.
    try:
        async with aiohttp.ClientSession() as session:
            response = await session.post(
                f"https://api.telegram.org/bot{BOT_TOKEN}/setChatMenuButton",
                json={
                    "scope": {"type": "default"},
                    "menu_button": {"type": "commands"}
                }
            )
            result = await response.json()
            if result.get("ok"):
                logging.info("Default Telegram menu button locked to Commands after plugin initialization.")
            else:
                logging.error("Could not enforce default Commands menu button: %s", result)
    except Exception:
        logging.exception("Failed to enforce default Telegram Commands menu button.")

    if ON_HEROKU or ON_RENDER:
        asyncio.create_task(ping_server())
    b_users, b_chats = await db.get_banned()
    temp.BANNED_USERS = b_users
    temp.BANNED_CHATS = b_chats
    await Media.ensure_indexes()
    if MULTIPLE_DB:
        await Media2.ensure_indexes()
        print("Multiple Database Mode On. Now Files Will Be Save In Second DB If First DB Is Full")
    else:
        print("Single DB Mode On ! Files Will Be Save In First Database")
    me = await roaroicbot.get_me()
    temp.ME = me.id
    temp.U_NAME = me.username
    temp.B_NAME = me.first_name
    temp.B_LINK = me.mention
    roaroicbot.username = '@' + me.username
    roaroicbot.loop.create_task(check_expired_premium(roaroicbot))
    logging.info(f"{me.first_name} with Pyrogram v{__version__} (Layer {layer}) started on {me.username}.")
    logging.info(LOG_STR)
    logging.info(script.LOGO)
    tz = pytz.timezone('Asia/Kolkata')
    today = date.today()
    now = datetime.now(tz)
    time_str = now.strftime("%H:%M:%S %p")
    try:
        await roaroicbot.send_message(chat_id=LOG_CHANNEL, text=script.RESTART_TXT.format(temp.B_LINK, today, time_str))
    except Exception as e:
        # A wrong LOG_CHANNEL id, or the bot not being an admin there, must not stop the bot from starting.
        logging.error(
            f"Could not send restart message to LOG_CHANNEL ({LOG_CHANNEL}): {type(e).__name__}: {e}. "
            "Check that LOG_CHANNEL is the full id (starts with -100), and that the bot is added as an admin in that channel."
        )
    roaroicbot.loop.create_task(keep_alive())
    await idle()
    
async def start_web_server():
    """Bind Render's HTTP health/stream server before Telegram startup."""
    app = web.AppRunner(await web_server())
    await app.setup()
    await web.TCPSite(app, "0.0.0.0", PORT).start()
    logging.info("HTTP server listening on 0.0.0.0:%s", PORT)
    return app


if __name__ == '__main__':
    try:
        loop = asyncio.get_event_loop()
    except RuntimeError:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)

    # Render must see an open port even if Telegram asks the bot to wait
    # because of a FloodWait during client startup.
    loop.run_until_complete(start_web_server())

    while True:
        try:
            loop.run_until_complete(roaroicbot_start())
            break  
        except FloodWait as e:
            print(f"FloodWait! Sleeping for {e.value} seconds.")
            try:
                loop.run_until_complete(roaroicbot.stop())
            except Exception:
                pass
            loop.run_until_complete(asyncio.sleep(e.value))
        except KeyboardInterrupt:
            logging.info('Service Stopped Bye 👋')
            break
