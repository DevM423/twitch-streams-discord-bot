import asyncio
import json
import logging
import os
import sys
import threading
import time
from datetime import datetime, timedelta

import discord
import requests
from discord.ext import tasks
from twitchAPI.twitch import Twitch

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

lock = threading.Lock()

YOUTUBE_STREAMS_ENABLED = False
YOUTUBE_VIDEOS_ENABLED = False

discord_bot_token = os.getenv("DISCORD_BOT_TOKEN")
twitch_client_id = os.getenv("TWITCH_CLIENT_ID")
twitch_oauth_token = os.getenv("TWITCH_OAUTH_TOKEN")
twitch_game_id = os.getenv("TWITCH_GAME_ID")
discord_streams_channel_id = os.getenv("DISCORD_STREAMS_CHANNEL_ID")
discord_videos_channel_id = os.getenv("DISCORD_VIDEOS_CHANNEL_ID")


if not all(
    [
        twitch_client_id,
        twitch_oauth_token,
        discord_bot_token,
        discord_streams_channel_id,
        twitch_game_id,
    ]
):
    logger.error("One or more required environment variables are not set")
    sys.exit(1)


static_game_name = os.getenv("STATIC_GAME_NAME")
google_api_key = os.getenv("GOOGLE_API_KEY")
youtube_search_game_name = os.getenv("YOUTUBE_SEARCH_GAME_NAME")

if YOUTUBE_STREAMS_ENABLED and not all(
    [
        static_game_name,
        google_api_key,
        youtube_search_game_name,
    ]
):
    logger.error("One or more YouTube streams environment variables are not set")
    sys.exit(1)


if YOUTUBE_VIDEOS_ENABLED and not all(
    [
        discord_videos_channel_id,
        static_game_name,
        google_api_key,
        youtube_search_game_name,
    ]
):
    logger.error("One or more YouTube videos environment variables are not set")
    sys.exit(1)


for platform in ["twitch", "youtube"]:
    if not os.path.exists(f"/var/data/last_{platform}_streamers.txt"):
        os.makedirs("/var/data", exist_ok=True)
        open(f"/var/data/last_{platform}_streamers.txt", "w").close()

streams_message = "### {user}\nis currently streaming **{game}**:\t{link}"
videos_message = "### {user}\npublished a new **{game}** video:\t{link}"

seconds_between_messages = 5
minutes_between_checking_streams = 5.0
minutes_between_checking_videos = 30.0

intents = discord.Intents.default()
client = discord.Client(intents=intents)

active_twitch_streamers = set()
active_youtube_streamers = set()
iognored_twitch_streamers = set()
ignored_youtube_streamers = set()


def read_ignored_streamers(platform: str):
    with lock:
        with open(f"/var/data/ignored_{platform}_streamers.txt", "r") as f:
            return set(line.strip() for line in f)

def read_last_streamers(platform: str):
    with lock:
        with open(f"/var/data/last_{platform}_streamers.txt", "r") as f:
            return set(line.strip() for line in f)


def write_last_streamers(platform: str, streamers: set[str]):
    with lock:
        with open(f"/var/data/last_{platform}_streamers.txt", "w") as f:
            for stream in streamers:
                f.write(stream + "\n")


async def send_stream_message(user: str, game: str, link: str):
    channel = client.get_channel(int(discord_streams_channel_id))
    await channel.send(
        streams_message.format(
            user=user,
            game=static_game_name if static_game_name else game,
            link=link,
        )
    )


async def send_video_message(user: str, game: str, link: str):
    channel = client.get_channel(int(discord_videos_channel_id))
    await channel.send(
        videos_message.format(
            user=user,
            game=static_game_name if static_game_name else game,
            link=link,
        )
    )


def make_request_with_retry(url, retries=3, delay=1):
    """Helper function to retry requests with exponential backoff."""
    for attempt in range(retries):
        try:
            response = requests.get(url)
            response.raise_for_status()  # Raises an HTTPError if the status is 4xx, 5xx
            return response.json()
        except requests.exceptions.RequestException as e:
            wait_time = delay * (2 ** attempt)  # Exponential backoff
            time.sleep(wait_time)
            continue
    raise Exception("Request failed after maximum attempts")
    

