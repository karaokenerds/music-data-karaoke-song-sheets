import os
import jwt
import requests
import logging
from time import time
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.backends import default_backend
from flask import redirect, request, session, url_for, current_app as app, g

logger = logging.getLogger("karaokehunt")

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

    @app.route("/authorize/applemusic_token", methods=["POST"])
    def authorize_applemusic_token():
        logger.info("Entering authorize_applemusic_token")
        data = request.json
        music_user_token = data.get("music_user_token")

        logger.info(
            f"Setting applemusic_music_user_token in session to music_user_token: {music_user_token}"
        )

        session["applemusic_music_user_token"] = music_user_token

        authorization_url = (
            f"https://appleid.apple.com/auth/authorize?"
            f"response_type=code%20id_token&"
            f"client_id={APPLE_MUSIC_CLIENT_ID}&"
            f"redirect_uri={APPLE_MUSIC_REDIRECT_URI}&"
            f"scope=name%20email&"
            f"response_mode=form_post&"
            f"state={session.get('state', 'default_value')}"
        )

        logger.info(
            f"Exiting authenticate_applemusic, responding with authorization_url: {authorization_url}"
        )
        return authorization_url

    @app.route("/authorize/applemusic", methods=["POST"])
    def authorize_applemusic():
        logger.info("Entering authorize_applemusic")
        code = request.form.get("code")
        id_token = request.form.get("id_token")

        logger.info(f"In authorize_applemusic, received post data:")
        for key, val in request.form.items():
            logger.info("key: {0} val: {1}".format(key, val))

        if code and id_token:
            client_secret = generate_client_secret()
            session["applemusic_client_secret"] = client_secret
            logger.info(f"Set client_secret to {client_secret}")

            token_request_data = {
                "client_id": APPLE_MUSIC_CLIENT_ID,
                "client_secret": client_secret,
                "code": code,
                "grant_type": "authorization_code",
                "redirect_uri": APPLE_MUSIC_REDIRECT_URI,
            }

            logger.info(
                f"About to POST to /auth/token with token_request_data: {token_request_data}"
            )
            token_response = requests.post(
                "https://appleid.apple.com/auth/token", data=token_request_data
            )
            token_data = token_response.json()

            logger.info(f"Apple auth token response: {token_data}")

            if "access_token" in token_data:
                logger.info(
                    "Found access_token in response, storing in session - Apple Music authentication successful!"
                )

                session["applemusic_user_access_token"] = token_data["access_token"]

                decoded_id_token = jwt.decode(
                    token_data["id_token"],
                    audience=APPLE_MUSIC_CLIENT_ID,
                    options={"verify_signature": False},
                )
                logger.info(f"decoded_id_token: {decoded_id_token}")

                session["applemusic_user_decoded_id_token"] = decoded_id_token
                username = decoded_id_token["email"]
                session["applemusic_username"] = username
                session["username"] = username
                g.username = username

                session["applemusic_authenticated"] = True

                return redirect(url_for("home"))
            else:
                logger.info(
                    "Error: Apple Music authentication failed; access_token not found in response. Redirecting to home"
                )
                return redirect(url_for("home"))
        else:
            logger.info(
                "Error: Apple Music authentication failed; code and id_token were not set. Redirecting to home"
            )
            return redirect(url_for("home"))


def generate_client_secret():
    logger.info("Entering generate_client_secret")
    with open(APPLE_MUSIC_CREDENTIALS_PATH, "r") as f:
        private_key_file_content = f.read()
        private_key = serialization.load_pem_private_key(
            private_key_file_content.encode(), password=None, backend=default_backend()
        )

    current_time = int(time())
    one_week = 604800
    expiry_time = current_time + one_week

    payload = {
        "iss": APPLE_MUSIC_TEAM_ID,
        "aud": "https://appleid.apple.com",
        "exp": expiry_time,
        "iat": current_time,
        "sub": APPLE_MUSIC_CLIENT_ID,
        "nonce": os.urandom(8).hex(),
    }
    headers = {"alg": "ES256", "kid": APPLE_MUSIC_KEY_ID}

    logger.info(f"payload: {payload}, headers: {headers}")

    client_secret = jwt.encode(
        payload,
        private_key,
        algorithm="ES256",
        headers=headers,
    )

    logger.info(f"Returning JWT encoded client_secret: {client_secret}")
    return client_secret


def generate_developer_token():
    logger.info("Entering generate_developer_token")

    with open(APPLE_MUSIC_CREDENTIALS_PATH, "r") as f:
        private_key = f.read()

    headers = {"alg": "ES256", "kid": APPLE_MUSIC_KEY_ID}

    current_time = int(time())
    one_week = 604800
    expiry_time = current_time + one_week

    payload = {
        "iss": APPLE_MUSIC_TEAM_ID,
        "exp": expiry_time,
        "iat": current_time,
    }

    developer_token = jwt.encode(
        payload, private_key, algorithm="ES256", headers=headers
    )
    return developer_token


def get_request_headers(developer_token, user_token):
    logger.info("Entering get_request_headers")

    if developer_token is None or user_token is None:
        logger.info("Error: missing user token")
        return

    headers = {
        "Authorization": f"Bearer {developer_token}",
        "Content-Type": "application/json",
        "Music-User-Token": user_token,
    }
    logger.info(f"Exiting get_request_headers, returning headers: {headers}")
    return headers


def get_applemusic_library_artists(developer_token, user_token):
    logger.info(
        f"Entering get_applemusic_library_artists, developer_token: {developer_token} user_token: {user_token}"
    )
    if developer_token is None or user_token is None:
        logger.info("Error: missing user token")
        return

    headers = get_request_headers(developer_token, user_token)

    url = "https://api.music.apple.com/v1/me/library/artists"
    logger.info(f"Making request to {url} with headers: {headers}")

    response = requests.get(url, headers=headers)
    logger.info(f"response: {response}")

    data = response.json()

    if "data" in data:
        artists = [item["attributes"]["name"] for item in data["data"]]
        logger.info("Exiting get_applemusic_library_artists")
        return artists
    else:
        logger.info("Failed to fetch Apple Music library artists")
        return []


def get_applemusic_library_songs(developer_token, user_token):
    logger.info(f"Entering get_applemusic_library_songs, user_token: {user_token}")
    if developer_token is None or user_token is None:
        logger.info("Error: missing user token")
        return

    headers = get_request_headers(developer_token, user_token)

    url = "https://api.music.apple.com/v1/me/library/songs"
    logger.info(f"Making request to {url} with headers: {headers}")

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
        logger.info("Exiting get_applemusic_library_songs")
        return songs
    else:
        logger.info("Failed to fetch Apple Music library songs")
        return []
