"""Send email to admins to about errors or other notworthy things."""

import pprint
import smtplib
import sys
import traceback
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid

import flask
import requests
from flask import current_app, g, has_request_context, request

from . import wikidata_api


def send_mail(
    subject: str, body: str, config: flask.config.Config | None = None
) -> None:
    """Send an email to admins, catch and ignore exceptions."""
    try:
        send_mail_main(subject, body, config=config)
    except smtplib.SMTPDataError:
        pass  # ignore email errors


def send_mail_main(
    subject: str, body: str, config: flask.config.Config | None = None
) -> None:
    """Send an email to admins."""
    if config is None:
        config = current_app.config

    mail_to = config["ADMIN_EMAIL"]
    mail_from = config["MAIL_FROM"]
    msg = MIMEText(body, "plain", "UTF-8")

    msg["Subject"] = subject
    msg["To"] = mail_to
    msg["From"] = mail_from
    msg["Date"] = formatdate()
    msg["Message-ID"] = make_msgid()
    extra_mail_headers: list[tuple[str, str]] = config.get("MAIL_HEADERS", [])
    for key, value in extra_mail_headers:
        assert key not in msg
        msg[key] = value

    s = smtplib.SMTP(config["SMTP_HOST"])
    s.sendmail(mail_from, [mail_to], msg.as_string())
    s.quit()


def get_username() -> str:
    """Get the username for the current user."""
    user: str
    if hasattr(g, "user"):
        if g.user.is_authenticated:
            user = g.user.username
        else:
            user = "not authenticated"
    else:
        user = "no user"

    return user


def error_mail(
    subject: str, data: str, r: requests.Response, via_web: bool = True
) -> None:
    """Error mail."""
    body = f"""
remote URL: {r.url}
status code: {r.status_code}

request data:
{data}

status code: {r.status_code}
content-type: {r.headers["content-type"]}

reply:
{r.text}
"""

    if has_request_context():
        body = f"site URL: {request.url}\nuser: {get_username()}\n" + body

    send_mail(subject, body)


def open_changeset_error(session_id: int, changeset: str, r: requests.Response) -> None:
    """Send error mail when failing to open a changeset."""
    username = g.user.username
    body = f"""
user: {username}
page: {r.url}

message user: https://www.openstreetmap.org/message/new/{username}

sent:

{changeset}

reply:

{r.text}

"""

    send_mail("error creating changeset", body)


def send_traceback(info, prefix="osm-wikidata"):
    exception_name = sys.exc_info()[0].__name__
    subject = f"{prefix} error: {exception_name}"
    body = f"user: {get_username()}\n" + info + "\n" + traceback.format_exc()
    send_mail(subject, body)


def datavalue_missing(field: str, entity: wikidata_api.EntityType) -> None:
    """Send an email for a missing datavalue."""
    qid = entity["title"]
    body = f"https://www.wikidata.org/wiki/{qid}\n\n{pprint.pformat(entity)}"

    subject = f"{qid}: datavalue missing in {field}"
    send_mail(subject, body)
