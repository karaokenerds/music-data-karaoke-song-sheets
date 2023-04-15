import os

from flask import (
    redirect,
    request,
    session,
    url_for,
    current_app as app
)

from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build


##########################################################################
################           Google Auth Flow                 ##############
##########################################################################


def get_google_flow():
    credentials_path = os.getenv("GOOGLE_CREDENTIALS_PATH")
    redirect_uri = os.environ.get("GOOGLE_REDIRECT_URI")

    scopes = [
        "https://www.googleapis.com/auth/drive.file",
    ]

    flow = Flow.from_client_secrets_file(
        credentials_path, scopes=scopes, redirect_uri=redirect_uri
    )
    return flow


with app.app_context():
    @app.route("/authorize_google", methods=["GET"])
    def authorize_google():
        flow = get_google_flow()
        authorization_url, state = flow.authorization_url(prompt="consent")

        session["google_auth_state"] = state

        return redirect(authorization_url)

    @app.route("/authenticate/google", methods=["GET"])
    def authenticate_google():
        flow = get_google_flow()
        code = request.args.get("code")

        if code:
            # Save the credentials in the session for later use
            session["google_token"] = flow.fetch_token(code=code)
            session["google_authenticated"] = True

            print("Google authentication successful")
            return redirect(url_for("home"))
        else:
            print("Google authentication failed")
            return redirect(url_for("home"))


##########################################################################
###########          Google Sheet Find & Create                ###########
##########################################################################

def find_google_sheet_id(sheet_title, creds):
    print(f"Finding google sheet with title: {sheet_title}")
    service = build("drive", "v3", credentials=creds)
    escaped_sheet_title = sheet_title.replace("'", "\\'")  # Escape single quotes
    query = "mimeType='application/vnd.google-apps.spreadsheet' and trashed=false and name='{0}'".format(
        escaped_sheet_title
    )
    results = (
        service.files().list(q=query, fields="nextPageToken, files(id, name)").execute()
    )
    items = results.get("files", [])

    if items:
        return items[0]["id"]
    else:
        return None


def create_google_sheet(title, creds):
    print(f"Creating google sheet with title: {title}")
    service = build("sheets", "v4", credentials=creds)
    spreadsheet = {"properties": {"title": title}}
    spreadsheet = (
        service.spreadsheets()
        .create(body=spreadsheet, fields="spreadsheetId")
        .execute()
    )
    return spreadsheet.get("spreadsheetId")


##########################################################################
###########                Write Rows to Sheet                 ###########
##########################################################################

def write_rows_to_google_sheet(spreadsheet_id, google_creds, header_values, data_values):
    print(f"Writing karaoke songs to google sheet with ID: {spreadsheet_id}")
    service = build("sheets", "v4", credentials=google_creds)

    header_body = {"values": [header_values]}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range="A1:N1",
        valueInputOption="RAW",
        body=header_body,
    ).execute()

    data_body = {"values": data_values}
    service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id,
        range=f"A2:N{len(data_values) + 1}",
        valueInputOption="RAW",
        body=data_body,
    ).execute()
