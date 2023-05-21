import os
import uuid
from dotenv import load_dotenv
import logging
import logging.config
import re

##########################################################################
###################            Init and Setup               ##############
##########################################################################

load_dotenv()

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")


class UsernameRequestIdFilter(logging.Filter):
    # This is a logging filter that makes both request ID and username
    # available for use in the logging formatter, if set (otherwise UNKNOWN)
    def filter(self, record):
        req_id = "UNKNOWN"
        username = "UNKNOWN"
        record.identifier = f"HTTP"

        if flask.has_request_context():
            record.identifier += " / ReqID: "

            if not hasattr(flask.g, "request_id"):
                new_uuid = uuid.uuid4().hex[:10]
                flask.g.request_id = new_uuid

            record.identifier += flask.g.request_id

        if flask.has_app_context() and flask.has_request_context():
            record.identifier += " / User: "

            if "username" in session:
                record.identifier += session["username"]
            else:
                record.identifier += "NoUserInSession"

        record.replacedmessage = re.sub("\[.+\] ", "", record.getMessage())
        record.replacedmessage = re.sub("127.0.0.1 ", "", record.replacedmessage)
        record.replacedmessage = re.sub("- - ", "", record.replacedmessage)
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {
        "add_request_and_username": {
            "()": "__main__.UsernameRequestIdFilter",
        },
    },
    "formatters": {
        "standard": {
            "format": "%(asctime)s [%(levelname)s] [%(identifier)s] %(name)s: %(replacedmessage)s"
        },
    },
    "handlers": {
        "default": {
            "stream": "ext://sys.stdout",  # Default is stderr
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "filters": ["add_request_and_username"],
        },
        "timed_rotate_file": {
            "filename": LOG_FILE_PATH,
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.handlers.TimedRotatingFileHandler",
            "encoding": "utf8",
            # Used to configure when backups happen 'seconds, minutes, w0,w1 (monday tuesday)
            "when": "midnight",  # Daily backup
            # This is used to configure rollover (7=weekly files if when = daily or midnight)
            "backupCount": 7,
        },
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["default", "timed_rotate_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "karaokehunt": {
            "handlers": ["default", "timed_rotate_file"],
            "level": "DEBUG",
            "propagate": False,
        },
        "__main__": {  # if __name__ == '__main__'
            "handlers": ["default", "timed_rotate_file"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)

import flask
from flask import Flask

app = Flask(__name__)
app.config.from_prefixed_env()
app.app_context().push()

from karaokehunt.karaokehunt import *


@app.before_request
def load_username():
    if "username" in session:
        flask.g.username = session.get("username")
    else:
        username = generate_slug(2)
        logger.debug(
            f"Before request, found no username in session. Generated one: {username}"
        )
        session["username"] = username
        flask.g.username = username


@app.after_request
def inject_identifying_headers(response):
    response.headers["X-Username"] = session.get("username", "UNKNOWN")
    return response


if __name__ == "__main__":
    logger.info("App starting up")
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=True, host="0.0.0.0", port=port)
    logger.info("App successfully started")
