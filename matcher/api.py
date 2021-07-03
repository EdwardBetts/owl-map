from sqlalchemy import func, or_, and_
from sqlalchemy.orm import selectinload
from matcher import model, database, wikidata_api, wikidata
from matcher.data import extra_keys
from collections import Counter, defaultdict
from flask import g, current_app
import re
import os.path
import json

srid = 4326
re_point = re.compile(r'^POINT\((.+) (.+)\)$')
entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}


def get_country_iso3166_1(lat, lon):
    point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), srid)
    alpha2_codes = set()
    q = model.Polygon.query.filter(func.ST_Covers(model.Polygon.way, point),
                                   model.Polygon.admin_level == "2")
    for country in q:
        alpha2 = country.tags.get("ISO3166-1")
        if not alpha2:
            continue
        alpha2_codes.add(alpha2)

    g.alpha2_codes = alpha2_codes
    return alpha2_codes


def is_street_number_first(lat, lon):
    if lat is None or lon is None:
        return True

    alpha2 = get_country_iso3166_1(lat, lon)
    alpha2_number_first = {'GB', 'IE', 'US', 'MX', 'CA', 'FR', 'AU', 'NZ', 'ZA'}

    return bool(alpha2_number_first & alpha2)


def make_envelope(bounds):
    return func.ST_MakeEnvelope(*bounds, srid)


def get_bbox_centroid(bbox):
    bbox = make_envelope(bbox)
    centroid = database.session.query(func.ST_AsText(func.ST_Centroid(bbox))).scalar()
    return reversed(re_point.match(centroid).groups())


def get_part_of(thing, bbox):
    db_bbox = make_envelope(bbox)
    ewkt = thing.as_EWKT
    q = model.Polygon.query.filter(
        func.ST_Intersects(db_bbox, model.Polygon.way),
        func.ST_Covers(model.Polygon.way, func.ST_GeomFromEWKT(ewkt)),
        or_(
            model.Polygon.tags.has_key("landuse"),
            model.Polygon.tags.has_key("amenity"),
        ),
        model.Polygon.tags.has_key("name"),
    )

    return [polygon.tags for polygon in q]


def get_and_save_item(qid):
    entity = wikidata_api.get_entity(qid)
    entity_qid = entity["id"]
    if entity_qid != qid:
        print(f'redirect {qid} -> {entity_qid}')
        item = model.Item.query.get(entity_qid[1:])
        return item

    coords = wikidata.get_entity_coords(entity["claims"])

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
    database.session.commit()

    return item


def get_isa_count(items):
    isa_count = Counter()
    for item in items:
        if not item:
            continue
        isa_list = item.get_claim("P31")
        for isa in isa_list:
            if not isa:
                print("missing IsA:", item.qid)
                continue
            isa_count[isa["id"]] += 1

    return isa_count.most_common()


def get_items_in_bbox(bbox):
    db_bbox = make_envelope(bbox)

    q = (
        model.Item.query.join(model.ItemLocation)
        .filter(func.ST_Covers(db_bbox, model.ItemLocation.location))
        .options(selectinload(model.Item.locations))
    )

    return q


def get_osm_with_wikidata_tag(bbox):
    db_bbox = make_envelope(bbox)

    tagged = []

    seen = set()
    for cls in (model.Point, model.Polygon, model.Line):
        q = cls.query.filter(
            cls.tags.has_key("wikidata"),
            func.ST_Intersects(db_bbox, cls.way),
            func.ST_Area(cls.way) < 20 * func.ST_Area(db_bbox),
        )
        for osm in q:
            if osm.identifier in seen:
                continue
            seen.add(osm.identifier)
            name = osm.name or osm.tags.get("addr:housename") or "[no label]"

            tagged.append(
                {
                    "identifier": osm.identifier,
                    "id": osm.id,
                    "type": osm.type,
                    "url": osm.osm_url,
                    "geojson": osm.geojson(),
                    "centroid": list(osm.get_centroid()),
                    "name": name,
                    "wikidata": osm.tags["wikidata"],
                }
            )

    return tagged


def get_items(item_ids):
    items = []
    for item_id in item_ids:
        item = model.Item.query.get(item_id)
        if not item:
            if not get_and_save_item(f"Q{item_id}"):
                continue
            item = model.Item.query.get(item_id)
        items.append(item)

    return items


