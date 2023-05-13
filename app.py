import os

from dotenv import load_dotenv
from flask import (
    Flask,
    render_template,
    session,
)

##########################################################################
###################            Init and Setup               ##############
##########################################################################

load_dotenv()

app = Flask(__name__)
app.config.from_prefixed_env()
app.app_context().push()

# autopep8: off
from karaokehunt.karaokehunt import *
from karaokehunt.applemusic import generate_developer_token
# autopep8: on

##########################################################################
###########          Render HTML template with strings         ###########
##########################################################################


@app.route("/", methods=["GET"])
def home():
    applemusic_developer_token = session.get("applemusic_developer_token")
    if not applemusic_developer_token:
        applemusic_developer_token = generate_developer_token()
        session["applemusic_developer_token"] = applemusic_developer_token
    
    spotify_authenticated = "spotify_authenticated" if session.get("spotify_authenticated") else ""
    lastfm_authenticated = "lastfm_authenticated" if session.get("lastfm_authenticated") else ""
    youtube_authenticated = "youtube_authenticated" if session.get("youtube_authenticated") else ""
    applemusic_authenticated = "applemusic_authenticated" if session.get("applemusic_authenticated") else ""
    google_authenticated = "google_authenticated" if session.get("google_authenticated") else ""
    lastfm_username = session.get("lastfm_username") if session.get("lastfm_username") else ""

    return render_template(
        "home.html",
        applemusic_developer_token=applemusic_developer_token,
        spotify_authenticated=spotify_authenticated,
        lastfm_authenticated=lastfm_authenticated,
        youtube_authenticated=youtube_authenticated,
        applemusic_authenticated=applemusic_authenticated,
        google_authenticated=google_authenticated,
        lastfm_username=lastfm_username
    )


if __name__ == "__main__":
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)
