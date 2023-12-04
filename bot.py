import asyncio
import logging
import os
import sys

import discord
from discord.ext import tasks
from twitchAPI.twitch import Twitch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
twitch_oauth_token = os.getenv("TWITCH_OAUTH_TOKEN")
twitch_game_id = os.getenv("TWITCH_GAME_ID")
discord_channel_id = os.getenv("DISCORD_CHANNEL_ID")

if not all(
    [
        discord_bot_token,
        twitch_client_id,
        twitch_oauth_token,
        twitch_game_id,
        discord_channel_id,
    ]
):
    logger.error("One or more environment variables are not set")
    sys.exit(1)


if not os.path.exists("/var/data/last_streamers.txt"):
    os.makedirs("/var/data", exist_ok=True)
    open("/var/data/last_streamers.txt", "w").close()

static_game_name = os.getenv("STATIC_GAME_NAME")
message = "### {user_name}\nis currently streaming **{game_name}**:\thttps://www.twitch.tv/{user_login}"

seconds_between_messages = 5
minutes_between_checking_streams = 5.0

intents = discord.Intents.default()
client = discord.Client(intents=intents)


def read_last_streamers():
    with open("/var/data/last_streamers.txt", "r") as f:
        return set(line.strip() for line in f)


def write_last_streamers(streams: set[str]):
    with open("/var/data/last_streamers.txt", "w") as f:
        for stream in streams:
            f.write(stream + "\n")


async def send_message(stream):
    channel = client.get_channel(int(discord_channel_id))
    await channel.send(
        message.format(
            user_login=stream.user_login,
            user_name=stream.user_name,
            game_name=static_game_name if static_game_name else stream.game_name,
        )
    )


@tasks.loop(minutes=minutes_between_checking_streams, reconnect=True)
async def check_streams(api):
    try:
        streamers = read_last_streamers()
        streams = [stream async for stream in api.get_streams(game_id=twitch_game_id)]
        streamers = streamers - (
            streamers - set(stream.user_login for stream in streams)
        )
        for stream in (s for s in streams if s.user_login not in streamers):
            await send_message(stream)
            streamers.add(stream.user_login)
            write_last_streamers(streamers)

            await asyncio.sleep(seconds_between_messages)
    except Exception as e:
        logger.info(f"An error occurred: {e}")
        await asyncio.sleep(60)


@client.event
async def on_ready():
    api = await Twitch(twitch_client_id, twitch_oauth_token)
    if not check_streams.is_running():
        check_streams.start(api)


try:
    client.run(discord_bot_token)
except Exception as e:
    logger.error(f"An error occurred while running the bot: {e}")
