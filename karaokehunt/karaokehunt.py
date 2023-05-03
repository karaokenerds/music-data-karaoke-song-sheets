import os
import csv
import random
import string

from flask import (
    redirect,
    request,
    session,
    url_for,
    current_app as app,
    send_from_directory,
)

# autopep8: off
from karaokehunt.youtube import *
from karaokehunt.lastfm import *
from karaokehunt.spotify import *
from karaokehunt.utils import *
from karaokehunt.google import *
from karaokehunt.applemusic import *
from karaokehunt.karaokenerds import *
# autopep8: on

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
CSV_OUTPUT_FILENAME_PREFIX = os.getenv("CSV_OUTPUT_FILENAME_PREFIX")

##########################################################################
###########               Calculate Songs Rows                 ###########
##########################################################################


def calculate_songs_rows(
        all_karaoke_songs, include_zero_score,
        lastfm_artist_playcounts, lastfm_track_playcounts,
        spotify_artist_scores, spotify_track_scores,
        youtube_liked_songs
):
    print(f"Filtering, sorting and calculating karaoke songs rows")

    # Build headers
    header_values = [
        "Artist",
        "Title",
        "Karaoke Brands",
        "Karaoke Popularity",
    ]

    music_source_count = 0

    if spotify_artist_scores is not None:
        header_values.append("Spotify Artist Score")
        header_values.append("Spotify Track Score")
        header_values.append("Spotify Artist Score x Karaoke Popularity")
        header_values.append("Spotify Track Score x Karaoke Popularity")
        music_source_count += 1

    if lastfm_artist_playcounts is not None:
        header_values.append("Last.fm Artist Play Count")
        header_values.append("Last.fm Track Play Count")
        header_values.append("Last.fm Artist Play Count x Karaoke Popularity")
        header_values.append("Last.fm Track Play Count x Karaoke Popularity")
        music_source_count += 1

    if youtube_liked_songs is not None:
        header_values.append("Youtube Artist Liked")
        header_values.append("Youtube Track Liked")
        header_values.append("Youtube Artist Liked x Karaoke Popularity")
        header_values.append("Youtube Track Liked x Karaoke Popularity")
        music_source_count += 1

    if music_source_count > 1:
        header_values.append("Combined Artist Score x Karaoke Popularity")
        header_values.append("Combined Track Score x Karaoke Popularity")

    # Sort by the last column, which will either be the combined score or a single provider track score
    sort_column = len(header_values) - 1

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

    youtube_artist_scores_simple = {}
    youtube_track_scores_simple = {}
    if youtube_liked_songs is not None:
        for track in youtube_liked_songs:
            artist = track[0].lower()
            if artist in youtube_artist_scores_simple:
                youtube_artist_scores_simple[artist] += 1
            else:
                youtube_artist_scores_simple[artist] = 1

        youtube_track_scores_simple = {
            (track[0].lower(), track[1].lower()): 1
            for track in youtube_liked_songs
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

        youtube_artist_score_simple = int(youtube_artist_scores_simple.get(
            artist_lower, 0
        ))
        youtube_track_score_simple = int(youtube_track_scores_simple.get(
            (artist_lower, title_lower), 0
        ))

        song_values = [
            song["Artist"],
            song["Title"],
            song["Brands"],
            popularity
        ]

        combined_artist_score = 0
        combined_track_score = 0

        if spotify_artist_scores is not None:
            combined_artist_score += spotify_artist_score_simple
            combined_track_score += spotify_track_score_simple
            spotify_artist_popularity_score = spotify_artist_score_simple * popularity
            spotify_track_popularity_score = spotify_track_score_simple * popularity
            song_values.append(spotify_artist_score_simple)
            song_values.append(spotify_track_score_simple)
            song_values.append(spotify_artist_popularity_score)
            song_values.append(spotify_track_popularity_score)

        if lastfm_artist_playcounts is not None:
            combined_artist_score += lastfm_artist_playcount_simple
            combined_track_score += lastfm_track_playcount_simple
            lastfm_artist_popularity_score = lastfm_artist_playcount_simple * popularity
            lastfm_track_popularity_score = lastfm_track_playcount_simple * popularity
            song_values.append(lastfm_artist_playcount_simple)
            song_values.append(lastfm_track_playcount_simple)
            song_values.append(lastfm_artist_popularity_score)
            song_values.append(lastfm_track_popularity_score)

        if youtube_liked_songs is not None:
            combined_artist_score += youtube_artist_score_simple
            combined_track_score += youtube_track_score_simple
            youtube_artist_popularity_score = youtube_artist_score_simple * popularity
            youtube_track_popularity_score = youtube_track_score_simple * popularity
            song_values.append(youtube_artist_score_simple)
            song_values.append(youtube_track_score_simple)
            song_values.append(youtube_artist_popularity_score)
            song_values.append(youtube_track_popularity_score)

        if music_source_count > 1:
            combined_artist_popularity_score = (combined_artist_score) * popularity
            combined_track_popularity_score = (combined_track_score) * popularity
            song_values.append(combined_artist_popularity_score)
            song_values.append(combined_track_popularity_score)

        if combined_artist_score > 0 or include_zero_score == "true":
            data_values.append(song_values)

    data_values.sort(key=lambda x: int(x[sort_column]), reverse=True)

    return header_values, data_values


##########################################################################
###########                  Generate Sheet                    ###########
##########################################################################

with app.app_context():
    @app.route("/fetch_csv")
    def fetch_csv():
        username = request.args.get("username")
        return send_from_directory(TEMP_OUTPUT_DIR, f'{CSV_OUTPUT_FILENAME_PREFIX}{username}.csv')

    @app.route("/generate_sheet")
    def generate_sheet():
        include_zero_score = request.args.get('includeZeroScoreSongs')

        if not session.get("spotify_authenticated") and not session.get("lastfm_authenticated") and \
           not session.get("applemusic_authenticated") and not session.get("youtube_authenticated"):
            return "At least one music data source is required", 401

        all_karaoke_songs = load_karaoke_songs()

        spotify_artist_scores = None
        spotify_track_scores = None
        lastfm_artist_playcounts = None
        lastfm_track_playcounts = None
        youtube_liked_songs = None

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

        if session.get("applemusic_authenticated"):
            print("Apple Music auth found, loading applemusic data")
            applemusic_user_access_token = session.get("applemusic_user_access_token")
            username = session.get("applemusic_user_email")

            print(f"Fetching Apple Music data with token: {applemusic_user_access_token}")
            applemusic_artist_playcounts = get_applemusic_library_artists(applemusic_user_access_token)
            applemusic_track_playcounts = get_applemusic_library_songs(applemusic_user_access_token)
            print(f"Apple Music artist counts: {applemusic_artist_playcounts} and track counts: {applemusic_track_playcounts}")

        if session.get("youtube_authenticated"):
            print("Youtube Music auth found, loading youtube data")
            youtube_oauth_token = session.get("youtube_token")

            username = get_youtube_channel_id(youtube_oauth_token)
            youtube_liked_videos = get_liked_videos(username, youtube_oauth_token)
            youtube_liked_songs = identify_songs_from_youtube_videos(username, youtube_liked_videos)

        header_values, data_values = calculate_songs_rows(all_karaoke_songs, include_zero_score,
                                                          lastfm_artist_playcounts, lastfm_track_playcounts,
                                                          spotify_artist_scores, spotify_track_scores,
                                                          youtube_liked_songs)

        print("Karaoke song rows calculated successfully, proceeding to write to CSV or Google Sheet")

        if session.get("google_authenticated"):
            return create_and_write_google_sheet(session.get("google_token"), username, header_values, data_values)
        else:
            print("No google auth found, writing output to CSV file instead")
            csv_file = f'{TEMP_OUTPUT_DIR}/{CSV_OUTPUT_FILENAME_PREFIX}{username}.csv'

            with open(csv_file, 'w') as file:
                writer = csv.writer(file)
                writer.writerow(header_values)
                writer.writerows(data_values)

            return f'/fetch_csv?username={username}'
