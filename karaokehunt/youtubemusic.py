import os
import json

from flask import (
    redirect,
    request,
    session,
    url_for,
    current_app as app
)

from google_auth_oauthlib.flow import Flow
from ytmusicapi import YTMusic

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

##########################################################################
################           youtubemusic Auth Flow                 ##############
##########################################################################


def get_youtubemusic_flow():
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    redirect_uri = os.environ.get("YOUTUBEMUSIC_REDIRECT_URI")

    scopes = "https://www.googleapis.com/auth/youtube"

    flow = Flow.from_client_secrets_file(
        credentials_path, scopes=scopes, redirect_uri=redirect_uri
    )
    return flow


with app.app_context():
    @app.route("/authorize_youtubemusic", methods=["GET"])
    def authorize_youtubemusic():
        flow = get_youtubemusic_flow()
        authorization_url, state = flow.authorization_url(prompt="consent")

        session["youtubemusic_auth_state"] = state

        return redirect(authorization_url)

    @app.route("/authenticate/youtubemusic", methods=["GET"])
    def authenticate_youtubemusic():
        flow = get_youtubemusic_flow()
        code = request.args.get("code")

        if code:
            # Save the credentials in the session for later use
            session["youtubemusic_token"] = flow.fetch_token(code=code)
            session["youtubemusic_authenticated"] = True

            print(f'youtubemusic authentication successful')
            return redirect(url_for("home"))
        else:
            print("youtubemusic authentication failed")
            return redirect(url_for("home"))


##########################################################################
###########                Load YouTube Music Data             ###########
##########################################################################

def get_library_artists_youtubemusic(username, token):
    cache_file = f'{TEMP_OUTPUT_DIR}/library_artists_youtubemusic_{username}.json'

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print("Found library artists cache file, loading this instead of fetching again")
        with open(cache_file, "r", encoding="utf-8") as f:
            library_artists = json.load(f)
            return library_artists

    print("No library artists cache file found, fetching from YouTube Music")

    ytmusic = YTMusic(token)
    library_artists = ytmusic.get_library_artists(limit=10000)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(library_artists, f)

    return library_artists


def get_library_songs_youtubemusic(username, token):
    cache_file = f'{TEMP_OUTPUT_DIR}/library_songs_youtubemusic_{username}.json'

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print("Found library songs cache file, loading this instead of fetching again")
        with open(cache_file, "r", encoding="utf-8") as f:
            library_songs = json.load(f)
            return library_songs

    print("No library songs cache file found, fetching from YouTube Music")

    ytmusic = YTMusic(token)
    library_songs = ytmusic.get_library_songs(limit=10000)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(library_songs, f)

    return library_songs
