# Simple Game Media Discord Bot

This is a very simple Python Discord Bot that allows game communities to set up automatic notification messages in a Discord server channel when someone starts streaming the set game on Twitch and YouTube or when a new video related to the set game has been published on YouTube.

## Setting up the bot

To set up the bot, simply set the necessary variables in the `.env` file

1. [Create a Twitch App](https://dev.twitch.tv/console/apps) and set the `TWITCH_CLIENT_ID` and `TWITCH_OAUTH_TOKEN`.
2. [Create a Discord Bot](https://discord.com/developers/applications) and set the `DISCORD_BOT_TOKEN`.
3. Copy the Discord Server Channel ID that you want the stream messages be sent in and set the `DISCORD_STREAMS_CHANNEL_ID`.
4. Check what the Twitch ID of the game you want to set the bot up for is and set the `TWITCH_GAME_ID`.

### Optional Settings
5. [Create a Google Project](https://console.cloud.google.com) and set the `GOOGLE_API_KEY`.
6. Copy the Discord Server Channel ID that you want the video messages be sent in and set the `DISCORD_VIDEOS_CHANNEL_ID`.
7. Define the relevant search, which is usually the name of the automatically generated channel for the given game and set the `YOUTUBE_SEARCH_GAME_NAME`.
8. If you want the game name to be something specific instead of the one used by Twitch or your YouTube search term, set a `STATIC_GAME_NAME`. For example the community project `Skylords Reborn` is the only way to play the game `BattleForge`, so it makes sense to change the name in the message.

## Running the bot

To run the bot, simply use the following command to spin up a Docker Container with Docker Compose on a machine that is able to run it and let it handle the rest:

`docker-compose up --build -d`

## Options

You are also able to adjust the time between checking for new streams, new videos and time between messages, as well as how the messages is formatted, if you want to.

That's it and I hope you enjoy it. :)
