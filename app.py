import os

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    request,
    session,
)

from google.oauth2.credentials import Credentials

##########################################################################
###################            Init and Setup               ##############
##########################################################################

load_dotenv()

app = Flask(__name__)
app.config.from_prefixed_env()
app.app_context().push()

from karaokehunt.karaokenerds import *
from karaokehunt.google import *
from karaokehunt.utils import *
from karaokehunt.spotify import *
from karaokehunt.lastfm import *

##########################################################################
###########               Calculate Songs Rows                 ###########
##########################################################################


def calculate_songs_rows(
        all_karaoke_songs, include_zero_score,
        lastfm_artist_playcounts, lastfm_track_playcounts,
        spotify_artist_scores, spotify_track_scores
):
    print(f"Filtering, sorting and calculating karaoke songs rows")

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

    return header_values, data_values


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

    header_values, data_values = calculate_songs_rows(all_karaoke_songs, include_zero_score,
                                                      lastfm_artist_playcounts, lastfm_track_playcounts,
                                                      spotify_artist_scores, spotify_track_scores)

    write_rows_to_google_sheet(spreadsheet_id, google_creds, header_values, data_values)

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
