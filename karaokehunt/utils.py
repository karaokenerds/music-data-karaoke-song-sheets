import io
import os
import sys
import json

from flask import (
    Response,
    redirect,
    session,
    url_for,
    send_from_directory,
    current_app as app
)

##########################################################################
###########           Utility Methods & Routes                ############
##########################################################################


TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
LOG_FILE_NAME = os.getenv("LOG_FILE_NAME")


class LogCapture(io.StringIO):
    def __init__(self):
        super().__init__()
        self.logfile = open(f'{TEMP_OUTPUT_DIR}/{LOG_FILE_NAME}', "a")

    def write(self, s):
        super().write(s)
        self.logfile.write(s)
        sys.__stdout__.write(s)
        sys.__stdout__.flush()


log_capture = LogCapture()
sys.stdout = log_capture


with app.app_context():
    @app.route("/debug", methods=["GET"])
    def debug():
        debug_html = '<h1>DEBUG: Session data</h1><pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
        debug_html += json.dumps(session, indent=4) + '</pre>'
        return debug_html

    @app.route("/logs", methods=["GET"])
    def get_log_output():
        log_output = log_capture.getvalue()
        return Response(log_output, mimetype="text/plain")

    @app.route('/favicon.ico')
    def send_favicon():
        return send_from_directory('assets', 'favicon.ico')

    @app.route('/assets/<path:path>')
    def send_asset(path):
        return send_from_directory('assets', path)

    @app.route("/reset")
    def reset_session():
        session.clear()
        return redirect(url_for("home"))