def get_item_tags(item):
    skip_tags = {"Key:addr", "Key:addr:street", "Key:lit"}

    isa_items = []
    isa_list = [v["numeric-id"] for v in item.get_claim("P31")]
    isa_items = [(isa, []) for isa in get_items(isa_list)]

    osm_list = defaultdict(list)

    skip_isa = {row[0] for row in database.session.query(model.SkipIsA.item_id)}
    if item.is_tram_stop():
        skip_isa.add(41176)  # building (Q41176)

    seen = set(isa_list) | skip_isa
    while isa_items:
        isa, isa_path = isa_items.pop()
        if not isa:
            continue
        isa_path = isa_path + [{'qid': isa.qid, 'label': isa.label()}]
        osm = [v for v in isa.get_claim("P1282") if v not in skip_tags]
        if isa.qid in extra_keys:
            osm += extra_keys[isa.qid]

        for i in osm:
            osm_list[i].append(isa_path[:])

        subclass_of = [v["numeric-id"] for v in (isa.get_claim("P279") or []) if v]
        religion = [v["numeric-id"] for v in (isa.get_claim("P140") or []) if v]
        sport = [v["numeric-id"] for v in (isa.get_claim("P641") or []) if v]
        use = [v["numeric-id"] for v in (isa.get_claim("P366") or []) if v]
        check = subclass_of + religion + sport + use
        print(isa.qid, isa.label(), check)
        isa_list = [isa_id for isa_id in check if isa_id not in seen]
        seen.update(isa_list)
        isa_items += [(isa, isa_path) for isa in get_items(isa_list)]
    return {key: list(values) for key, values in osm_list.items()}


def wikidata_items_count(bounds):
    q = (
        model.Item.query.join(model.ItemLocation)
        .filter(func.ST_Covers(make_envelope(bounds), model.ItemLocation.location))
    )

    return q.count()

def wikidata_isa_counts(bounds):

    db_bbox = make_envelope(bounds)

    q = (
        model.Item.query.join(model.ItemLocation)
        .filter(func.ST_Covers(db_bbox, model.ItemLocation.location))
    )

    db_items = q.all()

    counts = get_isa_count(db_items)
    isa_ids = [qid[1:] for qid, count in counts]
    isa_items = {
        isa.qid: isa for isa in model.Item.query.filter(model.Item.item_id.in_(isa_ids))
    }
    isa_count = []
    for qid, count in counts:
        item = isa_items.get(qid)
        if not item:
            item = get_and_save_item(qid)

        label = item.label() if item else "[missing]"
        isa = {
            "qid": qid,
            "count": count,
            "label": label,
        }
        isa_count.append(isa)

    return isa_count

def get_tag_filter(cls, tag_list):
    tag_filter = []
    for tag_or_key in tag_list:
        if tag_or_key.startswith("Key:"):
            tag_filter.append(and_(cls.tags.has_key(tag_or_key[4:]),
                                   cls.tags[tag_or_key[4:]] != 'no'))
        if tag_or_key.startswith("Tag:"):
            k, _, v = tag_or_key.partition("=")
            tag_filter.append(cls.tags[k[4:]] == v)

    return tag_filter

def get_nearby(bbox, item, max_distance=300):
    db_bbox = make_envelope(bbox)

    osm_objects = {}
    distances = {}
    tag_list = get_item_tags(item)
    if not tag_list:
        return []

    item_is_street = item.is_street()

    for loc in item.locations:
        lat, lon = loc.get_lat_lon()
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        for cls in model.Point, model.Line, model.Polygon:
            if item_is_street and cls == model.Point:
                continue

            tag_filter = get_tag_filter(cls, tag_list)
            dist = func.ST_DistanceSphere(point, cls.way)

            q = (cls.query.add_columns(dist.label('distance'))
                          .filter(
                              func.ST_Intersects(db_bbox, cls.way),
                              func.ST_Area(cls.way) < 20 * func.ST_Area(db_bbox),
                              or_(*tag_filter))
                          .order_by(point.distance_centroid(cls.way)))

            if item_is_street:
                q = q.filter(cls.tags.has_key("name"),
                             cls.tags["highway"] != 'bus_stop')

            if "Key:amenity" in tag_list:
                q = q.filter(cls.tags["amenity"] != "bicycle_parking",
                             cls.tags["amenity"] != "bicycle_repair_station",
                             cls.tags["amenity"] != "atm",
                             cls.tags["amenity"] != "recycling")

            q = q.limit(40)

            # print(q.statement.compile(compile_kwargs={"literal_binds": True}))

            for i, dist in q:
                if dist > max_distance:
                    continue
                osm_objects.setdefault(i.identifier, i)
                if i.identifier not in distances or dist < distances[i.identifier]:
                    distances[i.identifier] = dist

    nearby = [(osm_objects[identifier], dist)
              for identifier, dist
              in sorted(distances.items(), key=lambda i:i[1])]

    return nearby[:40]


