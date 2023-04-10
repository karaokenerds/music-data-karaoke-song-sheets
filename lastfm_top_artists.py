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


def load_karaoke_songs(file_path):
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
        return data


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


def write_songs_to_google_sheet(spreadsheet_id, songs, artists, creds):
    service = build('sheets', 'v4', credentials=creds)

    # Write headers
    header_values = [['Artist', 'Title', 'Brands',
                      'Artist Play Count', 'Popularity at Karaoke', 'Score']]
    header_body = {
        'values': header_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range='A1:F1',
        valueInputOption='RAW', body=header_body).execute()

    # Write data
    artist_play_counts = {artist['name'].lower(
    ): artist['playcount'] for artist in artists}
    data_values = []

    for song in songs:
        brands_list = song['Brands'].split(',')
        play_count = int(artist_play_counts[song['Artist'].lower()])
        popularity = len(brands_list)
        score = play_count * popularity

        data_values.append([
            song['Artist'],
            song['Title'],
            song['Brands'],
            play_count,
            popularity,
            score
        ])

    data_body = {
        'values': data_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f'A2:F{len(data_values) + 1}',
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
        filtered_songs = filter_songs_by_artists(karaoke_songs, top_artists)

        sheet_title = f"{username}'s Karaoke Songs"
        spreadsheet_id = find_google_sheet_id(sheet_title, creds)

        if spreadsheet_id is None:
            spreadsheet_id = create_google_sheet(sheet_title, creds)

        write_songs_to_google_sheet(
            spreadsheet_id, filtered_songs, top_artists, creds)

        print(
            f"Google Sheet URL for user {username}: https://docs.google.com/spreadsheets/d/{spreadsheet_id}")
