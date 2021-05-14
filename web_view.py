#!/usr/bin/python3

from flask import Flask, render_template, request, jsonify, redirect, url_for
from sqlalchemy import func, or_
from sqlalchemy.orm import selectinload
from matcher import nominatim, model, database, commons, wikidata, wikidata_api
from collections import Counter
from time import time
from geoalchemy2 import Geography
import os
import json
import GeoIP

srid = 4326

app = Flask(__name__)
app.debug = True
app.config.from_object('config.default')

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)
entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}

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


def make_envelope(bbox):
    west, south, east, north = [float(i) for i in bbox.split(",")]
    return func.ST_MakeEnvelope(west, south, east, north, srid)


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
            name = osm.name
            if not name:
                if "addr:housename" in osm.tags:
                    name = osm.tags["addr:housename"]
                else:
                    name = "[no label]"

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
        image_filenames = item.get_claim("P18")
        item = {
            "qid": item.qid,
            "label": item.label(),
            "description": item.description(),
            "markers": locations,
            "image_list": image_filenames,
            "street_address": item.get_claim("P6375"),
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


@app.route("/commons/<filename>")
def get_commons_image(filename):
    detail = commons.image_detail([filename], thumbheight=600, thumbwidth=600)
    image = detail[filename]
    return redirect(image["thumburl"])


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


def get_and_save_item(qid):
    entity = wikidata_api.get_entity(qid)
    if entity["id"] != qid:
        print(f'redirect {qid} -> {entity["id"]}')
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
        if not item:
            item = get_and_save_item(qid)

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


edu = ['Tag:amenity=college', 'Tag:amenity=university', 'Tag:amenity=school',
       'Tag:office=educational_institution']
tall = ['Key:height', 'Key:building:levels']

extra_keys = {
    'Q3914': ['Tag:building=school',
              'Tag:building=college',
              'Tag:amenity=college',
              'Tag:office=educational_institution'],  # school
    'Q322563': edu,                             # vocational school
    'Q383092': edu,                             # film school
    'Q1021290': edu,                            # music school
    'Q1244442': edu,                            # school building
    'Q1469420': edu,                            # adult education centre
    'Q2143781': edu,                            # drama school
    'Q2385804': edu,                            # educational institution
    'Q5167149': edu,                            # cooking school
    'Q7894959': edu,                            # University Technical College
    'Q47530379': edu,                           # agricultural college
    'Q11303': tall,                             # skyscraper
    'Q18142': tall,                             # high-rise building
    'Q33673393': tall,                          # multi-storey building
    'Q641226': ['Tag:leisure=stadium'],         # arena
    'Q2301048': ['Tag:aeroway=helipad'],        # special airfield
    'Q622425': ['Tag:amenity=pub',
                'Tag:amenity=music_venue'],     # nightclub
    'Q187456': ['Tag:amenity=pub',
                'Tag:amenity=nightclub'],       # bar
    'Q16917': ['Tag:amenity=clinic',
               'Tag:building=clinic'],          # hospital
    'Q330284': ['Tag:amenity=market'],          # marketplace
    'Q5307737': ['Tag:amenity=pub',
                 'Tag:amenity=bar'],            # drinking establishment
    'Q875157': ['Tag:tourism=resort'],          # resort
    'Q174782': ['Tag:leisure=park',
                'Tag:highway=pedestrian',
                'Tag:foot=yes',
                'Tag:area=yes',
                'Tag:amenity=market',
                'Tag:leisure=common'],          # square
    'Q34627': ['Tag:religion=jewish'],          # synagogue
    'Q16970': ['Tag:religion=christian'],       # church
    'Q32815': ['Tag:religion=islam'],           # mosque
    'Q811979': ['Key:building'],                # architectural structure
    'Q11691': ['Key:building'],                 # stock exchange
    'Q1329623': ['Tag:amenity=arts_centre',     # cultural centre
                 'Tag:amenity=community_centre'],
    'Q856584': ['Tag:amenity=library'],         # library building
    'Q11315': ['Tag:landuse=retail'],           # shopping mall
    'Q39658032': ['Tag:landuse=retail'],        # open air shopping centre
    'Q277760': ['Tag:historic=folly',
                'Tag:historic=city_gate'],      # gatehouse
    'Q180174': ['Tag:historic=folly'],          # folly
    'Q15243209': ['Tag:leisure=park',
                  'Tag:boundary=national_park'],   # historic district
    'Q3010369': ['Tag:historic=monument'],      # opening ceremony
    'Q123705': ['Tag:place=suburb'],            # neighbourhood
    'Q256020': ['Tag:amenity=pub'],             # inn
    'Q41253': ['Tag:amenity=theatre'],          # movie theater
    'Q17350442': ['Tag:amenity=theatre'],       # venue
    'Q156362': ['Tag:amenity=winery'],          # winery
    'Q14092': ['Tag:leisure=fitness_centre',
               'Tag:leisure=sports_centre'],    # gymnasium
    'Q27686': ['Tag:tourism=hostel',            # hotel
               'Tag:tourism=guest_house',
               'Tag:building=hotel'],
    'Q11707': ['Tag:amenity=cafe', 'Tag:amenity=fast_food',
               'Tag:shop=deli', 'Tag:shop=bakery',
               'Key:cuisine'],                  # restaurant
    'Q2360219': ['Tag:amenity=embassy'],        # permanent mission
    'Q27995042': ['Tag:protection_title=Wilderness Area'],  # wilderness area
    'Q838948': ['Tag:historic=memorial',
                'Tag:historic=monument'],       # work of art
    'Q23413': ['Tag:place=locality'],           # castle
    'Q28045079': ['Tag:historic=archaeological_site',
                  'Tag:site_type=fortification',
                  'Tag:embankment=yes'],        # contour fort
    'Q744099': ['Tag:historic=archaeological_site',
                'Tag:site_type=fortification',
                'Tag:embankment=yes'],          # hillfort
    'Q515': ['Tag:border_type=city'],           # city
    'Q1254933': ['Tag:amenity=university'],     # astronomical observatory
    'Q1976594': ['Tag:landuse=industrial'],     # science park
    'Q190928': ['Tag:landuse=industrial'],      # shipyard
    'Q4663385': ['Tag:historic=train_station',  # former railway station
                 'Tag:railway=historic_station'],
    'Q11997323': ['Tag:emergency=lifeboat_station'],  # lifeboat station
    'Q16884952': ['Tag:castle_type=stately',
                  'Tag:building=country_house'],  # country house
    'Q1343246': ['Tag:castle_type=stately',
                 'Tag:building=country_house'],   # English country house
    'Q4919932': ['Tag:castle_type=stately'],    # stately home
    'Q1763828': ['Tag:amenity=community_centre'],  # multi-purpose hall
    'Q3469910': ['Tag:amenity=community_centre'],  # performing arts center
    'Q57660343': ['Tag:amenity=community_centre'],  # performing arts building
    'Q163740': ['Tag:amenity=community_centre',  # nonprofit organization
                'Tag:amenity=social_facility',
                'Key:social_facility'],
    'Q41176': ['Key:building:levels'],          # building
    'Q44494': ['Tag:historic=mill'],            # mill
    'Q56822897': ['Tag:historic=mill'],         # mill building
    'Q2175765': ['Tag:public_transport=stop_area'],  # tram stop
    'Q179700': ['Tag:memorial=statue',          # statue
                'Tag:memorial:type=statue',
                'Tag:historic=memorial'],
    'Q1076486': ['Tag:landuse=recreation_ground'],  # sports venue
    'Q988108': ['Tag:amenity=community_centre',  # club
                'Tag:community_centre=club_home'],
    'Q55004558': ['Tag:service=yard',
                  'Tag:landuse=railway'],       # car barn
    'Q19563580': ['Tag:landuse=railway'],       # rail yard
    'Q134447': ['Tag:generator:source=nuclear'],  # nuclear power plant
    'Q1258086': ['Tag:leisure=park',
                 'Tag:boundary=national_park'],  # National Historic Site
    'Q32350958': ['Tag:leisure=bingo'],         # Bingo hall
    'Q53060': ['Tag:historic=gate',             # gate
               'Tag:tourism=attraction'],
    'Q3947': ['Tag:tourism=hotel',              # house
              'Tag:building=hotel',
              'Tag:tourism=guest_house'],
    'Q847017': ['Tag:leisure=sports_centre'],   # sports club
    'Q820477': ['Tag:landuse=quarry',
                'Tag:gnis:feature_type=Mine'],  # mine
    'Q77115': ['Tag:leisure=sports_centre'],    # community center
    'Q35535': ['Tag:amenity=police'],           # police
    'Q16560': ['Tag:tourism=attraction',        # palace
               'Tag:historic=yes'],
    'Q131734': ['Tag:amenity=pub',              # brewery
                'Tag:industrial=brewery'],
    'Q828909': ['Tag:landuse=commercial',
                'Tag:landuse=industrial',
                'Tag:historic=dockyard'],       # wharf
    'Q10283556': ['Tag:landuse=railway'],       # motive power depot
    'Q18674739': ['Tag:leisure=stadium'],       # event venue
    'Q20672229': ['Tag:historic=archaeological_site'],  # friary
    'Q207694': ['Tag:museum=art'],              # art museum
    'Q22698': ['Tag:leisure=dog_park',
               'Tag:amenity=market',
               'Tag:place=square',
               'Tag:leisure=common'],           # park
    'Q738570': ['Tag:place=suburb'],            # central business district
    'Q1133961': ['Tag:place=suburb'],           # commercial district
    'Q935277': ['Tag:gnis:ftype=Playa',
                'Tag:natural=sand'],            # salt pan
    'Q14253637': ['Tag:gnis:ftype=Playa',
                  'Tag:natural=sand'],          # dry lake
    'Q63099748': ['Tag:tourism=hotel',          # hotel building
                  'Tag:building=hotel',
                  'Tag:tourism=guest_house'],
    'Q2997369': ['Tag:leisure=park',
                 'Tag:highway=pedestrian',
                 'Tag:foot=yes',
                 'Tag:area=yes',
                 'Tag:amenity=market',
                 'Tag:leisure=common'],         # plaza
    'Q130003': ['Tag:landuse=winter_sports',    # ski resort
                'Tag:site=piste',
                'Tag:leisure=resort',
                'Tag:landuse=recreation_ground'],
    'Q4830453': ['Key:office',
                 'Tag:building=office'],        # business
}

skip_isa = {
    13226383,
    16686448,
    2221906,
    2133296,  # space (architecture)
    56052926,  # building division
    15989253,  # part
    9350592,  # telecommunications infrastructure
    121359,  # infrastructure
    28877,  # goods
    2897903,  # goods and services
    2995644,  # result
    733541,  # consequence
    408386,  # inference
    3249551,  # process
    20937557,  # series
    16887380,  # group
    28813620,  # set
    99527517,  # collection entity
    1150070,  # change
    1190554,  # occurrence
    26907166,  # temporal entity
    2425052,  # electrical appliance
    931447,  # electrical load
    210729,  # electrical element
    3749263,  # electrical device
    16798631,  # equipment
    66310125,  # nonbiological component
    22811462,  # type of manufactured good
    21146257,  # type
    16889133,  # class
    1310239,  # component
    337060,  # perceptible object
    581105,  # consumer electronics
    2858615,  # electronic machine
    1183543,  # device
    39546,  # tool
    35825432,  # converter
    11019,  # machine
    8205328,  # artificial physical object
    223557,  # physical object
    35459920,  # three-dimensional object
    488383,  # object
    35120,  # entity
    1454986,  # physical system
    30060700,  # scientific object
    58778,  # system
    6671777,  # structure
    4406616,  # concrete object
    2555640,  # cell (architecture)
    78642244,  # closed space
    1902617,  # verblijfsruimte
    180516,  # room ['Key:room']
    17334923,  # location
    27096213,  # geographic entity
    58416391,  # spatial entity
    58415929,  # spatio-temporal entity
    811979,  # architectural structure
    811430,  # human-made geographic feature
    35145743,  # human-made landform
    27096235,  # artificial geographic entity
    618123,  # geographical feature
    386724,  # work
    15401930,  # product
    102074988,  # artificial physical structure
    15710813,  # physical structure
    1299240,  # interior space
    4830453,  # business
    3563237,  # economic unit
    2198779,  # unit
    7184903,  # abstract object
    43229,  # organization
    16334295,  # group of humans
    16334298,  # group of living things
    61961344,  # group of physical objects
    98119401,  # group or class of physical objects
    106559804,  # person or organization
    24229398,  # agent
    23958946,  # individual entity
    4830453,  # business
    2695280,  # technique
    21162272,  # means
    4026292,  # action
    1914636,  # activity
    372222,  # human-readable medium
    494756,  # data
    42848,  # data
    1166770,  # depiction
    11024,  # communication
    6031064,  # information exchange
    52948,  # interaction
    23009552,  # exchange
    23009675,  # transfer
    22294683,  # biological process involved in intraspecies interaction between organisms
    628858,  # workplace
    1228250,  # line
    211548,  # locus
    36161,  # set
    864377,  # multiset
    246672,  # mathematical object
    5469988,  # formalization
    4393498,  # representation
    930933,  # relation
    217594,  # class
    294440,  # public space
    7551384,  # social space
    83493482,  # thanking
    83492918,  # acknowledgement
    628523,  # message
    11028,  # information
    189970,  # social status
    11424100,  # status
    4897819,  # role
    1207505,  # quality
    937228,  # property
    11862829,  # academic discipline
    1047113,  # specialty
    9081,  # knowledge
    104127086,  # memory
    12488383,  # content
    2434238,  # heritage
    23893363,  # heritage
    82821,  # tradition
    251777,  # custom
    1299714,  # habit
    36529775,  # habit
    7302601,  # recognition
    854429,  # portal
    391414,  # architectural element
    3955017,  # intermediate good
    2424752,  # product
    19603939,  # building component
    55638,  # tertiary sector of the economy
    3958441,  # economic sector
}
skip_tags = {"Key:addr:street"}

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
    isa_items = []
    isa_list = [v["numeric-id"] for v in item.get_claim("P31")]
    isa_items = get_items(isa_list)

    osm_list = set()
    seen = set(isa_list) | skip_isa
    while isa_items:
        isa = isa_items.pop()
        if not isa:
            continue
        osm = [v for v in isa.get_claim("P1282") if v not in skip_tags]
        if isa.qid in extra_keys:
            osm += extra_keys[isa.qid]

        osm_list.update(osm)

        subclass_of = [v["numeric-id"] for v in (isa.get_claim("P279") or []) if v]
        isa_list = [isa_id for isa_id in subclass_of if isa_id not in seen]
        seen.update(isa_list)
        isa_items += get_items(isa_list)
    return sorted(osm_list)


@app.route("/api/1/item/Q<int:item_id>/tags")
def api_get_item_tags(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    osm_list = get_item_tags(item)
    t1 = time() - t0
    return jsonify(success=True, qid=item.qid, tag_or_key_list=osm_list, duration=t1)


def get_tag_filter(cls, tag_list):
    tag_filter = []
    for tag_or_key in tag_list:
        if tag_or_key.startswith("Key:"):
            tag_filter.append(cls.tags.has_key(tag_or_key[4:]))
        if tag_or_key.startswith("Tag:"):
            k, _, v = tag_or_key.partition("=")
            tag_filter.append(cls.tags[k[4:]] == v)

    return tag_filter

def get_nearby(bbox, item, max_distance=200):
    db_bbox = make_envelope(bbox)

    osm_objects = {}
    distances = {}
    tag_list = get_item_tags(item)
    if not tag_list:
        return []

    for loc in item.locations:
        lat, lon = loc.get_lat_lon()
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        for cls in model.Point, model.Line, model.Polygon:
            tag_filter = get_tag_filter(cls, tag_list)
            dist = func.ST_Distance(point, cls.way.cast(Geography(srid=4326)))

            q = (cls.query.add_columns(dist.label('distance'))
                          .filter(
                              func.ST_Intersects(db_bbox, cls.way),
                              func.ST_Area(cls.way) < 20 * func.ST_Area(db_bbox),
                              or_(*tag_filter))
                          .order_by(point.distance_centroid(cls.way))
                          .limit(20))

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

    return nearby[:10]


def get_presets_from_tags(tags):
    preset_dir = app.config["ID_PRESET_DIR"]
    found = []
    for k, v in tags.items():
        filename = os.path.join(preset_dir, k, v + ".json")
        if not os.path.exists(filename):
            filename = os.path.join(preset_dir, k + ".json")
            if not os.path.exists(filename):
                continue
        data = json.load(open(filename))
        name = data["name"]
        found.append(name)

    return found


@app.route("/api/1/item/Q<int:item_id>/candidates")
def api_find_osm_candidates(item_id):
    bounds = request.args.get("bounds")

    t0 = time()
    item = model.Item.query.get(item_id)
    nearby = []
    for osm, dist in get_nearby(bounds, item):
        tags = osm.tags
        name = osm.name or tags.get("addr:housename")
        if not name and "addr:housenumber" in tags and "addr:street" in tags:
            name = tags["addr:housenumber"] + " " + tags["addr:street"]

        cur = {
            "identifier": osm.identifier,
            "distance": dist,
            "name": name,
            "tags": tags,
            "geojson": osm.geojson(),
            "presets": get_presets_from_tags(tags),
        }
        if hasattr(osm, 'area'):
            cur["area"] = osm.area

        nearby.append(cur)

    t1 = time() - t0
    return jsonify(success=True, qid=item.qid, nearby=nearby, duration=t1)


@app.route("/api/1/missing")
def api_missing_wikidata_items():
    qids_arg = request.args.get("qids")
    qids = qids_arg.split(",")
    if not qids or not qids[0]:
        return jsonify(success=True, items=[], isa_count=[])

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

    return jsonify(success=True, items=items, isa_count=isa_count)


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
