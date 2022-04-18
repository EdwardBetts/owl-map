from sqlalchemy import func, or_, and_, text
from sqlalchemy.orm import selectinload
from sqlalchemy.sql import select
from sqlalchemy.sql.expression import literal, union, cast, column
from sqlalchemy.types import Float
from sqlalchemy.dialects import postgresql
from matcher.planet import point, line, polygon
from matcher import model, database, wikidata_api, wikidata
from collections import Counter, defaultdict
from flask import g, current_app
import re
import os.path
import json

srid = 4326
re_point = re.compile(r'^POINT\((.+) (.+)\)$')
entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}

tag_prefixes = {
    "disused",
    "was",
    "abandoned",
    "demolished",
    "destroyed",
    "ruins",
    "historic",
}

# these tags are too generic, so we ignore them
skip_tags = {
    "Key:addr",
    "Key:addr:street",
    "Key:lit",
    "Key:image",
    "Key:name",
    "Key:symbol",
    "Key:brand",
}

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

def make_envelope_around_point(lat, lon, distance):
    conn = database.session.connection()

    p = func.ST_MakePoint(lon, lat)

    s = select([
        func.ST_AsText(func.ST_Project(p, distance, func.radians(0))),
        func.ST_AsText(func.ST_Project(p, distance, func.radians(90))),
        func.ST_AsText(func.ST_Project(p, distance, func.radians(180))),
        func.ST_AsText(func.ST_Project(p, distance, func.radians(270))),
    ])
    row = conn.execute(s).fetchone()
    coords = [[float(v) for v in re_point.match(i).groups()] for i in row]

    north = coords[0][1]
    east = coords[1][0]
    south = coords[2][1]
    west = coords[3][0]

    return func.ST_MakeEnvelope(west, south, east, north, srid)

def drop_way_area(tags):
    if "way_area" in tags:
        del tags["way_area"]
    return tags

def get_part_of(table_name, src_id, bbox):
    table_map = {'point': point, 'line': line, 'polygon': polygon}
    table_alias = table_map[table_name].alias()

    s = (select([polygon.c.osm_id,
                 polygon.c.tags,
                 func.ST_Area(func.ST_Collect(polygon.c.way))]).
         where(and_(func.ST_Intersects(bbox, polygon.c.way),
                    func.ST_Covers(polygon.c.way, table_alias.c.way),
                    table_alias.c.osm_id == src_id,
                    polygon.c.tags.has_key("name"),
                    or_(
                        polygon.c.tags.has_key("landuse"),
                        polygon.c.tags.has_key("amenity"),
                    ))).
        group_by(polygon.c.osm_id, polygon.c.tags))

    conn = database.session.connection()
    return [{
        "type": "way" if osm_id > 0 else "relation",
        "id": abs(osm_id),
        "tags": tags,
        "area": area,
    } for osm_id, tags, area in conn.execute(s)]

def get_and_save_item(qid):
    entity = wikidata_api.get_entity(qid)
    entity_qid = entity["id"]
    if entity_qid != qid:
        print(f'redirect {qid} -> {entity_qid}')
        item = model.Item.query.get(entity_qid[1:])
        return item

    if "claims" not in entity:
        return
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


