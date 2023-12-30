import asyncio
import json
import logging
import os
import sys

import discord
import requests
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


google_api_key = os.getenv("GOOGLE_API_KEY")
youtube_search_game_name = os.getenv("YOUTUBE_SEARCH_GAME_NAME")


for platform in ["twitch", "youtube"]:
    if not os.path.exists(f"/var/data/last_{platform}_streamers.txt"):
        os.makedirs("/var/data", exist_ok=True)
        open(f"/var/data/last_{platform}_streamers.txt", "w").close()

static_game_name = os.getenv("STATIC_GAME_NAME")
message = "### {user}\nis currently streaming **{game}**:\t{link}"

seconds_between_messages = 5
minutes_between_checking_streams = 5.0

intents = discord.Intents.default()
client = discord.Client(intents=intents)

active_twitch_streamers = set()
active_youtube_streamers = set()


def read_last_streamers(platform: str):
    with open(f"/var/data/last_{platform}_streamers.txt", "r") as f:
        return set(line.strip() for line in f)


def write_last_streamers(platform: str, streamers: set[str]):
    with open(f"/var/data/last_{platform}_streamers.txt", "w") as f:
        for stream in streamers:
            f.write(stream + "\n")


async def send_message(user: str, game: str, link: str):
    channel = client.get_channel(int(discord_channel_id))
    await channel.send(
        message.format(
            user=user,
            game=static_game_name if static_game_name else game,
            link=link,
        )
    )


def get_youtube_streams(page_token: str):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&eventType=live&maxResults=100&order=date&q={youtube_search_game_name}&key={google_api_key}"

    if page_token != "":
        url = url + f"&nextPageToken={page_token}"

    response = requests.get(url)
    return json.loads(response.text)


async def handle_twitch_streams(api):
    global active_twitch_streamers
    previous_streamers = active_twitch_streamers

    # Get all active streams
    streams = [stream async for stream in api.get_streams(game_id=twitch_game_id)]

    # Extract streamers that were not already live
    active_streamers = set(stream.user_name for stream in streams)
    new_streamers = active_streamers - previous_streamers
    remaining_streamers = previous_streamers - (previous_streamers - active_streamers)

    for stream in (s for s in streams if s.user_name in new_streamers):
        streamer = stream.user_name
        await send_message(
            streamer,
            stream.game_name,
            f"https://www.twitch.tv/{streamer}",
        )
        remaining_streamers.add(streamer)
        active_twitch_streamers = remaining_streamers
        write_last_streamers("twitch", active_twitch_streamers)

        await asyncio.sleep(seconds_between_messages)


async def handle_youtube_streams():
    global active_youtube_streamers
    previous_streamers = active_youtube_streamers

    # Get all active streams
    response = get_youtube_streams("")
    if "items" not in response:
        return
    streams = list()
    for item in response["items"]:
        streams.append(item)

    # Additional steps are necessary if there are more than 100 active streams
    # may run into issues with the youtube api request limits
    # page_token = response["nextPageToken"]
    # while "nextPageToken" in response:
    #     response = get_youtube_streams(page_token)
    #     for item in response["items"]:
    #         streams.append(item)
    #     if page_token == response["nextPageToken"]:
    #         break

    # Extract streamers that were not already live
    active_streamers = set(stream["snippet"]["channelTitle"] for stream in streams)
    new_streamers = active_streamers - previous_streamers
    remaining_streamers = previous_streamers - (previous_streamers - active_streamers)

    for stream in (s for s in streams if s["snippet"]["channelTitle"] in new_streamers):
        streamer = stream["snippet"]["channelTitle"]
        video_id = stream["id"]["videoId"]
        await send_message(
            streamer,
            static_game_name,
            f"https://www.youtube.com/watch?v={video_id}",
        )
        remaining_streamers.add(streamer)
        active_youtube_streamers = remaining_streamers
        write_last_streamers("youtube", active_youtube_streamers)

        await asyncio.sleep(seconds_between_messages)


@tasks.loop(minutes=minutes_between_checking_streams, reconnect=True)
async def check_streams(api):
    try:
        await handle_twitch_streams(api)
        if google_api_key and youtube_search_game_name:
            await handle_youtube_streams()

    except Exception as e:
        logger.info(f"An error occurred: {e}")
        await asyncio.sleep(60)


@client.event
async def on_ready():
    global active_twitch_streamers
    active_twitch_streamers = read_last_streamers("twitch")
    global active_youtube_streamers
    active_youtube_streamers = read_last_streamers("youtube")

    api = await Twitch(twitch_client_id, twitch_oauth_token)
    if not check_streams.is_running():
        check_streams.start(api)


try:
    client.run(discord_bot_token)
except Exception as e:
    logger.error(f"An error occurred while running the bot: {e}")
