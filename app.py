import gzip
import io
import json
import os
import sys

import requests
import spotipy
from dotenv import load_dotenv
from flask import (
    Flask,
    Response,
    redirect,
    render_template,
    request,
    session,
    url_for,
    send_from_directory,
)

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from requests.auth import HTTPBasicAuth
from spotipy.oauth2 import SpotifyOAuth

from google.oauth2.credentials import Credentials


load_dotenv()

KARAOKE_SONGS_FILE = os.getenv("KARAOKE_SONGS_FILE")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

app = Flask(__name__)
app.secret_key = "supersecretkey"


class LogCapture(io.StringIO):
    def __init__(self):
        super().__init__()

    def write(self, s):
        super().write(s)
        sys.__stdout__.write(s)
        sys.__stdout__.flush()


log_capture = LogCapture()


@app.route("/get_log_output", methods=["GET"])
def get_log_output():
    log_output = log_capture.getvalue()
    return Response(log_output, mimetype="text/plain")


sys.stdout = log_capture

@app.route('/favicon.ico')
def send_favicon():
    return send_from_directory('assets', 'favicon.ico')

@app.route('/assets/<path:path>')
def send_asset(path):
    return send_from_directory('assets', path)

@app.route("/authenticate/spotify")
def authenticate_spotify():
    session["spotify_authenticated"] = False
    session["lastfm_authenticated"] = False

    auth_manager = spotipy.SpotifyOAuth(
        client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
        client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
        scope="user-top-read user-follow-read user-library-read",
        cache_path=".cache",
        show_dialog=True,
    )
    auth_url = auth_manager.get_authorize_url()
    return redirect(auth_url)


@app.route("/callback/spotify")
def spotify_callback():
    auth_manager = SpotifyOAuth(
        client_id=os.environ.get("SPOTIFY_CLIENT_ID"),
        client_secret=os.environ.get("SPOTIFY_CLIENT_SECRET"),
        redirect_uri=os.environ.get("SPOTIFY_REDIRECT_URI"),
        scope="user-top-read user-follow-read user-library-read",
        show_dialog=True,
    )
    code = request.args.get("code")
    token_info = auth_manager.get_access_token(code)
    if token_info:
        session["spotify_authenticated"] = True
        session["spotify_auth_token"] = token_info
        print("Spotify authentication successful")
    else:
        print("Spotify authentication failed")
    return redirect(url_for("home"))


@app.route("/authenticate/lastfm")
def authenticate_lastfm():
    session["spotify_authenticated"] = False
    session["lastfm_authenticated"] = True
    session["lastfm_username"] = request.args.get("username")

    print(f'Last.fm authentication successful, username: {session["lastfm_username"]}')

    return redirect(url_for("home"))


def get_google_flow():
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")

    scopes = [
        "https://www.googleapis.com/auth/drive.file",
    ]

    flow = Flow.from_client_secrets_file(
        credentials_path, scopes=scopes, redirect_uri=redirect_uri
    )
    return flow


@app.route("/authorize_google", methods=["GET"])
def authorize_google():
    flow = get_google_flow()
    authorization_url, state = flow.authorization_url(prompt="consent")

    session["google_auth_state"] = state

    return redirect(authorization_url)


@app.route("/authenticate/google", methods=["GET"])
def authenticate_google():
    flow = get_google_flow()
    code = request.args.get("code")

    if code:
        # Save the credentials in the session for later use
        session["google_token"] = flow.fetch_token(code=code)
        session["google_authenticated"] = True

        print("Google authentication successful")
        return redirect(url_for("home"))
    else:
        print("Google authentication failed")
        return redirect(url_for("home"))


def create_google_sheet(title, creds):
    print(f"Creating google sheet with title: {title}")
    service = build("sheets", "v4", credentials=creds)
    spreadsheet = {"properties": {"title": title}}
    spreadsheet = (
        service.spreadsheets()
        .create(body=spreadsheet, fields="spreadsheetId")
        .execute()
    )
    return spreadsheet.get("spreadsheetId")