def get_youtube_streams(page_token: str):
    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&eventType=live&maxResults=100&order=date&q={youtube_search_game_name}&key={google_api_key}"

    if page_token != "":
        url = url + f"&nextPageToken={page_token}"

    return make_request_with_retry(url)


def get_youtube_new_videos(page_token: str):
    thirty_minutes_ago = datetime.utcnow() - timedelta(
        minutes=minutes_between_checking_videos
    )
    published_after = thirty_minutes_ago.strftime("%Y-%m-%dT%H:%M:%SZ").replace(
        ":", "%3A"
    )

    url = f"https://www.googleapis.com/youtube/v3/search?part=snippet&type=video&publishedAfter={published_after}&maxResults=100&order=date&q={youtube_search_game_name}&key={google_api_key}"

    if page_token != "":
        url = url + f"&nextPageToken={page_token}"

    return make_request_with_retry(url)


async def handle_twitch_streams(api):
    global active_twitch_streamers
    global read_ignored_streamers
    previous_streamers = active_twitch_streamers

    # Get all active streams
    streams = [stream async for stream in api.get_streams(game_id=twitch_game_id)]

    # Extract streamers that were not already live
    active_streamers = set(stream.user_name for stream in streams)
    new_streamers = active_streamers - previous_streamers - ignored_streamers
    remaining_streamers = previous_streamers - (previous_streamers - active_streamers)

    for stream in (s for s in streams if s.user_name in new_streamers):
        streamer = stream.user_name
        await send_stream_message(
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
        await send_stream_message(
            streamer,
            static_game_name,
            f"https://www.youtube.com/watch?v={video_id}",
        )
        remaining_streamers.add(streamer)
        active_youtube_streamers = remaining_streamers
        write_last_streamers("youtube", active_youtube_streamers)

        await asyncio.sleep(seconds_between_messages)


async def handle_youtube_new_videos():
    response = get_youtube_new_videos("")
    if "items" not in response:
        return
    videos = list()
    for item in response["items"]:
        videos.append(item)

    for video in (vid for vid in videos):
        channel = video["snippet"]["channelTitle"]
        video_id = video["id"]["videoId"]
        await send_video_message(
            channel,
            static_game_name,
            f"https://www.youtube.com/watch?v={video_id}",
        )

        await asyncio.sleep(seconds_between_messages)


@tasks.loop(minutes=minutes_between_checking_streams, reconnect=True)
async def check_streams(api):
    try:
        await handle_twitch_streams(api)
        if YOUTUBE_STREAMS_ENABLED:
            await handle_youtube_streams()

    except Exception as e:
        logger.info(f"An error occurred: {e}")
        await asyncio.sleep(60)


@tasks.loop(minutes=minutes_between_checking_videos, reconnect=True)
async def check_new_videos():
    try:
        await handle_youtube_new_videos()

    except Exception as e:
        logger.info(f"An error occurred: {e}")
        await asyncio.sleep(60)


@client.event
async def on_ready():
    global active_twitch_streamers
    active_twitch_streamers = read_last_streamers("twitch")
    global active_youtube_streamers
    active_youtube_streamers = read_last_streamers("youtube")
    global ignored_twitch_streamers
    ignored_twitch_streamers = read_ignored_streamers("twitch")
    global ignored_youtube_streamers
    ignored_youtube_streamers = read_ignored_streamers("youtube")

    api = await Twitch(twitch_client_id, twitch_oauth_token)
    if not check_streams.is_running():
        check_streams.start(api)

    if YOUTUBE_VIDEOS_ENABLED and not check_new_videos.is_running():
        check_new_videos.start()


try:
    client.run(discord_bot_token)
except Exception as e:
    logger.error(f"An error occurred while running the bot: {e}")
