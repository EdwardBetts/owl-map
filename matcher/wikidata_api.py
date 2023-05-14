import json
import typing
from typing import Any, cast

import requests
import simplejson.errors

from . import CallParams, user_agent_headers

wd_api_url = "https://www.wikidata.org/w/api.php"

EntityType = dict[str, Any]


def api_get(params: CallParams) -> requests.Response:
    """Call the wikidata API."""
    call_params: CallParams = {
        "format": "json",
        "formatversion": 2,
        **params,
    }

    r = requests.get(wd_api_url, params=call_params, headers=user_agent_headers())
    return r


def get_revision_timestamp(revid: int) -> str:
    """Get timetsmap for the given revid."""
    params: CallParams = {
        "action": "query",
        "prop": "revisions",
        "revids": revid,
        "rvprop": "ids|timestamp",
    }
    r = api_get(params)
    rev = r.json()["query"]["pages"][0]["revisions"][0]
    assert rev["revid"] == int(revid)
    return cast(str, rev["timestamp"])


def get_recent_changes(
    rcstart: str | None = None, rccontinue: str | None = None
) -> requests.Response:
    """Get list of recent changes."""
    props = [
        "title",
        "ids",
        "comment",
        "parsedcomment",
        "timestamp",
        "redirect",
        "loginfo",
    ]

    params: CallParams = {
        "action": "query",
        "list": "recentchanges",
        "rcnamespace": 0,
        "rclimit": "max",
        "rcdir": "newer",
        "rcprop": "|".join(props),
    }
    if rcstart is not None:
        params["rcstart"] = rcstart
    if rccontinue is not None:
        params["rccontinue"] = rccontinue

    return api_get(params)


def get_entity(qid: str) -> EntityType:
    """Retrieve a Wikidata item with the given QID using the API."""
    r = api_get({"action": "wbgetentities", "ids": qid})
    try:
        data = r.json()
    except simplejson.errors.JSONDecodeError:
        print(r.text)
        raise
    if "entities" not in data:
        print(json.dumps(data, indent=2))
    return cast(EntityType, data["entities"][qid])


def get_entities(ids: list[str]) -> typing.Iterator[tuple[str, EntityType]]:
    """Get Wikidata item entities with the given QIDs."""
    r = api_get({"action": "wbgetentities", "ids": "|".join(ids)})
    return ((qid, entity) for qid, entity in r.json()["entities"].items())