def write_songs_to_google_sheet(
    spreadsheet_id, songs, artists, top_tracks, creds, music_source
):
    print(f"Writing karaoke songs to google sheet with ID: {spreadsheet_id}")
    service = build("sheets", "v4", credentials=creds)

    # Write headers
    header_values = [
        [
            "Artist",
            "Title",
            "Brands",
            "Artist Play Count",
            "Track Play Count",
            "Popularity at Karaoke",
            "Artist Count x Karaoke Popularity",
            "Track Count x Karaoke Popularity",
        ]
    ]
    header_body = {"values": header_values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1:H1",
        valueInputOption="RAW",
        body=header_body,
    ).execute()

    # Write data
    if music_source == "Spotify":
        artist_play_counts = {artist["name"].lower(): 1 for artist in artists}
        track_play_counts = {
            (track["album"]["artists"][0]["name"].lower(), track["name"].lower()): 1
            for track in top_tracks
        }
    else:
        artist_play_counts = {
            artist["name"].lower(): artist["playcount"] for artist in artists
        }
        track_play_counts = {
            (track["artist"]["name"].lower(), track["name"].lower()): int(
                track["playcount"]
            )
            for track in top_tracks
        }

    data_values = []

    for song in songs:
        brands_list = song["Brands"].split(",")
        play_count_artist = 0

        artist_lower = song["Artist"].lower()
        if artist_lower in artist_play_counts:
            play_count_artist = int(artist_play_counts[artist_lower])

        play_count_track = track_play_counts.get(
            (song["Artist"].lower(), song["Title"].lower()), 0
        )
        popularity = len(brands_list)
        artist_popularity_score = play_count_artist * popularity
        track_popularity_score = play_count_track * popularity

        data_values.append(
            [
                song["Artist"],
                song["Title"],
                song["Brands"],
                play_count_artist,
                play_count_track,
                popularity,
                artist_popularity_score,
                track_popularity_score,
            ]
        )

    data_body = {"values": data_values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"A2:H{len(data_values) + 1}",
        valueInputOption="RAW",
        body=data_body,
    ).execute()


def find_google_sheet_id(sheet_title, creds):
    print(f"Finding google sheet with title: {sheet_title}")
    service = build("drive", "v3", credentials=creds)
    escaped_sheet_title = sheet_title.replace("'", "\\'")  # Escape single quotes
    query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and name='{0}'".format(
        escaped_sheet_title
    )
    results = (
        service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
    )
    items = results.get("files", [])

    if items:
        return items[0]["id"]
    else:
        return None


def get_spotify_user_id(access_token):
    url = "https://api.spotify.com/v1/me"
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers)

    if response.status_code != 200:
        print(f"Failed to fetch user ID. Error {response.status_code}: {response.text}")
        return None

    user_data = response.json()
    user_id = user_data["id"]

    return user_id


def get_top_artists_spotify(
    spotify_user_id, access_token, time_range="long_term", limit=500
):
    cache_file = f"{spotify_user_id}_top_artists_spotify.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(
            f"Found top artists cache file for user ID {spotify_user_id}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_artists = json.load(f)
            return all_top_artists

    print(
        f"No top artists cache file found for user ID {spotify_user_id}, fetching 50 top artists"
    )

    url = "https://api.spotify.com/v1/me/top/artists"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_artists = []

    params = {"time_range": time_range, "limit": limit, "offset": 0}

    response = requests.get(url, headers=headers, params=params)

    if response.status_code != 200:
        print(
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
        print(
            f"Inside followed artists while loop, offset: {followed_artists_offset}, len(all_top_artists): {len(all_top_artists)}"
        )
        followed_artists_params = {"limit": 50, "after": followed_artists_offset}

        followed_artists_response = requests.get(
            followed_artists_url, headers=headers, params=followed_artists_params
        )

        if followed_artists_response.status_code != 200:
            print(
                f"Failed to fetch followed artists. Error {followed_artists_response.status_code}: {followed_artists_response.text}"
            )
            return None

        followed_artists_data = followed_artists_response.json()
        followed_artists = followed_artists_data["artists"]["items"]
        all_top_artists.extend(followed_artists)

        if not followed_artists:
            break

        if len(all_top_artists) > limit:
            print(f"Top artists limit reached, breaking loop: {limit}")
            break

        followed_artists_offset += len(followed_artists)

    # Remove duplicates
    unique_artists = {artist["id"]: artist for artist in all_top_artists}.values()
    unique_artists_list = list(unique_artists)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(unique_artists_list, f)

    return unique_artists_list


def get_top_tracks_spotify(
    spotify_user_id, access_token, time_range="long_term", limit=10000
):
    cache_file = f"{spotify_user_id}_top_tracks_spotify.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(
            f"Found top tracks cache file for user ID {spotify_user_id}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    print(
        f"No top tracks cache file found for user ID {spotify_user_id}, beginning last.fm fetch loop"
    )

    url = "https://api.spotify.com/v1/me/top/tracks"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_tracks = []

    for offset in range(0, limit, 50):
        print(
            f"Inside top tracks for loop, time_range: {time_range}, limit: {limit}, offset: {offset}, len(all_top_tracks): {len(all_top_tracks)}"
        )
        params = {"time_range": time_range, "limit": 50, "offset": offset}

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(
                f"Failed to fetch top tracks. Error {response.status_code}: {response.text}"
            )
            return None

        top_tracks_data = response.json()
        top_tracks = top_tracks_data["items"]
        all_top_tracks.extend(top_tracks)

        if not top_tracks:
            break

        if len(all_top_tracks) > limit:
            print(f"Top tracks limit reached, breaking loop: {limit}")
            break

        offset += limit

    # Fetch saved tracks
    saved_tracks_url = "https://api.spotify.com/v1/me/tracks"
    saved_tracks_offset = 0

    while True:
        print(
            f"Inside saved tracks while loop, offset: {saved_tracks_offset}, len(all_top_tracks): {len(all_top_tracks)}"
        )

        saved_tracks_params = {"limit": 50, "offset": saved_tracks_offset}

        saved_tracks_response = requests.get(
            saved_tracks_url, headers=headers, params=saved_tracks_params
        )

        if saved_tracks_response.status_code != 200:
            print(
                f"Failed to fetch saved tracks. Error {saved_tracks_response.status_code}: {saved_tracks_response.text}"
            )
            return None

        saved_tracks_data = saved_tracks_response.json()
        saved_tracks = [item["track"] for item in saved_tracks_data["items"]]
        all_top_tracks.extend(saved_tracks)

        if len(saved_tracks) < 50:
            break

        if len(all_top_tracks) > limit:
            print(f"Top tracks limit reached, breaking loop: {limit}")
            break

        saved_tracks_offset += len(saved_tracks)

    # Remove duplicates
    unique_tracks = {track["id"]: track for track in all_top_tracks}.values()
    unique_tracks_list = list(unique_tracks)

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(unique_tracks_list, f)

    return unique_tracks_list


