import smtplib
import sys
import traceback
from email.mime.text import MIMEText
from email.utils import formatdate, make_msgid
from pprint import pformat

from flask import current_app, g, has_request_context, request


def send_mail(subject, body, config=None):
    try:
        send_mail_main(subject, body, config=config)
    except smtplib.SMTPDataError:
        pass  # ignore email errors


def send_mail_main(subject, body, config=None):
    return
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

    s = smtplib.SMTP(config["SMTP_HOST"])
    s.sendmail(mail_from, [mail_to], msg.as_string())
    s.quit()


def get_username():
    if hasattr(g, "user"):
        if g.user.is_authenticated:
            user = g.user.username
        else:
            user = "not authenticated"
    else:
        user = "no user"

    return user


def error_mail(subject, data, r, via_web=True):
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


def open_changeset_error(session_id, changeset, r):
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


def datavalue_missing(field, entity):
    qid = entity["title"]
    body = f"https://www.wikidata.org/wiki/{qid}\n\n{pformat(entity)}"

    subject = f"{qid}: datavalue missing in {field}"
    send_mail(subject, body)
