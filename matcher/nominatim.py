from collections import OrderedDict

import json
import requests


class SearchError(Exception):
    pass


def lookup_with_params(**kwargs):
    url = "http://nominatim.openstreetmap.org/search"

    params = {
        "format": "jsonv2",
        "addressdetails": 1,
        "extratags": 1,
        "limit": 30,
        "namedetails": 1,
        "accept-language": "en",
        "polygon_text": 0,
    }
    params.update(kwargs)
    r = requests.get(url, params=params)
    if r.status_code == 500:
        raise SearchError

    try:
        return json.loads(r.text, object_pairs_hook=OrderedDict)
    except json.decoder.JSONDecodeError:
        raise SearchError(r)


def lookup(q):
    return lookup_with_params(q=q)


def get_us_county(county, state):
    if " " not in county and "county" not in county:
        county += " county"
    results = lookup(q="{}, {}".format(county, state))

    def pred(hit):
        return (
            "osm_type" in hit
            and hit["osm_type"] != "node"
            and county in hit["display_name"].lower()
        )

    return next(filter(pred, results), None)


def get_us_city(name, state):
    results = lookup_with_params(city=name, state=state)
    if len(results) != 1:
        results = [
            hit for hit in results if hit["type"] == "city" or hit["osm_type"] == "node"
        ]
        if len(results) != 1:
            print("more than one")
            return
    hit = results[0]
    if hit["type"] not in ("administrative", "city"):
        print("not a city")
        return
    if hit["osm_type"] == "node":
        print("node")
        return
    if not hit["display_name"].startswith(name):
        print("wrong name")
        return
    assert "osm_type" in hit and "osm_id" in hit and "geotext" in hit
    return hit


def get_hit_name(hit):
    address = hit.get("address")
    if not address:
        return hit["display_name"]

    address_values = list(address.values())
    n1 = address_values[0]
    if len(address) == 1:
        return n1

    country = address.pop("country", None)
    country_code = address.pop("country_code", None)
    if country_code:
        country_code == country_code.lower()

    if country_code == "us" and "state" in address:
        state = address["state"]
        return f"{n1}, {state}, USA"

    if country_code == "gb":
        country = "UK"

    if len(address) == 1:
        return f"{n1}, {country}"
    else:
        n2 = address_values[1]
        return f"{n1}, {n2}, {country}"


def get_hit_label(hit):
    tags = hit["extratags"]
    designation = tags.get("designation")
    category = hit["category"]
    hit_type = hit["type"]

    if designation:
        return designation.replace("_", " ")

    if category == "boundary" and hit_type == "administrative":
        place = tags.get("place") or tags.get("linked_place")

        if place:
            return f"{place} {category}"

    if category == "place":
        return f"{hit_type}"

    return f"{hit_type} {category}"
