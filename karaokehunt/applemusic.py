import os
import jwt
import requests
from time import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from flask import redirect, request, session, url_for, current_app as app

APPLE_MUSIC_TEAM_ID = os.environ.get("APPLE_MUSIC_TEAM_ID")
APPLE_MUSIC_CLIENT_ID = os.environ.get("APPLE_MUSIC_CLIENT_ID")
APPLE_MUSIC_KEY_ID = os.environ.get("APPLE_MUSIC_KEY_ID")
APPLE_MUSIC_CREDENTIALS_PATH = os.environ.get("APPLE_MUSIC_CREDENTIALS_PATH")
APPLE_MUSIC_REDIRECT_URI = os.environ.get("APPLE_MUSIC_REDIRECT_URI")

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

##########################################################################
################             Apple Auth Flow                ##############
##########################################################################

with app.app_context():
    @app.route("/authenticate/applemusic", methods=["GET"])
    def authorize_applemusic():
        print("Entering authorize_applemusic")
        client_secret = generate_client_secret()
        session["applemusic_client_secret"] = client_secret
        print(f"Set client_secret to {client_secret}")

        authorization_url = (
            f"https://appleid.apple.com/auth/authorize?"
            f"response_type=code%20id_token&"
            f"client_id={APPLE_MUSIC_CLIENT_ID}&"
            f"redirect_uri={APPLE_MUSIC_REDIRECT_URI}&"
            f"scope=name%20email&"
            f"response_mode=form_post&"
            f"state={session.get('state', 'default_value')}"
        )

        print(f"Exiting authorize_applemusic, redirecting to authorization_url: {authorization_url}")
        return redirect(authorization_url)

    @app.route("/authorize/applemusic", methods=["POST"])
    def authenticate_applemusic():
        print("Entering authenticate_applemusic")
        code = request.form.get("code")
        id_token = request.form.get("id_token")
        state = request.form.get("state")

        print(f"In authenticate_applemusic, code: {code}, id_token: {id_token}: state: {state}")
        
        if code and id_token:
            client_secret = session["applemusic_client_secret"]

            token_request_data = {
                "client_id": APPLE_MUSIC_TEAM_ID,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": APPLE_MUSIC_REDIRECT_URI,
            }

            token_response = requests.post(
                "https://appleid.apple.com/auth/token", data=token_request_data
            )
            token_data = token_response.json()

            if "access_token" in token_data:
                session["applemusic_token"] = token_data["access_token"]
                session["applemusic_authenticated"] = True

                print("Apple Music authentication successful")
                return redirect(url_for("home"))
            else:
                print("Apple Music authentication failed")
                return redirect(url_for("home"))
        else:
            print("Apple Music authentication failed")
            return redirect(url_for("home"))
        print("Exiting authenticate_applemusic")


def generate_client_secret():
    print("Entering generate_client_secret")
    with open(APPLE_MUSIC_CREDENTIALS_PATH, "r") as f:
        private_key_file_content = f.read()
        private_key = serialization.load_pem_private_key(
            private_key_file_content.encode(), password=None, backend=default_backend()
        )

    current_time = int(time())
    payload = {
        "iss": APPLE_MUSIC_TEAM_ID,
        "aud": "https://appleid.apple.com",
        "exp": current_time + 3600,
        "iat": current_time,
        "sub": APPLE_MUSIC_TEAM_ID,
        "nonce": os.urandom(8).hex(),
    }
    headers = {"kid": APPLE_MUSIC_KEY_ID}

    print(f"payload: {payload}, headers: {headers}")

    client_secret = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers=headers,
    )

    print(f"Returning JWT encoded client_secret: {client_secret}")

    print("Exiting generate_client_secret")
    return client_secret


def get_applemusic_library_artists(token):
    print("Entering get_applemusic_library_artists")
    headers = {
        "Authorization": f"Bearer {token}",
        "Music-User-Token": token,
    }

    url = "https://api.music.apple.com/v1/me/library/artists"
    response = requests.get(url, headers=headers)
    data = response.json()

    if "data" in data:
        artists = [item["attributes"]["name"] for item in data["data"]]
        print("Exiting get_applemusic_library_artists")
        return artists
    else:
        print("Failed to fetch Apple Music library artists")
        return []


def get_applemusic_library_songs(token):
    print("Entering get_applemusic_library_songs")
    headers = {
        "Authorization": f"Bearer {token}",
        "Music-User-Token": token,
    }

    url = "https://api.music.apple.com/v1/me/library/songs"
    response = requests.get(url, headers=headers)
    data = response.json()

    if "data" in data:
        songs = [
            {
                "title": item["attributes"]["name"],
                "artist": item["attributes"]["artistName"],
                "album": item["attributes"]["albumName"],
            }
            for item in data["data"]
        ]
        print("Exiting get_applemusic_library_songs")
        return songs
    else:
        print("Failed to fetch Apple Music library songs")
        return []


def generate_jwt_token():
    print("Entering generate_jwt_token")
    with open(APPLE_MUSIC_CREDENTIALS_PATH, "r") as f:
        private_key = f.read()

    headers = {"alg": "ES256", "kid": APPLE_MUSIC_KEY_ID}

    payload = {
        "iss": APPLE_MUSIC_TEAM_ID,
        "iat": int(time.time()),
        "exp": int(time.time()) + 86400 * 180,  # 180 days in seconds
    }

    token = jwt.encode(payload, private_key, algorithm="ES256", headers=headers)
    print("Exiting generate_jwt_token")
    return token


def get_developer_token():
    print("Entering get_developer_token")
    jwt_token = generate_jwt_token()
    headers = {
        "Authorization": f"Bearer {jwt_token}",
        "Content-Type": "application/json",
        "Music-User-Token": session.get("applemusic_user_token", ""),
    }
    print("Exiting get_developer_token")
    return headers
