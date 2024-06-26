#!/usr/bin/python3

"""Views for the web app."""

import inspect
import json
import re
import sys
import traceback
import typing
from time import sleep, time

import flask
import flask_login  # type: ignore
import GeoIP  # type: ignore
import lxml
import maxminddb
import requests
import sqlalchemy
import werkzeug
from requests_oauthlib import OAuth1Session
from sqlalchemy import func
from sqlalchemy.sql.expression import update

from matcher import (
    api,
    commons,
    database,
    edit,
    error_mail,
    mail,
    model,
    nominatim,
    osm_oauth,
    wikidata,
    wikidata_api,
)
from matcher.data import property_map

StrDict = dict[str, typing.Any]

srid = 4326
re_point = re.compile(r"^POINT\((.+) (.+)\)$")

app = flask.Flask(__name__)
app.debug = True
app.config.from_object("config.default")
error_mail.setup_error_mail(app)

login_manager = flask_login.LoginManager(app)
login_manager.login_view = "login_route"
osm_api_base = "https://api.openstreetmap.org/api/0.6"

maxminddb_reader = maxminddb.open_database(app.config["GEOLITE2"])

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)
entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}

re_qid = re.compile(r"^Q\d+$")


@app.teardown_appcontext
def shutdown_session(exception=None) -> None:
    """Shutdown session."""
    database.session.remove()


@app.before_request
def global_user() -> None:
    """Make user object available globally."""
    flask.g.user = flask_login.current_user._get_current_object()


def dict_repr_values(d):
    return {key: repr(value) for key, value in d.items()}


@app.errorhandler(werkzeug.exceptions.InternalServerError)
def exception_handler(
    e: werkzeug.exceptions.InternalServerError,
) -> tuple[str | werkzeug.wrappers.Response, int]:
    """Handle exception."""
    exec_type, exc_value, current_traceback = sys.exc_info()
    assert exc_value
    tb = werkzeug.debug.tbtools.DebugTraceback(exc_value)

    # summary = tb.render_traceback_html(include_title=False)

    last_frame = list(traceback.walk_tb(current_traceback))[-1][0]
    last_frame_args = inspect.getargs(last_frame.f_code)
    if flask.request.path.startswith("/api/"):
        return (
            cors_jsonify(
                {
                    "success": False,
                    "error": tb._te.exc_type.__name__,
                    "traceback": tb.render_traceback_text(),
                    "locals": dict_repr_values(last_frame.f_locals),
                    "last_function": {
                        "name": last_frame.f_code.co_name,
                        "args": repr(last_frame_args),
                    },
                }
            ),
            500,
        )

    return (
        flask.render_template(
            "show_error.html",
            tb=tb,
            last_frame=last_frame,
            last_frame_args=last_frame_args,
        ),
        500,
    )


def cors_jsonify(*args, **kwargs) -> flask.Response:
    """Add CORS header to JSON."""
    response = flask.jsonify(*args, **kwargs)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response


def check_for_tagged_qids(qids: list[str]) -> set[str]:
    """Check OSM for existing wikidata tags for given QIDs."""
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


def geoip_user_record():
    gi = GeoIP.open(app.config["GEOIP_DATA"], GeoIP.GEOIP_STANDARD)

    remote_ip = flask.request.args.get("ip", flask.request.remote_addr)
    return gi.record_by_addr(remote_ip)


def get_user_location() -> StrDict | None:
    """Get user location."""
    remote_ip = flask.request.args.get("ip", flask.request.remote_addr)
    assert remote_ip
    maxmind = maxminddb_reader.get(remote_ip)
    return typing.cast(StrDict, maxmind.get("location")) if maxmind else None


@app.route("/")
def redirect_from_root() -> werkzeug.wrappers.Response:
    """Redirect from root to map start page."""
    return flask.redirect(flask.url_for("map_start_page"))


@app.route("/index")
def index_page() -> str:
    """Index page."""
    return flask.render_template("index.html")


