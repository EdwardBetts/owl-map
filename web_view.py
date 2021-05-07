#!/usr/bin/python3

from flask import Flask, render_template, request, jsonify, redirect, url_for
from sqlalchemy import func
from sqlalchemy.orm import selectinload
from matcher import nominatim, model, database
from collections import Counter
from time import time
import GeoIP

srid = 4326

app = Flask(__name__)
app.debug = True

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)

property_map = [
    ("P238", ["iata"], "IATA airport code"),
    ("P239", ["icao"], "ICAO airport code"),
    ("P240", ["faa", "ref"], "FAA airport code"),
    # ('P281', ['addr:postcode', 'postal_code'], 'postal code'),
    ("P296", ["ref", "ref:train", "railway:ref"], "station code"),
    ("P300", ["ISO3166-2"], "ISO 3166-2 code"),
    ("P359", ["ref:rce"], "Rijksmonument ID"),
    ("P590", ["ref:gnis", "GNISID", "gnis:id", "gnis:feature_id"], "USGS GNIS ID"),
    ("P649", ["ref:nrhp"], "NRHP reference number"),
    ("P722", ["uic_ref"], "UIC station code"),
    ("P782", ["ref"], "LAU (local administrative unit)"),
    ("P836", ["ref:gss"], "UK Government Statistical Service code"),
    ("P856", ["website", "contact:website", "url"], "website"),
    ("P882", ["nist:fips_code"], "FIPS 6-4 (US counties)"),
    ("P901", ["ref:fips"], "FIPS 10-4 (countries and regions)"),
    # A UIC id can be a IBNR, but not every IBNR is an UIC id
    ("P954", ["uic_ref"], "IBNR ID"),
    ("P981", ["ref:woonplaatscode"], "BAG code for Dutch residencies"),
    ("P1216", ["HE_ref"], "National Heritage List for England number"),
    ("P2253", ["ref:edubase"], "EDUBase URN"),
    ("P2815", ["esr:user", "ref", "ref:train"], "ESR station code"),
    ("P3425", ["ref", "ref:SIC"], "Natura 2000 site ID"),
    ("P3562", ["seamark:light:reference"], "Admiralty number"),
    (
        "P4755",
        ["ref", "ref:train", "ref:crs", "crs", "nat_ref"],
        "UK railway station code",
    ),
    ("P4803", ["ref", "ref:train"], "Amtrak station code"),
    ("P6082", ["nycdoitt:bin"], "NYC Building Identification Number"),
    ("P5086", ["ref"], "FIPS 5-2 alpha code (US states)"),
    ("P5087", ["ref:fips"], "FIPS 5-2 numeric code (US states)"),
    ("P5208", ["ref:bag"], "BAG building ID for Dutch buildings"),
]


@app.teardown_appcontext
def shutdown_session(exception=None):
    database.session.remove()


def check_for_tagged_qids(qids):
    tagged = set()
    for qid in qids:
        for cls in model.Point, model.Polygon, model.Line:
            q = cls.query.filter(cls.tags["wikidata"] == qid)
            print(q)
            if q.count():
                tagged.add(qid)
                break

    return tagged


def check_for_tagged_qid(qid):
    return any(
        database.session.query(
            cls.query.filter(
                cls.tags.has_key("wikidata"), cls.tags["wikidata"] == qid
            ).exists()
        ).scalar()
        for cls in (model.Point, model.Polygon, model.Line)
    )


def get_tagged_qid(qid):
    tagged = []
    seen = set()
    for cls in (model.Point, model.Polygon, model.Line):
        q = cls.query.filter(cls.tags.has_key("wikidata"), cls.tags["wikidata"] == qid)
        for osm in q:
            if osm.identifier in seen:
                continue
            seen.add(osm.identifier)
            tagged.append(
                {
                    "identifier": osm.identifier,
                    "url": osm.osm_url,
                    # 'geoson': osm.geojson(),
                    "centroid": list(osm.get_centroid()),
                    "name": osm.name or "[no label]",
                }
            )

    return tagged


def make_envelope(bbox):
    west, south, east, north = [float(i) for i in bbox.split(",")]
    return func.ST_MakeEnvelope(west, south, east, north, srid)


def get_osm_with_wikidata_tag(bbox):
    db_bbox = make_envelope(bbox)

    tagged = []

    seen = set()
    for cls in (model.Point, model.Polygon, model.Line):
        q = cls.query.filter(
            cls.tags.has_key("wikidata"), func.ST_Covers(db_bbox, cls.way)
        )
        for osm in q:
            if osm.identifier in seen:
                continue
            seen.add(osm.identifier)
            name = osm.name
            if not name:
                if "addr:housename" in osm.tags:
                    name = osm.tags["addr:housename"]
                else:
                    name = "[no label]"

            tagged.append(
                {
                    "identifier": osm.identifier,
                    "url": osm.osm_url,
                    # 'geoson': osm.geojson(),
                    "centroid": list(osm.get_centroid()),
                    "name": name,
                    "wikidata": osm.tags["wikidata"],
                }
            )

    return tagged


def get_items_in_bbox(bbox):
    db_bbox = make_envelope(bbox)

    q = (
        model.Item.query.join(model.ItemLocation)
        .filter(func.ST_Covers(db_bbox, model.ItemLocation.location))
        .options(selectinload(model.Item.locations))
    )

    return q