def get_osm_with_wikidata_tag(bbox, isa_filter=None):
    bbox_str = ','.join(str(v) for v in bbox)
    extra_sql = ""
    if isa_filter:
        q = (
            model.Item.query.join(model.ItemLocation)
            .filter(func.ST_Covers(make_envelope(bbox),
                    model.ItemLocation.location))
        )
        q = add_isa_filter(q, isa_filter)
        qids = [isa.qid for isa in q]
        if not qids:
            return []

        qid_list = ",".join(f"'{qid}'" for qid in qids)
        extra_sql += f" AND tags -> 'wikidata' in ({qid_list})"

    # easier than building this query with SQLAlchemy
    sql = f'''
SELECT tbl, osm_id, tags, ARRAY[ST_Y(centroid), ST_X(centroid)], geojson
FROM (
    SELECT 'point' as tbl, osm_id, tags, ST_AsText(ST_Centroid(way)) as centroid, ST_AsGeoJSON(way) as geojson
    FROM planet_osm_point
    WHERE ST_Intersects(ST_MakeEnvelope({bbox_str}, {srid}), way)
UNION
    SELECT 'line' as tbl, osm_id, tags, ST_AsText(ST_Centroid(ST_Collect(way))) AS centroid, ST_AsGeoJSON(ST_Collect(way)) AS geojson
    FROM planet_osm_line
    WHERE ST_Intersects(ST_MakeEnvelope({bbox_str}, {srid}), way)
    GROUP BY osm_id, tags
UNION
    SELECT 'polygon' as tbl, osm_id, tags, ST_AsText(ST_Centroid(ST_Collect(way))) AS centroid, ST_AsGeoJSON(ST_Collect(way)) AS geojson
    FROM planet_osm_polygon
    WHERE ST_Intersects(ST_MakeEnvelope({bbox_str}, {srid}), way)
    GROUP BY osm_id, tags
    HAVING st_area(st_collect(way)) < 20 * st_area(ST_MakeEnvelope({bbox_str}, {srid}))
) as anon
WHERE tags ? 'wikidata'
''' + extra_sql
    conn = database.session.connection()
    result = conn.execute(text(sql))

    print(sql)

    point_sql = f'''
    SELECT 'point' as tbl, osm_id, tags, ST_AsText(ST_Centroid(way)) as centroid, ST_AsGeoJSON(way) as geojson
    FROM planet_osm_point
    WHERE ST_Intersects(ST_MakeEnvelope({bbox_str}, {srid}), way) and tags ? 'wikidata'
''' + extra_sql

    print("point")
    print(point_sql)

    tagged = []
    for tbl, osm_id, tags, centroid, geojson in result:
        if tbl == 'point':
            osm_type = "node"
        else:
            osm_type = "way" if osm_id > 0 else "relation"
            osm_id = abs(osm_id)

        name = tags.get("name") or tags.get("addr:housename") or "[no label]"

        tagged.append({
            "identifier": f"{osm_type}/{osm_id}",
            "id": osm_id,
            "type": osm_type,
            "geojson": json.loads(geojson),
            "centroid": centroid,
            "name": name,
            "wikidata": tags["wikidata"],
        })

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
    isa_list = [v["numeric-id"] for v in item.get_isa()]
    isa_items = [(isa, []) for isa in get_items(isa_list)]

    osm_list = defaultdict(list)

    skip_isa = {row[0] for row in database.session.query(model.SkipIsA.item_id)}

    tram_stop_id = 41176
    airport_id = 1248784
    aerodrome_id = 62447
    if {tram_stop_id, airport_id, aerodrome_id} & set(isa_list):
        skip_isa.add(41176)  # building (Q41176)

    seen = set(isa_list) | skip_isa
    stop = {
        "Q11799049": "public institution",
        "Q7075": "library",
        "Q329683": "industrial park",
    }
    while isa_items:
        isa, isa_path = isa_items.pop()
        if not isa:
            continue
        isa_path = isa_path + [{'qid': isa.qid, 'label': isa.label()}]
        osm = [v for v in isa.get_claim("P1282") if v not in skip_tags]

        osm += [extra.tag_or_key
                for extra in model.ItemExtraKeys.query.filter_by(item_id=isa.item_id)]

        for i in osm:
            osm_list[i].append(isa_path[:])

        if isa.qid in stop:
            # item is specific enough, no need to keep walking the item hierarchy
            continue

        check = set()
        properties = [
            ("P279", "subclass of"),
            ("P140", "religion"),
            ("P641", "sport"),
            ("P366", "use"),
            ("P1269", "facet of"),
            # ("P361", "part of"),
        ]

        for pid, label in properties:
            check |= {v["numeric-id"] for v in (isa.get_claim(pid) or []) if v}

        print(isa.qid, isa.label(), check)
        isa_list = check - seen
        seen.update(isa_list)
        isa_items += [(isa, isa_path) for isa in get_items(isa_list)]
    return {key: list(values) for key, values in osm_list.items()}