def get_username() -> str | None:
    """Username for current user."""
    user = flask_login.current_user
    return user.username if user.is_authenticated else None


@app.route("/isa/Q<int:item_id>", methods=["GET", "POST"])
def isa_page(item_id: int) -> werkzeug.wrappers.Response | str:
    """Return IsA page."""
    item = api.get_item(item_id)

    if flask.request.method == "POST":
        tag_or_key = flask.request.form["tag_or_key"]
        extra = model.ItemExtraKeys(item=item, tag_or_key=tag_or_key)
        database.session.add(extra)
        database.session.commit()
        flask.flash("extra OSM tag/key added")

        endpoint = flask.request.endpoint
        assert endpoint
        return flask.redirect(flask.url_for(endpoint, item_id=item_id))

    q = model.ItemExtraKeys.query.filter_by(item=item)
    extra = [e.tag_or_key for e in q]
    subclass_property = "P279"

    subclass_list = []
    assert item
    for s in item.get_claim(subclass_property):
        assert isinstance(s, dict)
        subclass_item_id = s["numeric-id"]
        assert subclass_item_id and isinstance(subclass_item_id, int)
        subclass = api.get_item(subclass_item_id)
        assert subclass
        subclass_list.append(
            {
                "qid": s["id"],
                "item_id": subclass_item_id,
                "label": subclass.label(),
                "description": subclass.description(),
                "isa_page_url": flask.url_for("isa_page", item_id=s["numeric-id"]),
            }
        )

    tags = api.get_tags_for_isa_item(item)

    return flask.render_template(
        "isa.html",
        item=item,
        extra=extra,
        subclass_list=subclass_list,
        username=get_username(),
        tags=tags,
    )


@app.route("/admin/skip_isa")
def admin_skip_isa_list():
    q = model.Item.query.join(model.SkipIsA).order_by(model.Item.item_id)
    return flask.render_template("admin/skip_isa.html", q=q)


@app.route("/identifier")
def identifier_index():
    return flask.render_template("identifier_index.html", property_map=property_map)


@app.route("/commons/<filename>")
def get_commons_image(filename):
    detail = commons.image_detail([filename], thumbheight=1200, thumbwidth=1200)
    image = detail[filename]
    return flask.redirect(image["thumburl"])


@app.route("/identifier/<pid>")
def identifier_page(pid):
    per_page = 10
    page = int(flask.request.args.get("page", 1))
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

    return flask.render_template(
        "identifier_page.html",
        pid=pid,
        osm_keys=osm_keys,
        label=label,
        items=items,
        total=total,
        osm_total=osm_total,
        osm_points=osm_points,
    )


@app.route("/map")
def map_start_page() -> werkzeug.wrappers.Response:
    """Map start page."""
    loc = get_user_location()

    if loc:
        lat, lon = loc["latitude"], loc["longitude"]
        radius = loc["accuracy_radius"]
    else:
        lat, lon = 42.2917, -85.5872
        radius = 5

    return flask.redirect(
        flask.url_for(
            "map_location",
            lat=f"{lat:.5f}",
            lon=f"{lon:.5f}",
            zoom=16,
            radius=radius,
            ip=flask.request.args.get("ip"),
        )
    )


@app.route("/documentation")
def documentation_page() -> str:
    """Documentation."""
    user = flask_login.current_user
    username = user.username if user.is_authenticated else None

    return flask.render_template(
        "documentation.html", active_tab="documentation", username=username
    )


@app.route("/search")
def search_page() -> str:
    """Search."""
    loc = get_user_location()
    assert loc
    q = flask.request.args.get("q")

    user = flask_login.current_user
    username = user.username if user.is_authenticated else None

    return flask.render_template(
        "map.html",
        active_tab="map",
        lat=f'{loc["latitude"]:.5f}',
        lon=f'{loc["longitude"]:.5f}',
        zoom=16,
        radius=loc["accuracy_radius"],
        username=username,
        mode="search",
        q=q,
    )


