import json
import os
import sys
import requests
import logging

from flask import request, redirect, session, url_for, current_app as app, g

logger = logging.getLogger("karaokehunt")

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

##########################################################################
################           Last.fm Auth Flow                ##############
##########################################################################

with app.app_context():

    @app.route("/authenticate/lastfm")
    def authenticate_lastfm():
        username = request.args.get("username")
        session["lastfm_username"] = username
        session["username"] = username
        g.username = username
        session["lastfm_authenticated"] = True

        logger.info(f"Last.fm username stored in session: {username}")

        return redirect(url_for("home"))


##########################################################################
###########                Load Last.fm Data                   ###########
##########################################################################


def get_top_artists_lastfm(username):
    cache_file = f"{TEMP_OUTPUT_DIR}/top_artists_lastfm_{username}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found top artists cache file for user {username}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_artists = json.load(f)
            return all_top_artists

    logger.info(
        f"No top artists cache file found for user {username}, fetching from last.fm"
    )

    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "user.getTopArtists",
        "user": username,
        "api_key": LASTFM_API_KEY,
        "format": "json",
        "limit": 1000,
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        all_top_artists = data["topartists"]["artist"]

        # Cache fetched data to a file
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(all_top_artists, f)

        return all_top_artists
    else:
        logger.error(
            f"Error {response.status_code}: Failed to fetch top artists for user {username}"
        )
        sys.exit(1)


def get_top_tracks_lastfm(username):
    cache_file = f"{TEMP_OUTPUT_DIR}/top_tracks_lastfm_{username}.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        logger.info(
            f"Found top tracks cache file for user {username}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    logger.info(
        f"No top tracks cache file found for user {username}, beginning last.fm fetch loop"
    )

    # Fetch data from last.fm API and cache it to the file
    url = "https://ws.audioscrobbler.com/2.0/"
    all_top_tracks = []
    limit = 1000
    max_tracks = 10000
    fetched_tracks = 0
    page = 1

    while fetched_tracks < max_tracks:
        params = {
            "method": "user.getTopTracks",
            "user": username,
            "api_key": LASTFM_API_KEY,
            "format": "json",
            "limit": limit,
            "page": page,
        }

        logger.info(
            f"Inside top tracks fetch loop, page: {page}, fetched_tracks: {fetched_tracks}, max_tracks: {max_tracks}"
        )
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            tracks = data["toptracks"]["track"]
            num_new_tracks = len(tracks)
            fetched_tracks += num_new_tracks
            all_top_tracks.extend(tracks)

            if num_new_tracks < 1000:
                logger.info(
                    f"Fetched less than 1000 tracks while looping for user {username}, breaking out of fetch loop"
                )
                break

            page += 1
        else:
            logger.error(
                f"Error {response.status_code} while fetching top tracks for user {username}, breaking out of fetch loop"
            )
            break

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(all_top_tracks, f)

    return all_top_tracks[:max_tracks]