def get_tags_for_isa_item(item):
    isa_list = [item.item_id]
    isa_items = [(item, [])]

    osm_list = defaultdict(list)

    skip_isa = {row[0] for row in database.session.query(model.SkipIsA.item_id)}

    tram_stop_id = 41176
    airport_id = 1248784
    aerodrome_id = 62447
    if {tram_stop_id, airport_id, aerodrome_id} & set(isa_list):
        skip_isa.add(41176)  # building (Q41176)

    seen = set(isa_list) | skip_isa
    stop = {
        "Q11799049": "public institution",
        "Q7075": "library",
        "Q329683": "industrial park",
    }
    items_checked = []
    items_checked_done = set()
    while isa_items:
        isa, isa_path = isa_items.pop()
        if not isa:
            continue
        isa_path = isa_path + [{'qid': isa.qid, 'label': isa.label()}]
        if isa.item_id not in items_checked_done:
            items_checked.append({'qid': isa.qid, 'label': isa.label()})
            items_checked_done.add(isa.item_id)
        osm = [v for v in isa.get_claim("P1282") if v not in skip_tags]

        osm += [extra.tag_or_key
                for extra in model.ItemExtraKeys.query.filter_by(item_id=isa.item_id)]

        for i in osm:
            osm_list[i].append(isa_path[:])

        if isa.qid in stop:
            # item is specific enough, no need to keep walking the item hierarchy
            continue

        check = set()
        properties = [
            ("P279", "subclass of"),
            ("P140", "religion"),
            ("P641", "sport"),
            ("P366", "use"),
            ("P1269", "facet of"),
            # ("P361", "part of"),
        ]

        for pid, label in properties:
            check |= {v["numeric-id"] for v in (isa.get_claim(pid) or []) if v}

        print(isa.qid, isa.label(), check)
        isa_list = check - seen
        seen.update(isa_list)
        isa_items += [(isa, isa_path) for isa in get_items(isa_list)]
    return {
        'tags': {key: list(values) for key, values in osm_list.items()},
        'checked': items_checked,
    }


def add_isa_filter(q, isa_qids):

    q_subclass = database.session.query(model.Item.qid).filter(
        func.jsonb_path_query_array(
            model.Item.claims,
            '$.P279[*].mainsnak.datavalue.value.id',
        ).bool_op('?|')(list(isa_qids))
    )

    subclass_qid = {qid for qid, in q_subclass.all()}

    isa = func.jsonb_path_query_array(
        model.Item.claims,
        '$.P31[*].mainsnak.datavalue.value.id',
    ).bool_op('?|')
    return q.filter(isa(list(isa_qids | subclass_qid)))


def wikidata_items_count(bounds, isa_filter=None):

    q = (
        model.Item.query.join(model.ItemLocation)
        .filter(func.ST_Covers(make_envelope(bounds), model.ItemLocation.location))
    )

    if isa_filter:
        q = add_isa_filter(q, isa_filter)

    # print(q.statement.compile(compile_kwargs={"literal_binds": True}))

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

def get_tag_filter(tags, tag_list):
    tag_filter = []
    for tag_or_key in tag_list:
        if tag_or_key.startswith("Key:"):
            key = tag_or_key[4:]
            tag_filter.append(and_(tags.has_key(key), tags[key] != 'no'))
            for prefix in tag_prefixes:
                tag_filter.append(tags.has_key(f"{prefix}:{key}"))

        if tag_or_key.startswith("Tag:"):
            k, _, v = tag_or_key[4:].partition("=")
            tag_filter.append(tags[k] == v)
            for prefix in tag_prefixes:
                tag_filter.append(tags[f"{prefix}:{k}"] == v)

    return tag_filter


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
        lang_code = country_language.get("code")
        if not lang_code:
            continue
        filename = os.path.join(translation_dir, lang_code + ".json")
        json_data = json.load(open(filename))
        if lang_code not in json_data:
            continue

        try:
            return json_data[lang_code]["presets"]["presets"]
        except KeyError:
            pass

    return {}

def get_presets_from_tags(ending, tags):
    translations = get_preset_translations()

    found = []

    for k, v in tags.items():
        if k == 'amenity' and v == 'clock' and tags.get('display') == 'sundial':
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


def address_node_label(tags):
    address = address_from_tags(tags)
    return f"{tags['name']} ({address})" if "name" in tags else address


def get_address_nodes_within_building(osm_id, bbox_list):
    q = model.Point.query.filter(
        polygon.c.osm_id == osm_id,
        or_(*[func.ST_Intersects(bbox, model.Point.way)
              for bbox in bbox_list]),
        func.ST_Covers(polygon.c.way, model.Point.way),
        model.Point.tags.has_key("addr:street"),
        model.Point.tags.has_key("addr:housenumber"),
    )

    return [node.tags for node in q]


def osm_display_name(tags):
    keys = ("bridge:name", "tunnel:name", "lock_name", "name", "addr:housename",
            "inscription")
    for key in keys:
        if key in tags:
            return tags[key]


def street_address_in_tags(tags):
    return "addr:housenumber" in tags and "addr:street" in tags