def load_karaoke_songs(file_path):
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        data = json.load(f)
        return data


def get_top_artists_lastfm(username, api_key):
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "user.getTopArtists",
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": 500,
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data["topartists"]["artist"]
    else:
        print(
            f"Error {response.status_code}: Failed to fetch top artists for user {username}"
        )
        sys.exit(1)


def get_top_tracks_lastfm(username, api_key):
    cache_file = f"{username}_top_tracks_lastfm.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(
            f"Found top tracks cache file for user {username}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    print(
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
            "api_key": api_key,
            "format": "json",
            "limit": limit,
            "page": page,
        }

        print(
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
                print(
                    f"Fetched less than 1000 tracks while looping for user {username}, breaking out of fetch loop"
                )
                break

            page += 1
        else:
            print(
                f"Error {response.status_code} while fetching top tracks for user {username}, breaking out of fetch loop"
            )
            break

    # Cache fetched data to a file
    with open(cache_file, "w", encoding="utf-8") as f:
        json.dump(all_top_tracks, f)

    return all_top_tracks[:max_tracks]


@app.route("/generate_sheet")
def generate_sheet():
    google_token = session.get("google_token")

    if not google_token:
        return "Google authentication required", 401

    if not session["spotify_authenticated"] and not session["lastfm_authenticated"]:
        return "Spotify authentication or Last.fm username required", 401

    google_creds = Credentials(token=google_token["access_token"])
    karaoke_songs = load_karaoke_songs(KARAOKE_SONGS_FILE)

    if session["spotify_authenticated"]:
        music_source = "Spotify"
        spotify_auth_token = session.get("spotify_auth_token")
        spotify_auth_token = spotify_auth_token["access_token"]

        username = get_spotify_user_id(spotify_auth_token)
        top_artists = get_top_artists_spotify(username, spotify_auth_token)
        top_tracks = get_top_tracks_spotify(username, spotify_auth_token)
    else:
        music_source = "Last.fm"
        username = session.get("lastfm_username")
        top_artists = get_top_artists_lastfm(username, LASTFM_API_KEY)
        top_tracks = get_top_tracks_lastfm(username, LASTFM_API_KEY)

    sheet_title = f"{username}'s Karaoke Songs with {music_source} Data"
    spreadsheet_id = find_google_sheet_id(sheet_title, google_creds)

    if spreadsheet_id is None:
        spreadsheet_id = create_google_sheet(sheet_title, google_creds)

    write_songs_to_google_sheet(
        spreadsheet_id,
        karaoke_songs,
        top_artists,
        top_tracks,
        google_creds,
        music_source,
    )

    print(
        f"Google Sheet URL for user {username}: https://docs.google.com/spreadsheets/d/{spreadsheet_id} "
    )

    print("Karaoke sheet generated successfully")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    return sheet_url


@app.route("/", methods=["GET"])
def home():
    is_authenticated = session.get("spotify_authenticated") and (
        session.get("spotify_authenticated") or session.get("lastfm_authenticated")
    )

    return render_template("home.html", is_authenticated=is_authenticated)


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
