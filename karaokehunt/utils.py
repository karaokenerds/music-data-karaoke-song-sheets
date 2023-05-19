import io
import os
import sys
import json
import logging

from flask import (
    Response,
    redirect,
    session,
    url_for,
    send_from_directory,
    current_app as app,
    g
)

logger = logging.getLogger("karaokehunt")

##########################################################################
###########           Utility Methods & Routes                ############
##########################################################################


TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")

with app.app_context():

    @app.route("/debug", methods=["GET"])
    def debug():
        debug_html = '<h1>DEBUG: Session data</h1><pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
        debug_html += json.dumps(session, indent=4) + "</pre>"
        debug_html = '<h1>DEBUG: Flask globals</h1><pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
        debug_html += json.dumps(g, indent=4) + "</pre>"
        return debug_html

    # @app.route("/logs", methods=["GET"])
    # def get_log_output():
    #     log_output = log_capture.getvalue()
    #     return Response(log_output, mimetype="text/plain")

    @app.route("/favicon.ico")
    def send_favicon():
        return send_from_directory("assets", "favicon.ico")

    @app.route("/assets/<path:path>")
    def send_asset(path):
        logger.debug(f"Serving asset file: {path}")
        return send_from_directory("assets", path)

    @app.route("/reset")
    def reset_session():
        session.clear()
        return redirect(url_for("home"))
