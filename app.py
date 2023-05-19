import os
import uuid
from dotenv import load_dotenv
import logging
import logging.config

##########################################################################
###################            Init and Setup               ##############
##########################################################################

load_dotenv()

TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
LOG_FILE_NAME = os.getenv("LOG_FILE_NAME")

class UsernameRequestIdFilter(logging.Filter):
    # This is a logging filter that makes both request ID and username
    # available for use in the logging formatter, if set (otherwise UNKNOWN)
    def filter(self, record):
        req_id = "UNKNOWN"
        username = "UNKNOWN"

        if flask.has_app_context():
            if not hasattr(flask.g, "request_id"):
                new_uuid = uuid.uuid4().hex[:10]
                flask.g.request_id = new_uuid
            req_id = flask.g.request_id
            username = getattr(flask.g, "username", "UNKNOWN")

        record.req_id = req_id
        record.username = username
        return True


LOGGING_CONFIG = {
    "version": 1,
    "disable_existing_loggers": True,
    "filters": {
        "add_request_and_username": {
            "()": '__main__.UsernameRequestIdFilter',
        },
    },
    "formatters": {
        "standard": {"format": "%(asctime)s [%(levelname)s] %(name)s: %(message)s"},
    },
    "handlers": {
        "default": {
            "level": "DEBUG",
            "formatter": "standard",
            "class": "logging.StreamHandler",
            "stream": "ext://sys.stdout",  # Default is stderr
        }
    },
    "loggers": {
        "": {  # root logger
            "handlers": ["default"],
            "level": "DEBUG",
            "propagate": False,
        },
        "karaokehunt": {
            "handlers": ["default"],
            "level": "DEBUG",
            "propagate": False
        },
        "__main__": {  # if __name__ == '__main__'
            "handlers": ["default"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

logging.config.dictConfig(LOGGING_CONFIG)


# The StreamHandler responsible for writing logs to the console and log file
# logger_stream_handler = logging.StreamHandler()
# logger_stream_handler.addFilter(UsernameRequestIdFilter())

# log_formatter = logging.Formatter(
#     fmt="[%(asctime)s.%(msecs)03d] %(levelname)s in %(module)s/%(funcName)s Req: %(req_id)s User: %(username)s: %(message)s",
#     datefmt="%Y-%m-%d %H:%M:%S",
# )

# logger_stream_handler.setFormatter(log_formatter)

# logger = logging.getLogger()
# logger.setLevel(logging.DEBUG)
# logger.addHandler(logger_stream_handler)

# kh_logger = logging.getLogger("karaokehunt")
# kh_logger.setLevel(logging.DEBUG)
# kh_logger.addHandler(logger_stream_handler)

# werkzeug_logger = logging.getLogger("werkzeug")
# default_handler.setFormatter(log_formatter)
# werkzeug_logger.addHandler(logger_stream_handler)

import flask
from flask import Flask

app = Flask(__name__)
app.config.from_prefixed_env()
app.app_context().push()


# autopep8: off
from karaokehunt.karaokehunt import *
from karaokehunt.applemusic import generate_developer_token

# autopep8: on


@app.before_request
def load_username():
    if "username" in session:
        flask.g.username = session.get("username")
    else:
        username = generate_slug(2)
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
