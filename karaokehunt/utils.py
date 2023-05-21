import re
import os
import sys
import json
import logging

from flask import (
    Response,
    redirect,
    request,
    session,
    url_for,
    send_from_directory,
    current_app as app,
    g,
)

logger = logging.getLogger("karaokehunt")

##########################################################################
###########           Utility Methods & Routes                ############
##########################################################################


TEMP_OUTPUT_DIR = os.getenv("TEMP_OUTPUT_DIR")
ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")
LOG_FILE_PATH = os.getenv("LOG_FILE_PATH")
DEFAULT_loglimit = os.getenv("DEFAULT_loglimit", 50)

with app.app_context():

    def tail(f, lines=1, _buffer=4098):
        """Tail a file and get X lines from the end"""
        # place holder for the lines found
        lines_found = []

        # block counter will be multiplied by buffer
        # to get the block size from the end
        block_counter = -1

        # loop until we find X lines
        while len(lines_found) < lines:
            try:
                f.seek(block_counter * _buffer, os.SEEK_END)
            except IOError:  # either file is too small, or too many lines requested
                f.seek(0)
                lines_found = f.readlines()
                break

            lines_found = f.readlines()

            # decrement the block counter to get the
            # next X bytes
            block_counter -= 1

        return lines_found[-lines:]

    def get_all_logs(loglimit):
        with open(LOG_FILE_PATH) as f:
            tailed_logs = tail(f, loglimit)
            tailed_logs.reverse()
            return "".join(tailed_logs)

    def get_logs_for_username(username, loglimit):
        userlines = []
        with open(LOG_FILE_PATH) as f:
            for line in f.readlines():
                if re.search(f" / User: {username}", line):
                    userlines.append(line)

        if len(userlines) == 0:
            userlines = [f"No logs found for username: {username}"]

        if len(userlines) > loglimit:
            userlines = userlines[-loglimit:]

        userlines.reverse()
        return "".join(userlines)

    @app.route("/admin", methods=["GET"])
    def admin():
        logger.info("Admin page requested")
        admin_html = "unauthorized"

        if (
            ADMIN_PASSWORD is not None
            and request.args.get("password") == ADMIN_PASSWORD
        ):
            admin_html = f"<h1>KaraokeHunt Tools Admin Helper</h1>"
            admin_html += "<p>Please use this page with extreme caution, it shows all user logs, potentially including secrets</p>"

            loglimit = int(request.args["loglimit"]) if "loglimit" in request.args else DEFAULT_loglimit

            admin_html += f"<h2>Logs for all users since last app restart, last {loglimit} lines (newest at top):</h2>"
            admin_html += (
                '<pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
            )
            admin_html += get_all_logs(loglimit) + "</pre>"

            admin_html += debug()

        return admin_html

    @app.route("/debug", methods=["GET"])
    def debug():
        logger.info("Debug page requested")
        debug_html = "<h1>KaraokeHunt Tools Debug Helper</h1>"
        debug_html += "<p>Please use this page with caution, it shows your own personal access credentials in plain text (only to you, but don't copy/paste these anywhere unless you know what you're doing!)</p>"

        if "username" in session:
            loglimit = int(request.args["loglimit"]) if "loglimit" in request.args else DEFAULT_loglimit
            debug_html += f'<h2>Logs for username "{session["username"]}", last {loglimit} lines (newest at top):</h2>'
            debug_html += (
                '<pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
            )
            debug_html += (
                get_logs_for_username(session["username"], loglimit) + "</pre>"
            )

        debug_html += '<h2>Session data:</h2><pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
        debug_html += json.dumps(session, indent=4) + "</pre>"

        debug_html += '<h2>Flask globals:</h2><pre style="white-space: pre-wrap; overflow-wrap: break-word;">'
        debug_html += json.dumps(g.__dict__, indent=4) + "</pre>"

        return debug_html

    @app.route("/logs", methods=["GET"])
    def get_logs():
        user_logs = "no user session"

        if "username" in session:
            loglimit = int(request.args["loglimit"]) if "loglimit" in request.args else DEFAULT_loglimit
            user_logs = get_logs_for_username(session["username"], loglimit)

        return Response(user_logs, mimetype="text/plain")

    @app.route("/favicon.ico")
    def send_favicon():
        return send_from_directory("assets", "favicon.ico")

    @app.route("/assets/<path:path>")
    def send_asset(path):
        return send_from_directory("assets", path)

    @app.route("/reset")
    def reset_session():
        session.clear()
        return redirect(url_for("home"))
