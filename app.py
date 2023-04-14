import gzip
import io
import json
import os
import sys
from pathlib import Path
import urllib.request
from datetime import datetime, timedelta

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

##########################################################################
###################            Init and Setup               ##############
##########################################################################

load_dotenv()

KARAOKE_SONGS_FILE = os.getenv("KARAOKE_SONGS_FILE")
KARAOKE_SONGS_URL = os.getenv("KARAOKE_SONGS_URL")

LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
LOG_FILE_NAME = os.getenv("LOG_FILE_NAME")

app = Flask(__name__)
app.secret_key = "supersecretkey"

class LogCapture(io.StringIO):
    def __init__(self):
        super().__init__()
        self.logfile = open(f'{TEMP_OUTPUT_DIR}/{LOG_FILE_NAME}', "a")

    def write(self, s):
        super().write(s)
        self.logfile.write(s)
        sys.__stdout__.write(s)
        sys.__stdout__.flush()


log_capture = LogCapture()
sys.stdout = log_capture

def is_file_older_than(file, delta): 
    cutoff = datetime.utcnow() - delta
    mtime = datetime.utcfromtimestamp(os.path.getmtime(file))
    if mtime < cutoff:
        return True
    return False

##########################################################################
###################           Utility Routes                ##############
##########################################################################

@app.route("/logs", methods=["GET"])
def get_log_output():
    log_output = log_capture.getvalue()
    return Response(log_output, mimetype="text/plain")

@app.route('/favicon.ico')
def send_favicon():
    return send_from_directory('assets', 'favicon.ico')

@app.route('/assets/<path:path>')
def send_asset(path):
    return send_from_directory('assets', path)

@app.route("/reset")
def reset_session():
    session.clear()
    return redirect(url_for("home"))

##########################################################################
################           Spotify Auth Flow                ##############
##########################################################################

@app.route("/authenticate/spotify")
def authenticate_spotify():
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

##########################################################################
################           Last.fm Auth Flow                ##############
##########################################################################

@app.route("/authenticate/lastfm")
def authenticate_lastfm():
    session["lastfm_username"] = request.args.get("username")
    session["lastfm_authenticated"] = True

    print(f'Last.fm authentication successful, username: {session["lastfm_username"]}')

    return redirect(url_for("home"))


##########################################################################
################           Google Auth Flow                 ##############
##########################################################################

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


##########################################################################
###########          Google Sheet Find & Create                ###########
##########################################################################

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


##########################################################################
###########            Load Karaoke Nerds Data                 ###########
##########################################################################

def load_karaoke_songs():
    file_path = Path(f'{TEMP_OUTPUT_DIR}/{KARAOKE_SONGS_FILE}')
    needs_fetch = False

    if not file_path.is_file():
        print(f"Karaoke song DB file not found, download required")
        needs_fetch = True
    else:
        if is_file_older_than(file_path, timedelta(days=3)):
            print(f"Karaoke song DB is older than 3 days, download required")
            needs_fetch = True

    if needs_fetch:
        print(f"Downloading latest karaoke song DB from firebase storage")
        urllib.request.urlretrieve(KARAOKE_SONGS_URL, file_path)
        
    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        print(f"Successfully opened karaoke song DB")
        data = json.load(f)
        return data


##########################################################################
###########                Load Spotify Data                   ###########
##########################################################################

def get_top_artists_spotify(spotify_user_id, access_token):
    cache_file = f'{TEMP_OUTPUT_DIR}/top_artists_spotify_{spotify_user_id}.json'

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

    limit = 1000
    url = "https://api.spotify.com/v1/me/top/artists"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_artists = []

    time_ranges = ["long_term", "medium_term", "short_term"]
    for time_range in time_ranges:
        params = {"time_range": time_range, "limit": 50}   
        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"Failed to fetch top artists. Error {response.status_code}: {response.text}")
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


