import os
import sys
import requests
import gzip
import json
import csv
from dotenv import load_dotenv

import spotipy
import webbrowser
import requests
from requests.auth import HTTPBasicAuth
import base64
import socket
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs

import httplib2
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build


load_dotenv()

KARAOKE_SONGS_FILE = os.getenv("KARAOKE_SONGS_FILE")
LASTFM_API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_USERNAMES = os.getenv("LASTFM_USERNAMES").split(',')

SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
SPOTIFY_REDIRECT_URI = os.getenv("SPOTIFY_REDIRECT_URI")

SPOTIFY_AUTH_CODE = None
MODE = "spotify"

def load_karaoke_songs(file_path):
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
        return data


def get_top_artists_lastfm(username, api_key):
    url = "https://ws.audioscrobbler.com/2.0/"
    params = {
        "method": "user.getTopArtists",
        "user": username,
        "api_key": api_key,
        "format": "json",
        "limit": 500
    }

    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data["topartists"]["artist"]
    else:
        print(f"Error {response.status_code}: Failed to fetch top artists for user {username}")
        sys.exit(1)


def get_top_tracks_lastfm(username, api_key):
    cache_file = f"{username}_top_tracks_lastfm.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(f"Found top tracks cache file for user {username}, loading this instead of fetching again")
        with open(cache_file, 'r', encoding='utf-8') as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    print(f"No top tracks cache file found for user {username}, beginning last.fm fetch loop")

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
            "page": page
        }

        print(f"Inside top tracks fetch loop, page: {page}, fetched_tracks: {fetched_tracks}, max_tracks: {max_tracks}")
        response = requests.get(url, params=params)
        if response.status_code == 200:
            data = response.json()
            tracks = data["toptracks"]["track"]
            num_new_tracks = len(tracks)
            fetched_tracks += num_new_tracks
            all_top_tracks.extend(tracks)

            if num_new_tracks < 1000:
                print(f"Fetched less than 1000 tracks while looping for user {username}, breaking out of fetch loop")
                break

            page += 1
        else:
            print(f"Error {response.status_code} while fetching top tracks for user {username}, breaking out of fetch loop")
            break

    # Cache fetched data to a file
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(all_top_tracks, f)

    return all_top_tracks[:max_tracks]


def filter_songs_by_artists(songs, artists):
    artist_set = set(artist['name'].lower() for artist in artists)
    filtered_songs = [
        song for song in songs if song['Artist'].lower() in artist_set]
    return filtered_songs


def get_google_credentials():
    SCOPES = [
        'https://www.googleapis.com/auth/spreadsheets',
        'https://www.googleapis.com/auth/drive'
    ]
    creds = None
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")

    if os.path.exists('token.json'):
        creds = Credentials.from_authorized_user_file('token.json', SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                credentials_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open('token.json', 'w') as token:
            token.write(creds.to_json())

    return creds


def create_google_sheet(title, creds):
    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = {
        'properties': {
            'title': title
        }
    }
    spreadsheet = service.spreadsheets().create(
        body=spreadsheet, fields='spreadsheetId').execute()
    return spreadsheet.get('spreadsheetId')


def write_songs_to_google_sheet(spreadsheet_id, songs, artists, top_tracks, creds):
    service = build('sheets', 'v4', credentials=creds)

    # Write headers
    header_values = [['Artist', 'Title', 'Brands',
                      'Artist Play Count', 'Track Play Count', 'Popularity at Karaoke',
                      'Artist Count x Karaoke Popularity', 'Track Count x Karaoke Popularity']]
    header_body = {
        'values': header_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range='A1:H1',
        valueInputOption='RAW', body=header_body).execute()

    # Write data
    if MODE == 'spotify':
        artist_play_counts = {artist['name'].lower(): 1 for artist in artists}
        track_play_counts = {(track['album']['artists'][0]['name'].lower(), track['name'].lower()): 1 for track in top_tracks}
    else:
        artist_play_counts = {artist['name'].lower(): artist['playcount'] for artist in artists}
        track_play_counts = {(track['artist']['name'].lower(), track['name'].lower()): int(track['playcount']) for track in top_tracks}
    
    data_values = []

    for song in songs:
        brands_list = song['Brands'].split(',')
        play_count_artist = int(artist_play_counts[song['Artist'].lower()])
        play_count_track = track_play_counts.get(
            (song['Artist'].lower(), song['Title'].lower()), 0)
        popularity = len(brands_list)
        artist_popularity_score = play_count_artist * popularity
        track_popularity_score = play_count_track * popularity

        data_values.append([
            song['Artist'],
            song['Title'],
            song['Brands'],
            play_count_artist,
            play_count_track,
            popularity,
            artist_popularity_score,
            track_popularity_score
        ])

    data_body = {
        'values': data_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f'A2:H{len(data_values) + 1}',
        valueInputOption='RAW', body=data_body).execute()


def find_google_sheet_id(sheet_title, creds):
    service = build('drive', 'v3', credentials=creds)
    escaped_sheet_title = sheet_title.replace("'", "\\'")  # Escape single quotes
    query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and name='{0}'".format(
        escaped_sheet_title)
    results = service.files().list(
        q=query, fields="nextPageToken, files(id, name)").execute()
    items = results.get("files", [])

    if items:
        return items[0]["id"]
    else:
        return None


class RequestHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        global SPOTIFY_AUTH_CODE
        query = urlparse(self.path).query
        query_components = parse_qs(query)

        if 'code' in query_components:
            SPOTIFY_AUTH_CODE = query_components['code'][0]
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response = "<html><body><h1>Authentication successful! You can close this window.</h1></body></html>"
            self.wfile.write(response.encode())
            self.server.stop = True
        else:
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            response = "<html><body><h1>Authentication failed. Please try again.</h1></body></html>"
            self.wfile.write(response.encode())


class StoppableHTTPServer(HTTPServer):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.stop = False

    def serve_forever(self, *args, **kwargs):
        while not self.stop:
            self.handle_request()


def setup_spotify_auth():
    # Step 1: Obtain the authorization URL
    scope = "user-library-read user-top-read user-follow-read user-read-private user-read-email"
    auth_manager = spotipy.SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=scope,
        cache_path=".cache",
        show_dialog=True
    )
    auth_url = auth_manager.get_authorize_url()

    # Step 2: User authorizes the app and provides the code
    webbrowser.open(auth_url)

    # Step 3: Start the local web server to handle the redirect
    httpd = StoppableHTTPServer(('localhost', 8080), RequestHandler)
    print(f"Please open your web browser and log into Spotify / click agree to authenticate your Spotify account:")
    httpd.serve_forever()

    # Step 4: Exchange the code for an access token
    token_info = auth_manager.get_access_token(SPOTIFY_AUTH_CODE)

    return token_info["access_token"]


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


def get_spotify_top_artists(spotify_user_id, access_token, time_range='long_term', limit=500):
    cache_file = f"{spotify_user_id}_top_artists_spotify.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(f"Found top artists cache file for user ID {spotify_user_id}, loading this instead of fetching again")
        with open(cache_file, 'r', encoding='utf-8') as f:
            all_top_artists = json.load(f)
            return all_top_artists

    print(f"No top artists cache file found for user ID {spotify_user_id}, fetching 50 top artists")

    url = "https://api.spotify.com/v1/me/top/artists"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_artists = []

    params = {
        "time_range": time_range,
        "limit": limit,
        "offset": 0
    }

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
        print(f"Inside followed artists while loop, offset: {followed_artists_offset}, len(all_top_artists): {len(all_top_artists)}")
        followed_artists_params = {
            "limit": 50,
            "after": followed_artists_offset
        }

        followed_artists_response = requests.get(followed_artists_url, headers=headers, params=followed_artists_params)

        if followed_artists_response.status_code != 200:
            print(f"Failed to fetch followed artists. Error {followed_artists_response.status_code}: {followed_artists_response.text}")
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
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(unique_artists_list, f)

    return unique_artists_list


def get_spotify_top_tracks(spotify_user_id, access_token, time_range='long_term', limit=10000):
    cache_file = f"{spotify_user_id}_top_tracks_spotify.json"

    # Load data from cache file if it exists
    if os.path.exists(cache_file):
        print(f"Found top tracks cache file for user ID {spotify_user_id}, loading this instead of fetching again")
        with open(cache_file, 'r', encoding='utf-8') as f:
            all_top_tracks = json.load(f)
            return all_top_tracks

    print(f"No top tracks cache file found for user ID {spotify_user_id}, beginning last.fm fetch loop")

    url = "https://api.spotify.com/v1/me/top/tracks"
    headers = {"Authorization": f"Bearer {access_token}"}
    all_top_tracks = []

    for offset in range(0, limit, 50):
        print(f"Inside top tracks for loop, time_range: {time_range}, limit: {limit}, offset: {offset}, len(all_top_tracks): {len(all_top_tracks)}")
        params = {
            "time_range": time_range,
            "limit": 50,
            "offset": offset
        }

        response = requests.get(url, headers=headers, params=params)

        if response.status_code != 200:
            print(f"Failed to fetch top tracks. Error {response.status_code}: {response.text}")
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
        print(f"Inside saved tracks while loop, offset: {saved_tracks_offset}, len(all_top_tracks): {len(all_top_tracks)}")

        saved_tracks_params = {
            "limit": 50,
            "offset": saved_tracks_offset
        }

        saved_tracks_response = requests.get(saved_tracks_url, headers=headers, params=saved_tracks_params)

        if saved_tracks_response.status_code != 200:
            print(f"Failed to fetch saved tracks. Error {saved_tracks_response.status_code}: {saved_tracks_response.text}")
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
    with open(cache_file, 'w', encoding='utf-8') as f:
        json.dump(unique_tracks_list, f)

    return unique_tracks_list


if __name__ == "__main__":
    karaoke_songs = load_karaoke_songs(KARAOKE_SONGS_FILE)
    creds = get_google_credentials()

    spotify_access_token = setup_spotify_auth()
    username = get_spotify_user_id(spotify_access_token)

    top_artists = get_spotify_top_artists(username, spotify_access_token)
    top_tracks = get_spotify_top_tracks(username, spotify_access_token)

    # for username in LASTFM_USERNAMES:
    #     top_artists = get_top_artists_lastfm(username, LASTFM_API_KEY)
    #     top_tracks = get_top_tracks_lastfm(username, LASTFM_API_KEY)

    filtered_songs = filter_songs_by_artists(karaoke_songs, top_artists)

    sheet_title = f"{username}'s Karaoke Songs with Spotify Data"
    spreadsheet_id = find_google_sheet_id(sheet_title, creds)

    if spreadsheet_id is None:
        spreadsheet_id = create_google_sheet(sheet_title, creds)

    write_songs_to_google_sheet(spreadsheet_id, filtered_songs, top_artists, top_tracks, creds)

    print(
        f"Google Sheet URL for user {username}: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
