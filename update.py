#!/usr/bin/python3

"""Download Wikidata recent changes and update items in local database."""

import json
import typing
from time import sleep

from matcher import database, model, wikidata, wikidata_api

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)

entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}


def handle_new(change):
    qid = change["title"]
    ts = change["timestamp"]
    if change["redirect"]:
        print(f"{ts}: new item {qid}, since replaced with redirect")
        return
    item = model.Item.query.get(qid[1:])  # check if item is already loaded
    if item:
        return handle_edit(change)

    entity = wikidata_api.get_entity(qid)
    if entity["id"] != qid:
        print(f'redirect {qid} -> {entity["id"]}')
        return

    if "claims" not in entity:
        print(qid)
        print(entity)
    coords = wikidata.get_entity_coords(entity["claims"])
    if not coords:
        print(f"{ts}: new item {qid} without coordinates")
        return

    print(f"{ts}: new item {qid} with coordinates")

    item_id = int(qid[1:])
    obj = {k: v for k, v in entity.items() if k in entity_keys}
    try:
        item = model.Item(item_id=item_id, **obj)
    except TypeError:
        print(qid)
        print(f'{entity["pageid"]=} {entity["ns"]=} {entity["type"]=}')
        print(entity.keys())
        raise
    item.locations = model.location_objects(coords)
    database.session.add(item)


def coords_equal(a: dict[str, typing.Any], b: dict[str, typing.Any]) -> bool:
    """Deep equality comparison of nested dicts."""
    return json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def handle_edit(change):
    qid = change["title"]
    item = model.Item.query.get(qid[1:])
    if not item:
        return  # item isn't in our database so it probably has no coordinates

    ts = change["timestamp"]

    if item.lastrevid >= change["revid"]:
        print(f"{ts}: no need to update {qid}")
        return

    entity = wikidata_api.get_entity(qid)
    entity_qid = entity.pop("id")
    if entity_qid != qid:
        print(f"{ts}: item {qid} replaced with redirect")
        database.session.delete(item)
        database.session.commit()
        return

    assert entity_qid == qid
    existing_coords = wikidata.get_entity_coords(item.claims)
    if "claims" not in entity:
        return
    coords = wikidata.get_entity_coords(entity["claims"])

    if not coords_equal(existing_coords, coords):
        print(f"{ts}: update item {qid}, including coordinates")
        item.locations = model.location_objects(coords)
    else:
        print(f"{ts}: update item {qid}, no change to coordinates")

    for key in entity_keys:
        setattr(item, key, entity[key])


def update_timestamp(timestamp: str) -> None:
    """Save timestamp to rc_timestamp."""
    out = open("rc_timestamp", "w")
    print(timestamp, file=out)
    out.close()


def update_database() -> None:
    with open("rc_timestamp") as f:
        start = f.read().strip()

    rccontinue = None
    seen = set()
    while True:
        r = wikidata_api.get_recent_changes(rcstart=start, rccontinue=rccontinue)

        reply = r.json()
        for change in reply["query"]["recentchanges"]:
            rctype = change["type"]
            timestamp = change["timestamp"]
            qid = change["title"]
            if qid in seen:
                continue

            if rctype == "new":
                handle_new(change)
                seen.add(qid)
            if rctype == "edit":
                handle_edit(change)
                seen.add(qid)

        update_timestamp(timestamp)
        print("commit")
        database.session.commit()

        if "continue" not in reply:
            break

        rccontinue = reply["continue"]["rccontinue"]
    database.session.commit()
    print("finished")


def main() -> None:
    """Infinite loop."""
    while True:
        update_database()
        sleep(60)


if __name__ == "__main__":
    main()