def get_preset_translations():
    app = current_app
    country_language = {
        'AU': 'en-AU',  # Australia
        'GB': 'en-GB',  # United Kingdom
        'IE': 'en-GB',  # Ireland
        'IN': 'en-IN',  # India
        'NZ': 'en-NZ',  # New Zealand
    }
    ts_dir = app.config["ID_TAGGING_SCHEMA_DIR"]
    translation_dir = os.path.join(ts_dir, "dist", "translations")

    for code in g.alpha2_codes:
        if code not in country_language:
            continue
        filename = os.path.join(translation_dir, country_language[code] + ".json")
        return json.load(open(filename))["en-GB"]["presets"]["presets"]

    return {}

def get_presets_from_tags(osm):
    translations = get_preset_translations()

    found = []
    endings = {model.Point: "point", model.Line: "line", model.Polygon: "area"}
    ending = endings[type(osm)]

    for k, v in osm.tags.items():
        if k == 'amenity' and v == 'clock' and osm.tags.get('display') == 'sundial':
            tag_or_key = f"Tag:{k}={v}"
            found.append({"tag_or_key": tag_or_key, "name": "Sundial"})
            continue

        match = find_preset_file(k, v, ending)
        if not match:
            continue

        preset = match["preset"]
        if preset in translations:
            match["name"] = translations[preset]["name"]
        else:
            match["name"] = json.load(open(match["filename"]))["name"]

        del match["filename"]

        found.append(match)

    return found


def find_preset_file(k, v, ending):
    app = current_app
    ts_dir = app.config["ID_TAGGING_SCHEMA_DIR"]
    preset_dir = os.path.join(ts_dir, "data", "presets")

    filename = os.path.join(preset_dir, k, v + ".json")
    if os.path.exists(filename):
        return {
            "tag_or_key": f"Tag:{k}={v}",
            "preset": f"{k}/{v}",
            "filename": filename,
        }

    filename = os.path.join(preset_dir, k, f"{v}_{ending}.json")
    if os.path.exists(filename):
        return {
            "tag_or_key": f"Tag:{k}={v}",
            "preset": f"{k}/{v}",
            "filename": filename,
        }

    filename = os.path.join(preset_dir, k, "_" + v + ".json")
    if os.path.exists(filename):
        return {
            "tag_or_key": f"Tag:{k}={v}",
            "preset": f"{k}/{v}",
            "filename": filename,
        }

    filename = os.path.join(preset_dir, k + ".json")
    if os.path.exists(filename):
        return {
            "tag_or_key": f"Key:{k}",
            "preset": k,
            "filename": filename,
        }


def address_from_tags(tags):
    keys = ["street", "housenumber"]
    if not all("addr:" + k in tags for k in keys):
        return

    if g.street_number_first:
        keys.reverse()
    return " ".join(tags["addr:" + k] for k in keys)


def get_address_nodes_within_building(building, bbox):
    db_bbox = make_envelope(bbox)
    ewkt = building.as_EWKT
    q = model.Point.query.filter(
        func.ST_Intersects(db_bbox, model.Point.way),
        func.ST_Covers(func.ST_GeomFromEWKT(ewkt), model.Point.way),
        model.Point.tags.has_key("addr:street"),
        model.Point.tags.has_key("addr:housenumber"),
    )

    return [node.tags for node in q]


