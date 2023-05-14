"""Process Wikidata items to extract coordinates and names."""

import re
import typing
from collections import defaultdict
from typing import Any, cast

from . import wikidata_api

hq_pid = "P159"
coords_pid = "P625"

Claims = dict[str, list[dict[str, Any]]]


class Coords(typing.TypedDict):
    """Coordinates."""

    latitude: float
    longitude: float


def read_coords(snak: dict[str, Any]) -> Coords | None:
    """Read coordinates from snak."""
    try:
        v = snak["datavalue"]["value"]
    except KeyError:
        return None
    if v["globe"].rpartition("/")[2] != "Q2":
        return None

    return cast(Coords, {k: v[k] for k in ("latitude", "longitude")})


def read_hq_coords(claims: Claims) -> list[Coords]:
    """Coordinates of item headquarters."""
    found: list[Coords] = []
    for hq_claim in claims.get(hq_pid, []):
        for snak in hq_claim.get("qualifiers", {}).get(coords_pid, []):
            if coords := read_coords(snak):
                found.append(coords)

    return found


def read_location_statement(claims: Claims, pid: str) -> list[Coords]:
    """Get coordinates from given claim."""
    return [i for i in (read_coords(c["mainsnak"]) for c in claims.get(pid, [])) if i]


def get_entity_coords(claims: Claims) -> dict[str, Any]:
    """Read entity coordinate locations from claims dict."""
    assert "claims" not in claims  # make sure we weren't passed entity by mistake
    ret = {
        coords_pid: read_location_statement(claims, coords_pid),
        hq_pid: read_hq_coords(claims),
    }
    return {pid: values for pid, values in ret.items() if values}


def names_from_entity(
    entity: wikidata_api.EntityType, skip_lang: set[str] | None = None
) -> dict[str, Any]:
    """Find all sources of names from Item."""
    if skip_lang is None:
        skip_lang = set()

    ret = defaultdict(list)
    cat_start = "Category:"

    for k, v in entity["labels"].items():
        if k in skip_lang:
            continue
        ret[v["value"]].append(("label", k))

    for k, v in entity["sitelinks"].items():
        if k + "wiki" in skip_lang:
            continue
        title = v["title"]
        if title.startswith(cat_start):
            title = title[len(cat_start) :]

        first_letter = title[0]
        if first_letter.isupper():
            lc_first_title = first_letter.lower() + title[1:]
            if lc_first_title in ret:
                title = lc_first_title

        ret[title].append(("sitelink", k))

    for lang, value_list in entity.get("aliases", {}).items():
        if lang in skip_lang or len(value_list) > 3:
            continue
        for name in value_list:
            ret[name["value"]].append(("alias", lang))

    commonscats = entity.get("claims", {}).get("P373", [])
    for i in commonscats:
        if "datavalue" not in i["mainsnak"]:
            continue
        value = i["mainsnak"]["datavalue"]["value"]
        ret[value].append(("commonscat", None))

    officialname = entity.get("claims", {}).get("P1448", [])
    for i in officialname:
        if "datavalue" not in i["mainsnak"]:
            continue
        value = i["mainsnak"]["datavalue"]["value"]
        ret[value["text"]].append(("officialname", value["language"]))

    nativelabel = entity.get("claims", {}).get("P1705", [])
    for i in nativelabel:
        if "datavalue" not in i["mainsnak"]:
            continue
        value = i["mainsnak"]["datavalue"]["value"]
        ret[value["text"]].append(("nativelabel", value["language"]))

    image = entity.get("claims", {}).get("P18", [])
    for i in image:
        if "datavalue" not in i["mainsnak"]:
            continue
        value = i["mainsnak"]["datavalue"]["value"]
        m = re.search(r"\.[a-z]{3,4}$", value)
        if m:
            value = value[: m.start()]
        for pattern in r" - geograph\.org\.uk - \d+$", r"[, -]*0\d{2,}$":
            m = re.search(pattern, value)
            if m:
                value = value[: m.start()]
                break
        ret[value].append(("image", None))

    return ret
