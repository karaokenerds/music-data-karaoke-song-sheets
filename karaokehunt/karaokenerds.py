import gzip
import json
import os
from pathlib import Path
import urllib.request
from datetime import timedelta, datetime

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
KARAOKE_SONGS_FILE = os.getenv("KARAOKE_SONGS_FILE")
KARAOKE_SONGS_URL = os.getenv("KARAOKE_SONGS_URL")

##########################################################################
###########            Load Karaoke Nerds Data                 ###########
##########################################################################


def is_file_older_than(file, delta):
    cutoff = datetime.utcnow() - delta
    mtime = datetime.utcfromtimestamp(os.path.getmtime(file))
    if mtime < cutoff:
        return True
    return False


def load_karaoke_songs():
    file_path = Path(f'{TEMP_OUTPUT_DIR}/{KARAOKE_SONGS_FILE}')
    needs_fetch = False

    if not file_path.is_file():
        print(f"Karaoke song DB file not found, download required")
        needs_fetch = True
    else:
        if is_file_older_than(file_path, timedelta(days=3)):
            print(f"Karaoke song DB is older than 3 days, download required")
            needs_fetch = True

    if needs_fetch:
        print(f"Downloading latest karaoke song DB from firebase storage")
        urllib.request.urlretrieve(KARAOKE_SONGS_URL, file_path)

    with gzip.open(file_path, "rt", encoding="utf-8") as f:
        print(f"Successfully opened karaoke song DB")
        data = json.load(f)
        return data