def find_osm_candidates(item, bounds):
    g.street_number_first = is_street_number_first(*get_bbox_centroid(bounds))

    nearby = []
    for osm, dist in get_nearby(bounds, item):
        tags = osm.tags
        tags.pop("way_area", None)
        name = osm.display_name()
        if not name and osm.has_street_address:
            name = address_from_tags(tags)

        if isinstance(osm, model.Polygon) and "building" in osm.tags:
            address_nodes = get_address_nodes_within_building(osm, bounds)
            address_list = [address_from_tags(addr) for addr in address_nodes]
        else:
            address_list = []
        cur = {
            "identifier": osm.identifier,
            "distance": dist,
            "name": name,
            "tags": tags,
            "geojson": osm.geojson(),
            "presets": get_presets_from_tags(osm),
            "address_list": address_list,
        }
        if hasattr(osm, 'area'):
            cur["area"] = osm.area

        if address := address_from_tags(tags):
            cur["address"] = address

        part_of = [i["name"] for i in get_part_of(osm, bounds) if i["name"] != name]
        if part_of:
            cur["part_of"] = part_of

        nearby.append(cur)

    return nearby

def get_item(item_id):
    item = model.Item.query.get(item_id)
    if item:
        return item
    item = get_and_save_item(f"Q{item_id}")
    database.session.add(item)
    database.session.commit()
    return item


def get_item_street_addresses(item):
    street_address = [addr["text"] for addr in item.get_claim("P6375")]
    if street_address or "P669" not in item.claims:
        return street_address

    for claim in item.claims["P669"]:
        qualifiers = claim.get("qualifiers")
        if not qualifiers or 'P670' not in qualifiers:
            continue
        number = qualifiers["P670"][0]["datavalue"]["value"]

        street_item = get_item(claim["mainsnak"]["datavalue"]["value"]["numeric-id"])
        street = street_item.label()
        for q in qualifiers["P670"]:
            number = q["datavalue"]["value"]
            address = (f"{number} {street}"
                       if g.street_number_first
                       else f"{street} {number}")
            street_address.append(address)

    return street_address


def get_markers(all_items):
    items = []
    for item in all_items:
        if not item:
            continue
        locations = [list(i.get_lat_lon()) for i in item.locations]
        image_filenames = item.get_claim("P18")

        street_address = get_item_street_addresses(item)

        d = {
            "qid": item.qid,
            "label": item.label(),
            "description": item.description(),
            "markers": locations,
            "image_list": image_filenames,
            "street_address": street_address,
            "isa_list": [v["id"] for v in item.get_claim("P31") if v],
        }

        if aliases := item.get_aliases():
            d["aliases"] = aliases

        items.append(d)

    return items


def wikidata_items(bounds):
    g.street_number_first = is_street_number_first(*get_bbox_centroid(bounds))
    q = get_items_in_bbox(bounds)
    db_items = q.all()
    items = get_markers(db_items)

    counts = get_isa_count(db_items)
    isa_ids = [qid[1:] for qid, count in counts]
    isa_items = {
        isa.qid: isa for isa in model.Item.query.filter(model.Item.item_id.in_(isa_ids))
    }

    isa_count = []
    for qid, count in counts:
        item = isa_items.get(qid)
        if not item:
            item = get_and_save_item(qid)

        label = item.label() if item else "[missing]"
        isa = {
            "qid": qid,
            "count": count,
            "label": label,
        }
        isa_count.append(isa)

    return {'items': items, 'isa_count': isa_count}


def missing_wikidata_items(qids, lat, lon):
    g.street_number_first = is_street_number_first(lat, lon)

    db_items = []
    for qid in qids:
        item = model.Item.query.get(qid[1:])
        if not item:
            item = get_and_save_item(qid)
        db_items.append(item)
    items = get_markers(db_items)
    counts = get_isa_count(db_items)
    isa_ids = [qid[1:] for qid, count in counts]
    isa_items = {
        isa.qid: isa for isa in model.Item.query.filter(model.Item.item_id.in_(isa_ids))
    }

    isa_count = []
    for qid, count in counts:
        item = isa_items.get(qid)
        if not item:
            item = get_and_save_item(qid)

        label = item.label() if item else "[missing]"
        isa = {
            "qid": qid,
            "count": count,
            "label": label,
        }
        isa_count.append(isa)

    return dict(items=items, isa_count=isa_count)