@app.route("/map/<int:zoom>/<float(signed=True):lat>/<float(signed=True):lon>")
def map_location(zoom: int, lat: float, lon: float) -> str:
    """Map location."""
    qid = flask.request.args.get("item")
    isa_param = flask.request.args.get("isa")
    if qid:
        api.get_item(int(qid[1:]))

    isa_list = []
    if isa_param:
        for isa_qid in isa_param.split(";"):
            isa = api.get_item(int(isa_qid[1:]))
            if not isa:
                continue
            cur = {
                "qid": isa.qid,
                "label": isa.label(),
            }
            isa_list.append(cur)

    return flask.render_template(
        "map.html",
        active_tab="map",
        zoom=zoom,
        lat=lat,
        lon=lon,
        radius=flask.request.args.get("radius"),
        username=get_username(),
        mode="map",
        q=None,
        item_type_filter=isa_list,
    )


@app.route("/item/Q<int:item_id>")
def lookup_item(item_id: int):
    """Lookup item."""
    item = api.get_item(item_id)
    if not item:
        # TODO: show nicer page for Wikidata item not found
        return flask.abort(404)

    try:
        lat, lon = item.locations[0].get_lat_lon()
    except IndexError:
        # TODO: show nicer page for Wikidata item without coordinates
        return flask.abort(404)

    return flask.render_template(
        "map.html",
        active_tab="map",
        zoom=16,
        lat=lat,
        lon=lon,
        username=get_username(),
        mode="map",
        q=None,
        qid=item.qid,
        item_type_filter=[],
    )

    url = flask.url_for("map_location", zoom=16, lat=lat, lon=lon, item=item.qid)
    return flask.redirect(url)


@app.route("/search/map")
def search_map_page() -> str:
    """Search map page."""
    user_lat, user_lon = get_user_location() or (None, None)

    q = flask.request.args.get("q")
    if not q:
        return flask.render_template("map.html", user_lat=user_lat, user_lon=user_lon)

    hits = nominatim.lookup(q)
    for hit in hits:
        if "geotext" in hit:
            del hit["geotext"]
    bbox = [hit["boundingbox"] for hit in hits]

    return flask.render_template(
        "search_map.html",
        hits=hits,
        bbox_list=bbox,
        user_lat=user_lat,
        user_lon=user_lon,
    )


def read_bounds_param() -> list[float]:
    """Read bounds parameter."""
    return [float(i) for i in flask.request.args["bounds"].split(",")]


def read_isa_filter_param():
    isa_param = flask.request.args.get("isa")
    if isa_param:
        return set(qid.strip() for qid in isa_param.upper().split(","))


@app.route("/api/1/location")
def show_user_location() -> werkzeug.wrappers.Response:
    """User location."""
    return cors_jsonify(get_user_location())


@app.route("/api/1/count")
def api_wikidata_items_count() -> werkzeug.wrappers.Response:
    t0 = time()
    isa_filter = read_isa_filter_param()
    count = api.wikidata_items_count(read_bounds_param(), isa_filter=isa_filter)

    t1 = time() - t0
    return cors_jsonify(success=True, count=count, duration=t1)


@app.route("/api/1/isa_search")
def api_isa_search():
    t0 = time()
    search_terms = flask.request.args.get("q")
    items = api.isa_incremental_search(search_terms)
    t1 = time() - t0

    return cors_jsonify(success=True, items=items, duration=t1)


@app.route("/api/1/isa")
def api_wikidata_isa_counts():
    t0 = time()

    bounds = read_bounds_param()
    isa_filter = read_isa_filter_param()

    isa_count = api.wikidata_isa_counts(bounds, isa_filter=isa_filter)

    t1 = time() - t0
    return cors_jsonify(success=True, isa_count=isa_count, bounds=bounds, duration=t1)


@app.route("/api/1/items")
def api_wikidata_items():
    t0 = time()

    bounds = read_bounds_param()
    isa_filter = read_isa_filter_param()

    ret = api.wikidata_items(bounds, isa_filter=isa_filter)

    t1 = time() - t0
    return cors_jsonify(success=True, duration=t1, **ret)


