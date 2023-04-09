import os
import requests
import gzip
import json
import csv
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv("LASTFM_API_KEY")
LASTFM_USERNAMES = os.getenv("LASTFM_USERNAMES")


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


if __name__ == "__main__":
    usernames = LASTFM_USERNAMES.split(',')

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
