hq_pid = "P159"
coords_pid = "P625"


def read_coords(snak):
    try:
        v = snak["datavalue"]["value"]
    except KeyError:
        return
    if v["globe"].rpartition("/")[2] != "Q2":
        return

    return {k: v[k] for k in ("latitude", "longitude")}


def read_hq_coords(claims):
    if hq_pid not in claims:
        return []

    found = []
    for hq_claim in claims[hq_pid]:
        if "qualifiers" not in hq_claim:
            continue
        if coords_pid not in hq_claim["qualifiers"]:
            continue
        for snak in hq_claim["qualifiers"][coords_pid]:
            coords = read_coords(snak)
            if coords:
                found.append(coords)

    return found


def read_location_statement(claims, pid):
    if pid not in claims:
        return []

    found = []
    for statement in claims[pid]:
        coords = read_coords(statement["mainsnak"])
        if coords:
            found.append(coords)
    return found


def get_entity_coords(claims):
    assert "claims" not in claims  # make sure we weren't passed entity by mistake
    ret = {
        coords_pid: read_location_statement(claims, coords_pid),
        hq_pid: read_hq_coords(claims),
    }
    return {pid: values for pid, values in ret.items() if values}