@app.route("/api/1/place/<osm_type>/<int:osm_id>")
def api_place_items(osm_type, osm_id):
    t0 = time()

    ret = api.get_place_items(osm_type, osm_id)

    t1 = time() - t0
    return cors_jsonify(success=True, duration=t1, **ret)


@app.route("/api/1/osm")
def api_osm_objects():
    t0 = time()
    isa_filter = read_isa_filter_param()
    objects = api.get_osm_with_wikidata_tag(read_bounds_param(), isa_filter=isa_filter)
    t1 = time() - t0
    return cors_jsonify(success=True, objects=objects, duration=t1)


@app.route("/api/1/item/Q<int:item_id>")
def api_get_item(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    detail = api.item_detail(item)
    t1 = time() - t0

    return cors_jsonify(success=True, duration=t1, **detail)


@app.route("/api/1/item/Q<int:item_id>/tags")
def api_get_item_tags(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    tags = api.get_item_tags(item)
    osm_list = sorted(tags.keys())
    t1 = time() - t0

    return cors_jsonify(
        success=True, qid=item.qid, tag_or_key_list=osm_list, tag_src=tags, duration=t1
    )


def expand_street_name(from_names):
    ret = set(from_names)
    for name in from_names:
        if any(name.startswith(st) for st in ("St ", "St. ")):
            first_space = name.find(" ")
            ret.add("Saint" + name[first_space:])

        if ", " in name:
            for n in set(ret):
                comma = n.find(", ")
                ret.add(name[:comma])
        elif "/" in name:
            for n in set(ret):
                ret.extend(part.strip() for part in n.split("/"))

    ret.update({"The " + name for name in ret if not name.startswith("The ")})
    return ret


@app.route("/api/1/item/Q<int:item_id>/candidates")
def api_find_osm_candidates(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    if not item:
        return cors_jsonify(success=True, qid=f"Q{item_id}", error="item doesn't exist")

    if not item.locations:
        return cors_jsonify(
            success=True, qid=f"Q{item_id}", error="item has no coordinates"
        )

    label = item.label()
    item_is_street = item.is_street()
    item_is_watercourse = item.is_watercourse()

    if item_is_street:
        max_distance = 5_000
        limit = None
        names = expand_street_name([label] + item.get_aliases())
    elif item_is_watercourse:
        max_distance = 20_000
        limit = None
        names = {label}
    else:
        max_distance = 1_000
        limit = 40
        names = None
    nearby = api.find_osm_candidates(
        item, limit=limit, max_distance=max_distance, names=names
    )

    if (item_is_street or item_is_watercourse) and not nearby:
        # nearby = [osm for osm in nearby if street_name_match(label, osm)]

        # try again without name filter
        nearby = api.find_osm_candidates(item, limit=100, max_distance=1_000)

    t1 = time() - t0
    return cors_jsonify(
        success=True,
        qid=item.qid,
        nearby=nearby,
        duration=t1,
        max_distance=max_distance,
    )


@app.route("/api/1/missing")
def api_missing_wikidata_items():
    t0 = time()
    qids_arg = flask.request.args.get("qids")
    if not qids_arg:
        return cors_jsonify(
            success=False,
            error="required parameter 'qids' is missing",
            items=[],
            isa_count=[],
        )

    qids = []
    for qid in qids_arg.upper().split(","):
        qid = qid.strip()
        m = re_qid.match(qid)
        if not m:
            continue
        qids.append(qid)
    if not qids:
        return flask.jsonify(success=True, items=[], isa_count=[])

    lat, lon = flask.request.args.get("lat"), flask.request.args.get("lon")

    ret = api.missing_wikidata_items(qids, lat, lon)
    t1 = time() - t0
    return cors_jsonify(success=True, duration=t1, **ret)


@app.route("/api/1/search")
def api_search():
    q = flask.request.args["q"]
    hits = nominatim.lookup(q)
    for hit in hits:
        hit["name"] = nominatim.get_hit_name(hit)
        hit["label"] = nominatim.get_hit_label(hit)
        hit["address"] = list(hit["address"].items())
        if "osm_type" in hit and "osm_id" in hit:
            hit["identifier"] = f"{hit['osm_type']}/{hit['osm_id']}"
        else:
            print(hit)
            print(q)

    return cors_jsonify(success=True, hits=hits)


@app.route("/api/1/polygon/<osm_type>/<int:osm_id>")
def api_polygon(osm_type, osm_id):
    obj = model.Polygon.get_osm(osm_type, osm_id)
    return cors_jsonify(
        successful=True, osm_type=osm_type, osm_id=osm_id, geojson=obj.geojson()
    )


@app.route("/refresh/Q<int:item_id>")
def refresh_item(item_id: int) -> str:
    """Refresh the local mirror of a Wikidata item."""
    existing = model.Item.query.get(item_id)

    qid = f"Q{item_id}"
    entity = wikidata_api.get_entity(qid)
    entity_qid = entity.pop("id")
    assert qid == entity_qid

    coords = wikidata.get_entity_coords(entity["claims"])

    obj = {k: v for k, v in entity.items() if k in entity_keys}
    if existing:
        for k, v in obj.items():
            setattr(model, k, v)
    else:
        item = model.Item(item_id=item_id, **obj)
        database.session.add(item)

    if coords:
        item.locations = model.location_objects(coords)
    database.session.commit()

    return "done"


@app.route("/login")
def login_openstreetmap() -> flask.Response:
    """Redirect to login."""
    return flask.redirect(
        flask.url_for("start_oauth", next=flask.request.args.get("next"))
    )


@app.route("/logout")
def logout() -> flask.Response:
    """Logout."""
    next_url = flask.request.args.get("next") or flask.url_for("map_start_page")
    flask_login.logout_user()
    flask.flash("you are logged out")
    return flask.redirect(next_url)


@app.route("/done/")
def done():
    flask.flash("login successful")
    return flask.redirect(flask.url_for("map_start_page"))


@app.route("/oauth/start")
def start_oauth():
    """Start OAuth."""
    next_page = flask.request.args.get("next")
    if next_page:
        flask.session["next"] = next_page

    client_key = app.config["CLIENT_KEY"]
    client_secret = app.config["CLIENT_SECRET"]

    request_token_url = "https://www.openstreetmap.org/oauth/request_token"

    callback = flask.url_for("oauth_callback", _external=True)

    oauth = OAuth1Session(
        client_key, client_secret=client_secret, callback_uri=callback
    )
    fetch_response = oauth.fetch_request_token(request_token_url)

    flask.session["owner_key"] = fetch_response.get("oauth_token")
    flask.session["owner_secret"] = fetch_response.get("oauth_token_secret")

    base_authorization_url = "https://www.openstreetmap.org/oauth/authorize"
    authorization_url = oauth.authorization_url(
        base_authorization_url, oauth_consumer_key=client_key
    )
    return flask.redirect(authorization_url)


@login_manager.user_loader
def load_user(user_id) -> model.User:
    """User with the given user_id."""
    return model.User.query.get(user_id)


@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    client_key = app.config["CLIENT_KEY"]
    client_secret = app.config["CLIENT_SECRET"]

    oauth = OAuth1Session(
        client_key,
        client_secret=client_secret,
        resource_owner_key=flask.session["owner_key"],
        resource_owner_secret=flask.session["owner_secret"],
    )

    oauth_response = oauth.parse_authorization_response(flask.request.url)
    verifier = oauth_response.get("oauth_verifier")
    access_token_url = "https://www.openstreetmap.org/oauth/access_token"
    oauth = OAuth1Session(
        client_key,
        client_secret=client_secret,
        resource_owner_key=flask.session["owner_key"],
        resource_owner_secret=flask.session["owner_secret"],
        verifier=verifier,
    )

    oauth_tokens = oauth.fetch_access_token(access_token_url)
    flask.session["owner_key"] = oauth_tokens.get("oauth_token")
    flask.session["owner_secret"] = oauth_tokens.get("oauth_token_secret")

    r = oauth.get(osm_api_base + "/user/details")
    info = osm_oauth.parse_userinfo_call(r.content)

    user = model.User.query.filter_by(osm_id=info["id"]).one_or_none()

    if user:
        user.osm_oauth_token = oauth_tokens.get("oauth_token")
        user.osm_oauth_token_secret = oauth_tokens.get("oauth_token_secret")
    else:
        user = model.User(
            username=info["username"],
            description=info["description"],
            img=info["img"],
            osm_id=info["id"],
            osm_account_created=info["account_created"],
            mock_upload=False,
        )
        database.session.add(user)
    database.session.commit()
    flask_login.login_user(user)

    next_page = flask.session.get("next") or flask.url_for("map_start_page")
    return flask.redirect(next_page)


def validate_edit_list(edits):
    for e in edits:
        assert model.Item.get_by_qid(e["qid"])
        assert e["op"] in {"add", "remove", "change"}
        osm_type, _, osm_id = e["osm"].partition("/")
        osm_id = int(osm_id)
        if osm_type == "node":
            assert model.Point.query.get(osm_id)
        else:
            src_id = osm_id if osm_type == "way" else -osm_id
            assert model.Line.query.get(src_id) or model.Polygon.query.get(src_id)


@app.route("/api/1/edit", methods=["POST"])
def api_new_edit_session():
    user = flask_login.current_user
    incoming = flask.request.json

    validate_edit_list(incoming["edit_list"])
    es = model.EditSession(
        user=user, edit_list=incoming["edit_list"], comment=incoming["comment"]
    )
    database.session.add(es)
    database.session.commit()

    session_id = es.id

    return cors_jsonify(success=True, session_id=session_id)


@app.route("/api/1/edit/<int:session_id>", methods=["POST"])
def api_edit_session(session_id):
    es = model.EditSession.query.get(session_id)
    assert flask_login.current_user.id == es.user_id
    incoming = flask.request.json

    for f in "edit_list", "comment":
        if f not in incoming:
            continue
        setattr(es, f, incoming[f])
    database.session.commit()

    return cors_jsonify(success=True, session_id=session_id)


class VersionMismatch(Exception):
    """Version doesn't match."""


def osm_object(
    osm_type: str, osm_id: int
) -> model.Point | model.Line | model.Polygon | None:
    """Get an OSM object from the database."""
    if osm_type == "node":
        return model.Point.query.get(osm_id)

    src_id = int(osm_id) * {"way": 1, "relation": -1}[osm_type]
    for cls in model.Line, model.Polygon:
        obj = cls.query.get(src_id)
        if obj:
            return obj


def process_edit(changeset_id, e):
    osm_type, _, osm_id = e["osm"].partition("/")
    qid = e["qid"]
    item_id = qid[1:]

    osm = osm_object(osm_type, osm_id)
    assert osm

    r = edit.get_existing(osm_type, osm_id)
    if r.status_code == 410 or r.content == b"":
        return "deleted"

    root = lxml.etree.fromstring(r.content)
    existing = root.find('.//tag[@k="wikidata"]')
    if e["op"] == "add" and existing is not None:
        return "already_added"
    if e["op"] == "remove":
        if existing is None:
            return "already_removed"
        if existing.get("v") != qid:
            return "different_qid"

    root[0].set("changeset", str(changeset_id))
    if e["op"] == "add":
        tag = lxml.etree.Element("tag", k="wikidata", v=qid)
        root[0].append(tag)
    if e["op"] == "remove":
        root[0].remove(existing)
    if e["op"] == "change":
        existing.set("v", qid)

    element_data = lxml.etree.tostring(root)
    try:
        success = edit.save_element(osm_type, osm_id, element_data)
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409 and "Version mismatch" in r.text:
            raise VersionMismatch
        mail.error_mail(
            "error saving element", element_data.decode("utf-8"), e.response
        )
        database.session.commit()
        return "element-error"

    if not success:
        return "element-error"

    new_tags = dict(osm.tags)
    if e["op"] in ("add", "change"):
        new_tags["wikidata"] = qid
    if e["op"] == "remove":
        del new_tags["wikidata"]

    cls = type(osm)
    database.session.execute(
        update(cls).where(cls.src_id == osm.src_id).values(tags=new_tags)
    )

    db_edit = model.ChangesetEdit(
        changeset_id=changeset_id,
        item_id=item_id,
        osm_id=osm_id,
        osm_type=osm_type,
    )
    database.session.add(db_edit)
    database.session.commit()

    return "saved"


@app.route("/api/1/save/<int:session_id>")
def api_save_changeset(session_id: int):
    assert flask.g.user.is_authenticated

    mock = flask.g.user.mock_upload
    api_call = api_mock_save_changeset if mock else api_real_save_changeset
    return api_call(session_id)


@app.route("/sql", methods=["GET", "POST"])
def run_sql() -> str:
    """Web form where the user can run an SQL query."""
    if flask.request.method != "POST":
        return flask.render_template("run_sql.html")

    sql = flask.request.form["sql"]
    conn = database.session.connection()
    result = conn.execute(sqlalchemy.text(sql))

    return flask.render_template("run_sql.html", result=result)


def api_real_save_changeset(session_id):
    es = model.EditSession.query.get(session_id)

    def send(event, **data):
        data["type"] = event
        return f"data: {json.dumps(data)}\n\n"

    def stream(user):
        changeset = edit.new_changeset(es.comment)
        r = edit.create_changeset(changeset)
        reply = r.text.strip()

        if reply == "Couldn't authenticate you":
            mail.open_changeset_error(session_id, changeset, r)
            yield send("auth-fail", error=reply)
            return

        if not reply.isdigit():
            mail.open_changeset_error(session_id, changeset, r)
            yield send("changeset-error", error=reply)
            return

        changeset_id = int(reply)
        yield send("open", id=changeset_id)

        update_count = 0

        change = edit.record_changeset(
            id=changeset_id, user=user, comment=es.comment, update_count=update_count
        )

        # each edit contains these keys:
        # qid: Wikidata item QID
        # osm: OpenStreetMap identifier
        # op: either 'add' or 'remove'

        for num, e in enumerate(es.edit_list):
            print(num, e)
            yield send("progress", edit=e, num=num)
            result = process_edit(changeset_id, e)
            yield send(result, edit=e, num=num)
            if result == "saved":
                update_count += 1
                change.update_count = update_count
            database.session.commit()

        yield send("closing")
        edit.close_changeset(changeset_id)
        yield send("done")

    return flask.Response(
        flask.stream_with_context(stream(flask.g.user)), mimetype="text/event-stream"
    )


def api_mock_save_changeset(session_id):
    es = model.EditSession.query.get(session_id)

    def send(event, **data):
        data["type"] = event
        return f"data: {json.dumps(data)}\n\n"

    def stream(user):
        print("stream")
        changeset_id = database.session.query(func.max(model.Changeset.id) + 1).scalar()
        sleep(1)
        yield send("open", id=changeset_id)
        sleep(1)

        update_count = 0

        print("record_changeset", changeset_id)
        edit.record_changeset(
            id=changeset_id, user=user, comment=es.comment, update_count=update_count
        )

        print("edits")

        for num, e in enumerate(es.edit_list):
            print(num, e)
            yield send("progress", edit=e, num=num)
            sleep(1)
            yield send("saved", edit=e, num=num)
            sleep(1)

        print("closing")
        yield send("closing")
        sleep(1)
        yield send("done")

    return flask.Response(stream(flask.g.user), mimetype="text/event-stream")


if __name__ == "__main__":
    app.run(host="0.0.0.0")
