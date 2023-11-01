"""Nominatim."""

import json
import typing
from collections import OrderedDict

import requests

from . import CallParams

Hit = dict[str, typing.Any]


class SearchError(Exception):
    """Search error."""


def lookup_with_params(**kwargs: str) -> list[Hit]:
    url = "http://nominatim.openstreetmap.org/search"

    params: CallParams = {
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
        reply: list[Hit] = json.loads(r.text, object_pairs_hook=OrderedDict)
        return reply
    except json.decoder.JSONDecodeError:
        raise SearchError(r)


def lookup(q: str) -> list[Hit]:
    """Nominatim search."""
    return lookup_with_params(q=q)


def get_us_county(county: str, state: str) -> Hit | None:
    """Search for US county and return resulting hit."""
    if " " not in county and "county" not in county:
        county += " county"
    results = lookup(q="{}, {}".format(county, state))

    def pred(hit: Hit) -> typing.TypeGuard[Hit]:
        return (
            "osm_type" in hit
            and hit["osm_type"] != "node"
            and county in hit["display_name"].lower()
        )

    return next(filter(pred, results), None)


def get_us_city(name: str, state: str) -> Hit | None:
    """Search for US city and return resulting hit."""
    results = lookup_with_params(city=name, state=state)
    if len(results) != 1:
        results = [
            hit for hit in results if hit["type"] == "city" or hit["osm_type"] == "node"
        ]
        if len(results) != 1:
            print("more than one")
            return None
    hit = results[0]
    if hit["type"] not in ("administrative", "city"):
        print("not a city")
        return None
    if hit["osm_type"] == "node":
        print("node")
        return None
    if not hit["display_name"].startswith(name):
        print("wrong name")
        return None
    assert "osm_type" in hit and "osm_id" in hit and "geotext" in hit
    return hit


def get_hit_name(hit: Hit) -> str:
    """Get name from hit."""
    address = hit.get("address")
    if not address:
        assert isinstance(hit["display_name"], str)
        return hit["display_name"]

    address_values = list(address.values())
    n1 = address_values[0]
    if len(address) == 1:
        assert isinstance(n1, str)
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


def get_hit_label(hit: Hit) -> str:
    """Parse hit and generate label."""
    tags = hit["extratags"]
    designation = tags.get("designation")
    category = hit["category"]
    hit_type = hit["type"]

    if designation:
        assert isinstance(designation, str)
        return designation.replace("_", " ")

    if category == "boundary" and hit_type == "administrative":
        place = tags.get("place") or tags.get("linked_place")

        if place:
            return f"{place} {category}"

    if category == "place":
        return f"{hit_type}"

    return f"{hit_type} {category}"
