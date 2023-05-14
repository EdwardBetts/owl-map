#!/usr/bin/python3

"""Download Wikidata recent changes and update items in local database."""

import json
import os
import sys
from time import sleep

from matcher import database, model, utils, wikidata, wikidata_api

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)

previous_max_lastrevid = 1388804050  # Q106152661

entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}


def read_changes():
    qids = set()
    max_lastrevid = 0
    for f in sorted(os.listdir("changes"), key=lambda f: int(f.partition(".")[0])):
        reply = json.load(open("changes/" + f))
        print(f, len(qids))
        for change in reply["query"]["recentchanges"]:
            # rctype = change["type"]
            title = change["title"]
            revid = change["revid"]
            if revid and revid > max_lastrevid:
                max_lastrevid = revid
            assert title.startswith("Q")
            qids.add(title)
    print(len(qids))
    print(max_lastrevid)

    return

    for cur in utils.chunk(qids, 50):
        print(cur)
        for qid, entity in wikidata_api.get_entities(cur):
            with open(f"items/{qid}.json", "w") as out:
                json.dump(entity, out)


def get_changes():
    start = "2021-03-24T11:56:11"
    rccontinue = None
    i = 0
    while True:
        i += 1
        r = wikidata_api.query_wd_api(rcstart=start, rccontinue=rccontinue)
        with open(f"changes/{i:06d}.json", "w") as out:
            out.write(r.text)

        reply = r.json()
        try:
            print(reply["query"]["recentchanges"][0]["timestamp"])
        except KeyError:
            print("KeyError")

        if False:
            for change in reply["query"]["recentchanges"]:
                # rctype = change["type"]
                # if change["revid"] == 0 and change["old_revid"] == 0:
                #     continue

                if change["logtype"] == "delete" and change["logaction"] in {
                    "revision",
                    "delete",
                    "restore",
                }:
                    continue

                if change["logtype"] == "protect" and change["logaction"] in {
                    "unprotect",
                    "protect",
                }:
                    continue

                print(json.dumps(change, indent=2))
                sys.exit(0)

                continue

                if not change["title"].startswith("Q"):
                    continue  # not an item

                qid = change["title"]
                assert qid[1:].isdigit()
                item_id = int(qid[1:])
                revid = change["revid"]

                item = model.Item.query.get(item_id)
                if change["type"] == "edit" and not item:
                    continue

                if change["type"] == "new" and not item:
                    print(("new", qid))
                    continue

                if not item:
                    print(qid)
                    print(json.dumps(change, indent=2))
                print((change["type"], qid, item.lastrevid, revid))

            # print(json.dumps(reply, indent=2))

        if "continue" not in reply:
            break

        rccontinue = reply["continue"]["rccontinue"]
        print(rccontinue)
        sleep(1)


def get_timestamp():
    ts = wikidata_api.get_revision_timestamp(previous_max_lastrevid)
    print(ts)


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


def coords_equal(a, b):
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


def update_timestamp(timestamp):
    out = open("rc_timestamp", "w")
    print(timestamp, file=out)
    out.close()


def update_database():
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


# read_changes()
# get_timestamp()
# get_changes()

while True:
    update_database()
    sleep(60)