def find_osm_candidates(item, limit=80, max_distance=450, names=None):
    item_id = item.item_id
    item_is_linear_feature = item.is_linear_feature()
    item_is_street = item.is_street()
    item_names_dict = item.names()
    if item_names_dict:
        item_names = {n.lower() for n in item_names_dict.keys()}
    else:
        item_names = set()

    check_is_street_number_first(item.locations[0].get_lat_lon())

    bbox_list = [make_envelope_around_point(*loc.get_lat_lon(), max_distance)
                 for loc in item.locations]

    null_area = cast(None, Float)
    dist = column('dist')
    tags = column('tags', postgresql.HSTORE)

    tag_list = get_item_tags(item)
    # tag_filters = get_tag_filter(point.c.tags, tag_list)
    # print(tag_filters)

    s_point = (select([literal('point').label('t'), point.c.osm_id, point.c.tags.label('tags'),
                       func.min(func.ST_DistanceSphere(model.ItemLocation.location, point.c.way)).label('dist'),
                       func.ST_AsText(point.c.way),
                       func.ST_AsGeoJSON(point.c.way),
                       null_area]).
               where(and_(
                          or_(*[func.ST_Intersects(bbox, point.c.way)
                                for bbox in bbox_list]),
                          model.ItemLocation.item_id == item_id,
                          or_(*get_tag_filter(point.c.tags, tag_list)))).
               group_by(point.c.osm_id, point.c.tags, point.c.way))

    s_line = (select([literal('line').label('t'), line.c.osm_id, line.c.tags.label('tags'),
                         func.min(func.ST_DistanceSphere(model.ItemLocation.location, line.c.way)).label('dist'),
                         func.ST_AsText(func.ST_Centroid(func.ST_Collect(line.c.way))),
                         func.ST_AsGeoJSON(func.ST_Collect(line.c.way)),
                         null_area]).
                 where(and_(
                     or_(*[func.ST_Intersects(bbox, line.c.way) for bbox in bbox_list]),
                     model.ItemLocation.item_id == item_id,
                     or_(*get_tag_filter(line.c.tags, tag_list)))).
               group_by(line.c.osm_id, line.c.tags))

    s_polygon = (select([literal('polygon').label('t'), polygon.c.osm_id, polygon.c.tags.label('tags'),
                         func.min(func.ST_DistanceSphere(model.ItemLocation.location, polygon.c.way)).label('dist'),
                         func.ST_AsText(func.ST_Centroid(func.ST_Collect(polygon.c.way))),
                         func.ST_AsGeoJSON(func.ST_Collect(polygon.c.way)),
                         func.ST_Area(func.ST_Collect(polygon.c.way))]).
                 where(and_(
                     or_(*[func.ST_Intersects(bbox, polygon.c.way) for bbox in bbox_list]),
                     model.ItemLocation.item_id == item_id,
                     or_(*get_tag_filter(polygon.c.tags, tag_list)))).
               group_by(polygon.c.osm_id, polygon.c.tags).
               having(func.ST_Area(func.ST_Collect(polygon.c.way)) < 20 * func.ST_Area(bbox_list[0])))

    tables = ([] if item_is_linear_feature else [s_point]) + [s_line, s_polygon]
    s = select([union(*tables).alias()]).where(dist < max_distance).order_by(dist)

    if names:
        s = s.where(or_(tags["name"].in_(names), tags["old_name"].in_(names)))

    if item_is_street:
        s = s.where(tags["highway"] != "bus_stop")
        if not names:
            s = s.where(tags.has_key("name"))

    if "Key:amenity" in tag_list:
        s = s.where(and_(tags["amenity"] != "bicycle_parking",
                         tags["amenity"] != "bicycle_repair_station",
                         tags["amenity"] != "atm",
                         tags["amenity"] != "recycling"))

    if limit:
        s = s.limit(limit)

    print(s.compile(compile_kwargs={"literal_binds": True}))

    conn = database.session.connection()
    nearby = []
    for table, src_id, tags, distance, centroid, geojson, area in conn.execute(s):
        osm_id = src_id
        if table == "point":
            osm_type = "node"
        elif osm_id > 0:
            osm_type = "way"
        else:
            osm_type = "relation"
            osm_id = -osm_id

        tags.pop("way_area", None)
        name = osm_display_name(tags)
        if not name and street_address_in_tags(tags):
            name = address_from_tags(tags)

        if table == "polygon" and "building" in tags:
            address_nodes = get_address_nodes_within_building(src_id, bbox_list)
            address_list = [address_node_label(addr) for addr in address_nodes]
        else:
            address_list = []

        shape = "area" if table == "polygon" else table

        cur = {
            "identifier": f"{osm_type}/{osm_id}",
            "type": osm_type,
            "id": osm_id,
            "distance": distance,
            "name": name,
            "name_match": (name and name.lower() in item_names),
            "tags": tags,
            "geojson": json.loads(geojson),
            "presets": get_presets_from_tags(shape, tags),
            "address_list": address_list,
            "centroid": list(reversed(re_point.match(centroid).groups())),
        }
        if area is not None:
            cur["area"] = area

        part_of = []
        for bbox in bbox_list:
            part_of += [i for i in get_part_of(table, src_id, bbox)
                        if i["tags"]["name"] != name]
        if part_of:
            cur["part_of"] = part_of

        if address := address_from_tags(tags):
            cur["address"] = address

        nearby.append(cur)

    return nearby