def get_top_tracks_spotify(spotify_user_id, access_token):
    cache_file = f'{TEMP_OUTPUT_DIR}/top_tracks_spotify_{spotify_user_id}.json'

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(
            f"Found top tracks cache file for user ID {spotify_user_id}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    print(
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
            print(f"Failed to fetch top tracks. Error {response.status_code}: {response.text}")
            return None

        top_tracks_data = response.json()
        top_tracks = top_tracks_data["items"]
        all_top_tracks.extend(top_tracks)

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


##########################################################################
###########                Load Last.fm Data                   ###########
##########################################################################


def get_top_artists_lastfm(username):
    cache_file = f'{TEMP_OUTPUT_DIR}/top_artists_lastfm_{username}.json'

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(
            f"Found top artists cache file for user {username}, loading this instead of fetching again"
        )
        with open(cache_file, "r", encoding="utf-8") as f:
            all_top_artists = json.load(f)
            return all_top_artists

    print(
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
        print(
            f"Error {response.status_code}: Failed to fetch top artists for user {username}"
        )
        sys.exit(1)


def get_top_tracks_lastfm(username):
    cache_file = f'{TEMP_OUTPUT_DIR}/top_tracks_lastfm_{username}.json'

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
            "api_key": LASTFM_API_KEY,
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



##########################################################################
###########                Write Rows to Sheet                 ###########
##########################################################################

def write_songs_to_google_sheet(
    spreadsheet_id, google_creds, all_karaoke_songs, include_zero_score,
    lastfm_artist_playcounts, lastfm_track_playcounts, 
    spotify_artist_scores, spotify_track_scores
):
    print(f"Writing karaoke songs to google sheet with ID: {spreadsheet_id}")
    service = build("sheets", "v4", credentials=google_creds)

    # Write headers
    header_values = [
        "Artist",
        "Title",
        "Karaoke Brands",
        "Karaoke Popularity",
    ]

    if spotify_artist_scores is not None:
        header_values.append("Spotify Artist Score")
        header_values.append("Spotify Track Score")
        header_values.append("Spotify Artist Score x Karaoke Popularity")
        header_values.append("Spotify Track Score x Karaoke Popularity")

    if lastfm_artist_playcounts is not None:
        header_values.append("Last.fm Artist Play Count")
        header_values.append("Last.fm Track Play Count")
        header_values.append("Last.fm Artist Play Count x Karaoke Popularity")
        header_values.append("Last.fm Track Play Count x Karaoke Popularity")
    
    # If there's only one music data provider, sort by that provider's track x popularity column (7)
    sort_column = 7
    if spotify_artist_scores is not None and lastfm_artist_playcounts is not None:
        header_values.append("Combined Artist Score x Karaoke Popularity")
        header_values.append("Combined Track Score x Karaoke Popularity")

        # If there's more than one music data provider, sort by the combined track x popularity column (13)
        sort_column = 13

    header_body = {"values": [header_values]}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1:N1",
        valueInputOption="RAW",
        body=header_body,
    ).execute()

    # Combine track data
    spotify_artist_scores_simple = {}
    spotify_track_scores_simple = {}
    if spotify_artist_scores is not None:
        spotify_artist_scores_simple = {artist["name"].lower(): artist["popularity"] for artist in spotify_artist_scores}

    if spotify_track_scores is not None:
        for track in spotify_track_scores:
            try:
                spotify_track_scores_simple[(track["album"]["artists"][0]["name"].lower(), track["name"].lower())] = track["popularity"]
            except:
                print(f'Failed to add track {track["name"]} as it had no album artists')
    
    lastfm_artist_playcounts_simple = {}
    lastfm_track_playcounts_simple = {}
    if lastfm_artist_playcounts is not None:
        lastfm_artist_playcounts_simple = {
            artist["name"].lower(): artist["playcount"] for artist in lastfm_artist_playcounts
        }
    
    if lastfm_track_playcounts is not None:
        lastfm_track_playcounts_simple = {
            (track["artist"]["name"].lower(), track["name"].lower()): int(
                track["playcount"]
            )
            for track in lastfm_track_playcounts
        }

    data_values = []

    for song in all_karaoke_songs:
        brands_list = song["Brands"].split(",")
        artist_lower = song["Artist"].lower()
        title_lower = song["Title"].lower()
    
        popularity = len(brands_list)

        spotify_artist_score_simple = 0
        spotify_track_score_simple = 0
        lastfm_artist_playcount_simple = 0
        lastfm_track_playcount_simple = 0

        spotify_artist_score_simple = int(spotify_artist_scores_simple.get(
            artist_lower, 0
        ))
        spotify_track_score_simple = int(spotify_track_scores_simple.get(
            (artist_lower, title_lower), 0
        ))

        lastfm_artist_playcount_simple = int(lastfm_artist_playcounts_simple.get(
            artist_lower, 0
        ))
        lastfm_track_playcount_simple = int(lastfm_track_playcounts_simple.get(
            (artist_lower, title_lower), 0
        ))

        song_values = [
            song["Artist"],
            song["Title"],
            song["Brands"],
            popularity
        ]

        if spotify_artist_scores is not None:
            spotify_artist_popularity_score = spotify_artist_score_simple * popularity
            spotify_track_popularity_score = spotify_track_score_simple * popularity
            song_values.append(spotify_artist_score_simple)
            song_values.append(spotify_track_score_simple)
            song_values.append(spotify_artist_popularity_score)
            song_values.append(spotify_track_popularity_score)

        if lastfm_artist_playcounts is not None:
            lastfm_artist_popularity_score = lastfm_artist_playcount_simple * popularity
            lastfm_track_popularity_score = lastfm_track_playcount_simple * popularity
            song_values.append(lastfm_artist_playcount_simple)
            song_values.append(lastfm_track_playcount_simple)
            song_values.append(lastfm_artist_popularity_score)
            song_values.append(lastfm_track_popularity_score)

        if spotify_artist_scores is not None and lastfm_artist_playcounts is not None:
            combined_artist_popularity_score = (spotify_artist_score_simple + lastfm_artist_playcount_simple) * popularity
            combined_track_popularity_score = (spotify_track_score_simple + lastfm_track_playcount_simple) * popularity
            song_values.append(combined_artist_popularity_score)
            song_values.append(combined_track_popularity_score)
            
        data_values.append(song_values)

    if include_zero_score != "true":
        data_values = [x for x in data_values if x[sort_column] > 0]
    
    data_values.sort(key=lambda x: int(x[sort_column]), reverse=True)

    data_body = {"values": data_values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"A2:N{len(data_values) + 1}",
        valueInputOption="RAW",
        body=data_body,
    ).execute()


##########################################################################
###########                  Generate Sheet                    ###########
##########################################################################

@app.route("/generate_sheet")
def generate_sheet():
    google_token = session.get("google_token")
    include_zero_score = request.args.get('includeZeroScoreSongs')

    if not google_token:
        return "Google authentication required", 401

    if not session.get("spotify_authenticated") and not session.get("lastfm_authenticated"):
        return "At least one music data source is required", 401

    google_creds = Credentials(token=google_token["access_token"])
    all_karaoke_songs = load_karaoke_songs()

    spotify_artist_scores = None
    spotify_track_scores = None
    lastfm_artist_playcounts = None
    lastfm_track_playcounts = None

    if session.get("spotify_authenticated"):
        print("Spotify auth found, loading spotify data")
        spotify_auth_token = session.get("spotify_auth_token")
        spotify_auth_token = spotify_auth_token["access_token"]

        username = get_spotify_user_id(spotify_auth_token)
        spotify_artist_scores = get_top_artists_spotify(username, spotify_auth_token)
        spotify_track_scores = get_top_tracks_spotify(username, spotify_auth_token)

    if session.get("lastfm_authenticated"):
        print("Last.fm auth found, loading lastfm data")
        username = session.get("lastfm_username")
        lastfm_artist_playcounts = get_top_artists_lastfm(username)
        lastfm_track_playcounts = get_top_tracks_lastfm(username)

    sheet_title = f"{username}'s KaraokeHunt Sheet"
    spreadsheet_id = find_google_sheet_id(sheet_title, google_creds)

    if spreadsheet_id is None:
        spreadsheet_id = create_google_sheet(sheet_title, google_creds)

    write_songs_to_google_sheet(
        spreadsheet_id, google_creds, all_karaoke_songs, include_zero_score,
        lastfm_artist_playcounts, lastfm_track_playcounts, 
        spotify_artist_scores, spotify_track_scores
    )

    print(
        f"Google Sheet URL for user {username}: https://docs.google.com/spreadsheets/d/{spreadsheet_id} "
    )

    print("Karaoke sheet generated successfully")

    sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}"
    return sheet_url


##########################################################################
###########          Render HTML template with strings         ###########
##########################################################################

@app.route("/", methods=["GET"])
def home():
    spotify_authenticated = "spotify_authenticated" if session.get("spotify_authenticated") else ""
    lastfm_authenticated = "lastfm_authenticated" if session.get("lastfm_authenticated") else ""
    google_authenticated = "google_authenticated" if session.get("google_authenticated") else ""
    lastfm_username = session.get("lastfm_username") if session.get("lastfm_username") else ""

    return render_template(
        "home.html", 
        spotify_authenticated=spotify_authenticated, 
        lastfm_authenticated=lastfm_authenticated,
        google_authenticated=google_authenticated,
        lastfm_username=lastfm_username
    )


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
