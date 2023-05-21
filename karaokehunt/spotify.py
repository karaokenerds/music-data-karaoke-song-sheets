import os
import requests
import json
import spotipy
import logging

from flask import request, redirect, session, url_for, current_app as app, g

from spotipy.oauth2 import SpotifyOAuth

logger = logging.getLogger("karaokehunt")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")
SPOTIFY_SCOPES = "user-top-read user-follow-read user-library-read"

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

##########################################################################
################           Spotify Auth Flow                ##############
##########################################################################


def get_spotify_user_id(access_token):
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        logger.error(f"Failed to fetch user ID. Error {response.status_code}: {response.text}")
        return None

    user_data = response.json()
    user_id = user_data["id"]

    return user_id


with app.app_context():

    @app.route("/authenticate/spotify")
    def authenticate_spotify():
        cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
        auth_manager = spotipy.SpotifyOAuth(
            client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
            client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
            scope=SPOTIFY_SCOPES,
            cache_handler=cache_handler,
            show_dialog=True,
        )
        auth_url = auth_manager.get_authorize_url()
        return redirect(auth_url)

    @app.route("/callback/spotify")
    def spotify_callback():
        cache_handler = spotipy.cache_handler.FlaskSessionCacheHandler(session)
        auth_manager = SpotifyOAuth(
            client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
            client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
            redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
            scope=SPOTIFY_SCOPES,
            cache_handler=cache_handler,
            show_dialog=True,
        )
        code = request.args.get("code")
        token_info = auth_manager.get_access_token(code)
        if token_info:
            session["spotify_authenticated"] = True
            session["spotify_auth_token"] = token_info
            logger.info("Spotify authentication successful")

            username = get_spotify_user_id(token_info)
            session["spotify_username"] = username
            session["username"] = username
            g.username = username

            logger.info(f"Spotify username stored in session: {username}")
        else:
            logger.error("Spotify authentication failed")
        return redirect(url_for("home"))


##########################################################################
###########                Load Spotify Data                   ###########
##########################################################################


def get_top_artists_spotify(spotify_user_id, access_token):
    cache_file = f"{TEMP_OUTPUT_DIR}/top_artists_spotify_{spotify_user_id}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found top artists cache file for user ID {spotify_user_id}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_artists = json.load(f)
            return all_top_artists

    logger.info(
        f"No top artists cache file found for user ID {spotify_user_id}, fetching 50 top artists"
    )

    limit = 1000
    url = "https://api.spotify.com/v1/me/top/artists"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_artists = []

    time_ranges = ["long_term", "medium_term", "short_term"]
    for time_range in time_ranges:
        params = {"time_range": time_range, "limit": 50}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch top artists. Error {response.status_code}: {response.text}"
            )
            return None

        top_artists_data = response.json()
        top_artists = top_artists_data["items"]
        all_top_artists.extend(top_artists)

    # Fetch followed artists
    followed_artists_url = "https://api.spotify.com/v1/me/following?type=artist"
    followed_artists_offset = 0

    while True:
        logger.info(
            f"Inside followed artists while loop, offset: {followed_artists_offset}, len(all_top_artists): {len(all_top_artists)}"
        )
        followed_artists_params = {"limit": 50, "after": followed_artists_offset}

        followed_artists_response = requests.get(
            followed_artists_url, headers=headers, params=followed_artists_params
        )

        if followed_artists_response.status_code != 200:
            logger.error(
                f"Failed to fetch followed artists. Error {followed_artists_response.status_code}: {followed_artists_response.text}"
            )
            return None

        followed_artists_data = followed_artists_response.json()
        followed_artists = followed_artists_data["artists"]["items"]
        all_top_artists.extend(followed_artists)

        if not followed_artists:
            break

        if len(all_top_artists) > limit:
            logger.info(f"Top artists limit reached, breaking loop: {limit}")
            break

        followed_artists_offset += len(followed_artists)

    # Remove duplicates
    unique_artists = {artist["id"]: artist for artist in all_top_artists}.values()
    unique_artists_list = list(unique_artists)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(unique_artists_list, f)

    return unique_artists_list


def get_top_tracks_spotify(spotify_user_id, access_token):
    cache_file = f"{TEMP_OUTPUT_DIR}/top_tracks_spotify_{spotify_user_id}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found top tracks cache file for user ID {spotify_user_id}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    logger.info(
        f"No top tracks cache file found for user ID {spotify_user_id}, beginning fetch loop"
    )

    limit = 10000
    url = "https://api.spotify.com/v1/me/top/tracks"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_tracks = []

    time_ranges = ["long_term", "medium_term", "short_term"]
    for time_range in time_ranges:
        params = {"time_range": time_range, "limit": 50}
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            logger.error(
                f"Failed to fetch top tracks. Error {response.status_code}: {response.text}"
            )
            return None

        top_tracks_data = response.json()
        top_tracks = top_tracks_data["items"]
        all_top_tracks.extend(top_tracks)

    # Fetch saved tracks
    saved_tracks_url = "https://api.spotify.com/v1/me/tracks"
    saved_tracks_offset = 0

    while True:
        logger.info(
            f"Inside saved tracks while loop, offset: {saved_tracks_offset}, len(all_top_tracks): {len(all_top_tracks)}"
        )

        saved_tracks_params = {"limit": 50, "offset": saved_tracks_offset}

        saved_tracks_response = requests.get(
            saved_tracks_url, headers=headers, params=saved_tracks_params
        )

        if saved_tracks_response.status_code != 200:
            logger.error(
                f"Failed to fetch saved tracks. Error {saved_tracks_response.status_code}: {saved_tracks_response.text}"
            )
            return None

        saved_tracks_data = saved_tracks_response.json()
        saved_tracks = [item["track"] for item in saved_tracks_data["items"]]
        all_top_tracks.extend(saved_tracks)

        if len(saved_tracks) < 50:
            break

        if len(all_top_tracks) > limit:
            logger.info(f"Top tracks limit reached, breaking loop: {limit}")
            break

        saved_tracks_offset += len(saved_tracks)

    # Remove duplicates
    unique_tracks = {track["id"]: track for track in all_top_tracks}.values()
    unique_tracks_list = list(unique_tracks)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(unique_tracks_list, f)

    return unique_tracks_list
