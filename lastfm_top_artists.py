import os
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

API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_USERNAMES = os.getenv("LASTFM_USERNAMES")
usernames = LASTFM_USERNAMES.split(',')


def get_top_artists(username, limit=500):
    base_url = 'https://ws.audioscrobbler.com/2.0/'
    params = {
        'method': 'user.gettopartists',
        'user': username,
        'api_key': API_KEY,
        'format': 'json',
        'limit': limit
    }

    response = requests.get(base_url, params=params)
    if response.status_code == 200:
        data = response.json()
        return data['topartists']['artist']
    else:
        print(f"Error fetching data from Last.fm API: {response.status_code}")
        return []


def load_karaoke_songs(file_path):
    with gzip.open(file_path, 'rt', encoding='utf-8') as f:
        data = json.load(f)
        return data


def filter_songs_by_artists(songs, artists):
    artist_set = set(artist['name'].lower() for artist in artists)
    filtered_songs = [
        song for song in songs if song['Artist'].lower() in artist_set]
    return filtered_songs


def write_songs_to_csv(songs, artists, output_file):
    artist_play_counts = {artist['name'].lower(
    ): artist['playcount'] for artist in artists}

    with open(output_file, 'w', newline='', encoding='utf-8') as csvfile:
        fieldnames = ['Artist', 'Title', 'Brands',
                      'Artist Play Count', 'Popularity at Karaoke']
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()

        for song in songs:
            brands_list = song['Brands'].split(',')
            writer.writerow({
                'Artist': song['Artist'],
                'Title': song['Title'],
                'Brands': song['Brands'],
                'Artist Play Count': artist_play_counts[song['Artist'].lower()],
                'Popularity at Karaoke': len(brands_list)
            })


def create_google_sheet(title):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
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

    service = build('sheets', 'v4', credentials=creds)
    spreadsheet = {
        'properties': {
            'title': title
        }
    }
    spreadsheet = service.spreadsheets().create(
        body=spreadsheet, fields='spreadsheetId').execute()
    return spreadsheet.get('spreadsheetId')


def write_songs_to_google_sheet(spreadsheet_id, songs, artists):
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
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

    service = build('sheets', 'v4', credentials=creds)

    # Write headers
    header_values = [['Artist', 'Title', 'Brands',
                      'Artist Play Count', 'Popularity at Karaoke']]
    header_body = {
        'values': header_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range='A1:E1',
        valueInputOption='RAW', body=header_body).execute()

    # Write data
    artist_play_counts = {artist['name'].lower(
    ): artist['playcount'] for artist in artists}
    data_values = []

    for song in songs:
        brands_list = song['Brands'].split(',')
        data_values.append([
            song['Artist'],
            song['Title'],
            song['Brands'],
            artist_play_counts[song['Artist'].lower()],
            len(brands_list)
        ])

    data_body = {
        'values': data_values
    }
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=f'A2:E{len(data_values) + 1}',
        valueInputOption='RAW', body=data_body).execute()


if __name__ == "__main__":
    for username in usernames:
        top_artists = get_top_artists(username)

        # Load karaoke songs from the gzip-encoded JSON file
        file_path = 'full-data-latest.json.gz'
        karaoke_songs = load_karaoke_songs(file_path)

        # Filter songs by top artists
        filtered_songs = filter_songs_by_artists(karaoke_songs, top_artists)

        # Write filtered songs to a CSV file
        output_file = f'karaoke_songs_by_top_artists_{username}.csv'
        write_songs_to_csv(filtered_songs, top_artists, output_file)

        print(f"Filtered karaoke songs by top artists saved to {output_file}")

        # Create a new Google Sheet and write the filtered songs to it
        sheet_title = f'Karaoke Songs by Top Artists - {username}'
        spreadsheet_id = create_google_sheet(sheet_title)
        write_songs_to_google_sheet(
            spreadsheet_id, filtered_songs, top_artists)

        sheet_url = f"https://docs.google.com/spreadsheets/d/{spreadsheet_id}/edit"
        print(
            f"Filtered karaoke songs by top artists saved to Google Sheet '{sheet_title}' with URL: {sheet_url}")
