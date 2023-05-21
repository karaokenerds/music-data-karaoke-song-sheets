import yt_dlp as youtube_dl
import os
import json
import logging

from flask import redirect, request, session, url_for, current_app as app, g

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from google.oauth2.credentials import Credentials

logger = logging.getLogger("karaokehunt")

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

##########################################################################
###############           Youtube Auth Flow                 ##############
##########################################################################


def get_youtube_flow():
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    redirect_uri = os.environ.get("YOUTUBE_REDIRECT_URI")

    scopes = "https://www.googleapis.com/auth/youtube.readonly"

    flow = Flow.from_client_secrets_file(
        credentials_path, scopes=scopes, redirect_uri=redirect_uri
    )
    return flow


with app.app_context():

    @app.route("/authorize_youtube", methods=["GET"])
    def authorize_youtube():
        flow = get_youtube_flow()
        authorization_url, state = flow.authorization_url(prompt="consent")

        session["youtube_auth_state"] = state

        return redirect(authorization_url)

    @app.route("/authenticate/youtube", methods=["GET"])
    def authenticate_youtube():
        flow = get_youtube_flow()
        code = request.args.get("code")

        if code:
            # Save the credentials in the session for later use
            session["youtube_token"] = flow.fetch_token(code=code)
            session["youtube_authenticated"] = True

            username = get_youtube_channel_id(session["youtube_token"])
            session["youtube_username"] = username
            session["username"] = username
            g.username = username

            logger.info(f"Youtube authentication successful, username: {username}")
            return redirect(url_for("home"))
        else:
            logger.info("Youtube authentication failed")
            return redirect(url_for("home"))


##########################################################################
###########                Load YouTube Video Data             ###########
##########################################################################


def get_youtube_channel_id(google_token):
    logger.info(f"Finding youtube username for authenticated user")

    # Create an authorized YouTube API client
    credentials = Credentials(token=google_token["access_token"])
    youtube = build("youtube", "v3", credentials=credentials)

    # Retrieve the user's YouTube channel
    channels_request = youtube.channels().list(part="id", mine=True)
    channels_response = channels_request.execute()

    # Extract the channel ID
    if "items" in channels_response and len(channels_response["items"]) > 0:
        channel_id = channels_response["items"][0]["id"]
        return channel_id
    else:
        return None


def get_liked_videos(userid, google_token):
    cache_file = f"{TEMP_OUTPUT_DIR}/youtube_liked_videos_{userid}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found liked videos cache file for user ID {userid}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            liked_videos = json.load(f)
            return liked_videos

    logger.info(
        f"No liked videos cache file found for user ID {userid}, fetching up to 10k liked videos"
    )

    # Create an authorized YouTube API client
    credentials = Credentials(token=google_token["access_token"])
    youtube = build("youtube", "v3", credentials=credentials)

    # Retrieve the user's channel
    channels_request = youtube.channels().list(part="contentDetails", mine=True)
    channels_response = channels_request.execute()

    if "items" in channels_response and len(channels_response["items"]) > 0:
        logger.info(channels_response["items"][0]["contentDetails"])

        likes_playlist_id = channels_response["items"][0]["contentDetails"][
            "relatedPlaylists"
        ]["likes"]
    else:
        return None

    liked_videos = []
    next_page_token = None
    num_results = 0
    max_results = 10000

    # Retrieve the liked videos using pagination
    while num_results < max_results:
        logger.info(
            f"Inside liked videos fetch loop, num_results: {num_results}, max_results: {max_results}"
        )

        # Retrieve the current page of liked videos
        likes_request = youtube.playlistItems().list(
            part="snippet",
            playlistId=likes_playlist_id,
            maxResults=min(50, max_results - num_results),
            pageToken=next_page_token,
        )
        likes_response = likes_request.execute()

        # Extract the video details
        for item in likes_response["items"]:
            video_id = item["snippet"]["resourceId"]["videoId"]
            video_title = item["snippet"]["title"]
            liked_videos.append((video_id, video_title))
            num_results += 1

        # If there's a nextPageToken, update the token and continue fetching
        if "nextPageToken" in likes_response:
            next_page_token = likes_response["nextPageToken"]
        else:
            break

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(liked_videos, f)

    return liked_videos


def identify_songs_from_youtube_videos(userid, liked_videos):
    cache_file = f"{TEMP_OUTPUT_DIR}/youtube_liked_songs_{userid}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found liked songs cache file for user ID {userid}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            liked_songs = json.load(f)
            return liked_songs

    logger.info(
        f"No liked songs cache file found for user ID {userid}, running all liked videos through identification"
    )

    logger.info(f"Attempting to identify songs from {len(liked_videos)} youtube videos")
    liked_songs = []

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "nocheckcertificate": True,
        "skip_download": True,
    }

    total = len(liked_videos)
    count = 0

    for video in liked_videos:
        video_id = video[0]

        identified_count = len(liked_songs)
        if count == 0 or (count % 10) == 0:
            logger.info(
                f"Inside youtube song identification loop, processed: {count} of total: {total}, identified: {identified_count}"
            )

        try:
            with youtube_dl.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(
                    f"https://www.youtube.com/watch?v={video_id}", download=False
                )

                if "artist" in info and "track" in info:
                    liked_songs.append((info["artist"], info["track"]))

        except Exception as e:
            logger.info(f"Error extracting metadata for video ID {video_id}: {e}")

        count += 1

    logger.info(f"Successfully identified {len(liked_songs)} songs from youtube videos")

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(liked_songs, f)

    return liked_songs
