import os
import sys
import requests
import gzip
import json
import csv
from dotenv import load_dotenv

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


def load_karaoke_songs(file_path):
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
        return data


def get_top_artists(username, api_key):
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


def get_top_tracks(username, api_key):
    cache_file = f"{username}_top_tracks.json"

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
    artist_play_counts = {artist['name'].lower(
    ): artist['playcount'] for artist in artists}
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


if __name__ == "__main__":
    karaoke_songs = load_karaoke_songs(KARAOKE_SONGS_FILE)
    creds = get_google_credentials()

    for username in LASTFM_USERNAMES:
        top_artists = get_top_artists(username, LASTFM_API_KEY)
        top_tracks = get_top_tracks(username, LASTFM_API_KEY)

        filtered_songs = filter_songs_by_artists(karaoke_songs, top_artists)

        sheet_title = f"{username}'s Karaoke Songs"
        spreadsheet_id = find_google_sheet_id(sheet_title, creds)

        if spreadsheet_id is None:
            spreadsheet_id = create_google_sheet(sheet_title, creds)

        write_songs_to_google_sheet(spreadsheet_id, filtered_songs, top_artists, top_tracks, creds)

        print(
            f"Google Sheet URL for user {username}: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
