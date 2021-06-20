import requests
import json
import simplejson.errors

wd_api_url = "https://www.wikidata.org/w/api.php"


def api_get(params):
    base_params = {
        "format": "json",
        "formatversion": 2,
    }

    return requests.get(wd_api_url, params={**base_params, **params})


def get_revision_timestamp(revid):
    params = {
        "action": "query",
        "prop": "revisions",
        "revids": revid,
        "rvprop": "ids|timestamp",
    }
    r = api_get(params)
    rev = r.json()["query"]["pages"][0]["revisions"][0]
    assert rev["revid"] == int(revid)
    return rev["timestamp"]


def get_recent_changes(**kwargs):
    props = [
        "title",
        "ids",
        "comment",
        "parsedcomment",
        "timestamp",
        "redirect",
        "loginfo",
    ]

    params = {
        "action": "query",
        "list": "recentchanges",
        "rcnamespace": 0,
        # "rctype": "log",
        # "rclimit": "max",
        "rclimit": "max",
        # "rcstart": start,
        "rcdir": "newer",
        "rcprop": "|".join(props),
        **{k: v for k, v in kwargs.items() if v},
    }

    return api_get(params)


def get_entity(qid):
    r = api_get({"action": "wbgetentities", "ids": qid})
    try:
        data = r.json()
    except simplejson.errors.JSONDecodeError:
        print(r.text)
        raise
    if "entities" not in data:
        print(json.dumps(data, indent=2))
    return data["entities"][qid]


def get_entities(ids):
    r = api_get({"action": "wbgetentities", "ids": "|".join(ids)})
    for qid, entity in r.json()["entities"].items():
        yield qid, entity