def get_item(item_id):
    item = model.Item.query.get(item_id)
    return item or get_and_save_item(f"Q{item_id}")


def get_item_street_addresses(item):
    street_address = [addr["text"] for addr in item.get_claim("P6375") if addr]
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

def check_is_street_number_first(latlng):
    g.street_number_first = is_street_number_first(*latlng)

def item_detail(item):
    unsupported_relation_types = {
        'Q194356',   # wind farm
        'Q2175765',  # tram stop
    }

    locations = [list(i.get_lat_lon()) for i in item.locations]
    if not hasattr(g, 'street_number_first'):
        g.street_number_first = is_street_number_first(*locations[0])

    image_filenames = item.get_claim("P18")

    street_address = get_item_street_addresses(item)

    heritage_designation = []
    for v in item.get_claim("P1435"):
        if not v:
            print('heritage designation missing:', item.qid)
            continue
        heritage_designation_item = get_item(v["numeric-id"])
        heritage_designation.append({
            "qid": v["id"],
            "label": heritage_designation_item.label(),
        })

    isa_items = [get_item(isa["numeric-id"]) for isa in item.get_isa()]
    isa_lookup = {isa.qid: isa for isa in isa_items}

    wikipedia_links = [{"lang": site[:-4], "title": link["title"]}
                       for site, link in sorted(item.sitelinks.items())
                       if site.endswith("wiki") and len(site) < 8]

    d = {
        "qid": item.qid,
        "label": item.label(),
        "description": item.description(),
        "markers": locations,
        "image_list": image_filenames,
        "street_address": street_address,
        "isa_list": [{"qid": isa.qid, "label": isa.label()} for isa in isa_items if isa],
        "closed": item.closed(),
        "inception": item.time_claim("P571"),
        "p1619": item.time_claim("P1619"),
        "p576": item.time_claim("P576"),
        "heritage_designation": heritage_designation,
        "wikipedia": wikipedia_links,
    }

    if aliases := item.get_aliases():
        d["aliases"] = aliases

    if "commonswiki" in item.sitelinks:
        d["commons"] = item.sitelinks["commonswiki"]["title"]

    unsupported = isa_lookup.keys() & unsupported_relation_types
    if unsupported:
        d["unsupported_relation_types"] = [isa for isa in d["isa_list"]
                                           if isa.qid in isa_lookup]

    return d


def get_markers(all_items):
    return [item_detail(item) for item in all_items if item]


def wikidata_items(bounds, isa_filter=None):
    check_is_street_number_first(get_bbox_centroid(bounds))
    q = get_items_in_bbox(bounds)

    if isa_filter:
        q = add_isa_filter(q, isa_filter)

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

def isa_incremental_search(search_terms):
    en_label = func.jsonb_extract_path_text(model.Item.labels, "en", "value")
    q = model.Item.query.filter(
            model.Item.claims.has_key("P1282"),
            en_label.ilike(f"%{search_terms}%"),
            func.length(en_label) < 20,
    )

    print(q.statement.compile(compile_kwargs={"literal_binds": True}))

    ret = []
    for item in q:
        cur = {
            "qid": item.qid,
            "label": item.label(),
        }
        ret.append(cur)
    return ret

def get_place_items(osm_type, osm_id):
    src_id = osm_id * {'way': 1, 'relation': -1}[osm_type]

    q = (model.Item.query
                   .join(model.ItemLocation)
                   .join(model.Polygon, func.ST_Covers(model.Polygon.way, model.ItemLocation.location))
                   .filter(model.Polygon.src_id == src_id))
    # sql = q.statement.compile(compile_kwargs={"literal_binds": True})

    item_count = q.count()
    items = []
    for item in q:
        keys = ["item_id", "labels", "descriptions", "aliases", "sitelinks", "claims"]
        item_dict = {key: getattr(item, key) for key in keys}
        items.append(item_dict)

    return {"count": item_count, "items": items}