def get_markers(all_items):
    items = []
    for item in all_items:
        if "en" not in item.labels:
            continue
        locations = [list(i.get_lat_lon()) for i in item.locations]
        item = {
            "qid": item.qid,
            "label": item.label(),
            "description": item.description(),
            "markers": locations,
            "isa_list": [v["id"] for v in item.get_claim("P31")],
        }
        items.append(item)

    return items


def get_user_location():
    gi = GeoIP.open("/home/edward/lib/data/GeoIPCity.dat", GeoIP.GEOIP_STANDARD)

    remote_ip = request.remote_addr
    gir = gi.record_by_addr(remote_ip)
    if not gir:
        return
    lat, lon = gir["latitude"], gir["longitude"]
    return (lat, lon)


@app.route("/")
def redirect_from_root():
    return redirect(url_for("map_start_page"))


@app.route("/index")
def index_page():
    return render_template("index.html")


@app.route("/identifier")
def identifier_index():
    return render_template("identifier_index.html", property_map=property_map)


@app.route("/identifier/<pid>")
def identifier_page(pid):
    per_page = 10
    page = int(request.args.get("page", 1))
    property_dict = {pid: (osm_keys, label) for pid, osm_keys, label in property_map}
    osm_keys, label = property_dict[pid]

    wd = model.Item.query.filter(model.Item.claims.has_key(pid))
    total = wd.count()

    start = per_page * (page - 1)
    items = wd.all()[start : per_page * page]

    qids = [item.qid for item in items]
    print(qids)

    #    pred = None
    #    values = set()
    #    for item in items:
    #        values |= set(item.get_claim(pid))
    #
    #    for key in osm_keys:
    #        if key == 'ref':
    #            continue
    #        if pred is None:
    #            pred = model.Point.tags[key].in_(values)
    #        else:
    #            pred |= model.Point.tags[key].in_(values)
    #

    osm_points = {}

    for qid in qids:
        osm_points[qid] = model.Point.query.filter(
            model.Point.tags["wikidata"] == qid
        ).all()

    osm_total = len(osm_points)

    return render_template(
        "identifier_page.html",
        pid=pid,
        osm_keys=osm_keys,
        label=label,
        items=items,
        total=total,
        osm_total=osm_total,
        osm_points=osm_points,
    )


@app.route("/map/<int:zoom>/<float(signed=True):lat>/<float(signed=True):lng>")
def map_location(zoom, lat, lng):
    t = int(time())
    return render_template("map.html", zoom=zoom, lat=lat, lng=lng, time=t)


@app.route("/map")
def map_start_page():
    t = int(time())
    location = get_user_location()
    if not location:
        return render_template("map.html", zoom=16, lat=None, lng=None, time=t)

    lat, lng = location
    return render_template("map.html", zoom=16, lat=lat, lng=lng, time=t)


@app.route("/search/map")
def search_map_page():
    user_lat, user_lon = get_user_location() or (None, None)

    q = request.args.get("q")
    if not q:
        return render_template("map.html", user_lat=user_lat, user_lon=user_lon)

    hits = nominatim.lookup(q)
    for hit in hits:
        if "geotext" in hit:
            del hit["geotext"]
    bbox = [hit["boundingbox"] for hit in hits]

    return render_template(
        "search_map.html",
        hits=hits,
        bbox_list=bbox,
        user_lat=user_lat,
        user_lon=user_lon,
    )


@app.route("/search")
def search_page():
    q = request.args.get("q")
    if not q:
        return render_template("search.html", hits=None, bbox_list=None)
    hits = nominatim.lookup(q)
    for hit in hits:
        if "geotext" in hit:
            del hit["geotext"]
    bbox = [hit["boundingbox"] for hit in hits]
    return render_template("search.html", hits=hits, bbox_list=bbox)


def get_isa_count(items):
    isa_count = Counter()
    for item in items:
        isa_list = item.get_claim("P31")
        for isa in isa_list:
            isa_count[isa["id"]] += 1

    return isa_count.most_common()


@app.route("/api/1/items")
def api_wikidata_items():
    bounds = request.args.get("bounds")
    t0 = time()
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
        label = item.label() if item else "[missing]"
        isa = {
            "qid": qid,
            "count": count,
            "label": label,
        }
        isa_count.append(isa)

    t1 = time() - t0
    print(f"wikidata: {t1} seconds")

    return jsonify(success=True, items=items, isa_count=isa_count, duration=t1)


@app.route("/api/1/osm")
def api_osm_objects():
    bounds = request.args.get("bounds")
    t0 = time()
    objects = get_osm_with_wikidata_tag(bounds)
    t1 = time() - t0
    print(f"OSM: {t1} seconds")
    return jsonify(success=True, objects=objects, duration=t1)


@app.route("/api/1/item/Q<int:item_id>")
def api_item_detail(item_id):
    qid = f"Q{item_id}"
    tagged = get_tagged_qid(qid)
    return jsonify(qid=qid, tagged=bool(tagged), info=tagged)


@app.route("/api/1/search")
def api_search():
    q = request.args["q"]
    hits = nominatim.lookup(q)
    for hit in hits:
        if "geotext" in hit:
            del hit["geotext"]
        hit["name"] = nominatim.get_hit_name(hit)

    return jsonify(hits=hits)


if __name__ == "__main__":
    app.run(host="0.0.0.0")
