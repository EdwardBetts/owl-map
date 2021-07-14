#!/usr/bin/python3

from flask import (Flask, render_template, request, jsonify, redirect, url_for, g,
                   flash, session, Response)
from sqlalchemy import func
from matcher import (nominatim, model, database, commons, wikidata, wikidata_api,
                     osm_oauth, edit, mail, api)
from matcher.data import property_map
from time import time, sleep
from requests_oauthlib import OAuth1Session
import flask_login
import json
import GeoIP
import re
import maxminddb

srid = 4326
re_point = re.compile(r'^POINT\((.+) (.+)\)$')

app = Flask(__name__)
app.debug = True
app.config.from_object('config.default')

login_manager = flask_login.LoginManager(app)
login_manager.login_view = 'login_route'
osm_api_base = 'https://api.openstreetmap.org/api/0.6'

maxminddb_reader = maxminddb.open_database(app.config["GEOLITE2"])

DB_URL = "postgresql:///matcher"
database.init_db(DB_URL)
entity_keys = {"labels", "sitelinks", "aliases", "claims", "descriptions", "lastrevid"}

re_qid = re.compile(r'^Q\d+$')


@app.teardown_appcontext
def shutdown_session(exception=None):
    database.session.remove()


@app.before_request
def global_user():
    g.user = flask_login.current_user._get_current_object()

def cors_jsonify(*args, **kwargs):
    response = jsonify(*args, **kwargs)
    response.headers["Access-Control-Allow-Origin"] = "*"
    return response

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


def geoip_user_record():
    gi = GeoIP.open(app.config["GEOIP_DATA"], GeoIP.GEOIP_STANDARD)

    remote_ip = request.get('ip', request.remote_addr)
    return gi.record_by_addr(remote_ip)


def get_user_location():
    remote_ip = request.args.get('ip', request.remote_addr)
    return maxminddb_reader.get(remote_ip)["location"]

    gir = geoip_user_record()
    return (gir["latitude"], gir["longitude"]) if gir else None


@app.route("/")
def redirect_from_root():
    return redirect(url_for("map_start_page"))


@app.route("/index")
def index_page():
    return render_template("index.html")

@app.route("/admin/skip_isa")
def admin_skip_isa_list():
    q = model.Item.query.join(model.SkipIsA).order_by(model.Item.item_id)
    return render_template("admin/skip_isa.html", q=q)


@app.route("/identifier")
def identifier_index():
    return render_template("identifier_index.html", property_map=property_map)


@app.route("/commons/<filename>")
def get_commons_image(filename):
    detail = commons.image_detail([filename], thumbheight=1200, thumbwidth=1200)
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


@app.route("/map")
def map_start_page():
    loc = get_user_location()

    return redirect(url_for(
        'map_location',
        lat=f'{loc["latitude"]:.5f}',
        lon=f'{loc["longitude"]:.5f}',
        zoom=16,
        radius=loc["accuracy_radius"],
        ip=request.args.get('ip'),
    ))


@app.route("/documentation")
def documentation_page():
    user = flask_login.current_user
    username = user.username if user.is_authenticated else None

    return render_template(
        "documentation.html",
        active_tab="documentation",
        username=username
    )


@app.route("/search")
def search_page():
    loc = get_user_location()
    q = request.args.get('q')

    user = flask_login.current_user
    username = user.username if user.is_authenticated else None

    return render_template(
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
def map_location(zoom, lat, lon):
    user = flask_login.current_user
    username = user.username if user.is_authenticated else None

    return render_template(
        "map.html",
        active_tab="map",
        zoom=zoom,
        lat=lat,
        lon=lon,
        radius=request.args.get('radius'),
        username=username,
        mode="map",
        q=None,
    )


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


@app.route("/old_search")
def old_search_page():
    q = request.args.get("q")
    if not q:
        return render_template("search.html", hits=None, bbox_list=None)
    hits = nominatim.lookup(q)
    for hit in hits:
        if "geotext" in hit:
            del hit["geotext"]
    bbox = [hit["boundingbox"] for hit in hits]
    return render_template("search.html", hits=hits, bbox_list=bbox)


def read_bounds_param():
    return [float(i) for i in request.args["bounds"].split(",")]


@app.route("/api/1/location")
def show_user_location():
    return cors_jsonify(get_user_location())


@app.route("/api/1/count")
def api_wikidata_items_count():
    t0 = time()
    count = api.wikidata_items_count(read_bounds_param())

    t1 = time() - t0
    return cors_jsonify(success=True, count=count, duration=t1)


@app.route("/api/1/isa")
def api_wikidata_isa_counts():
    t0 = time()

    bounds = read_bounds_param()
    isa_count = api.wikidata_isa_counts(bounds)

    t1 = time() - t0
    return cors_jsonify(success=True, isa_count=isa_count, bounds=bounds, duration=t1)


@app.route("/api/1/items")
def api_wikidata_items():
    t0 = time()

    bounds = read_bounds_param()
    ret = api.wikidata_items(bounds)

    t1 = time() - t0
    return cors_jsonify(success=True, duration=t1, **ret)


@app.route("/api/1/osm")
def api_osm_objects():
    t0 = time()
    objects = api.get_osm_with_wikidata_tag(read_bounds_param())
    t1 = time() - t0
    return cors_jsonify(success=True, objects=objects, duration=t1)


@app.route("/api/1/item/Q<int:item_id>")
def api_get_item(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    detail = api.item_detail(item)
    t1 = time() - t0

    return cors_jsonify(success=True,
                        duration=t1,
                        **detail)


@app.route("/api/1/item/Q<int:item_id>/tags")
def api_get_item_tags(item_id):
    t0 = time()
    item = model.Item.query.get(item_id)
    tags = api.get_item_tags(item)
    osm_list = sorted(tags.keys())
    t1 = time() - t0

    return cors_jsonify(success=True,
                        qid=item.qid,
                        tag_or_key_list=osm_list,
                        tag_src=tags,
                        duration=t1)


@app.route("/api/1/item/Q<int:item_id>/candidates")
def api_find_osm_candidates(item_id):
    t0 = time()
    bounds = read_bounds_param()
    item = model.Item.query.get(item_id)
    nearby = api.find_osm_candidates(item, bounds)

    t1 = time() - t0
    return cors_jsonify(success=True, qid=item.qid, nearby=nearby, duration=t1)


@app.route("/api/1/missing")
def api_missing_wikidata_items():
    qids_arg = request.args.get("qids")
    if not qids_arg:
        return cors_jsonify(success=False,
                           error="required parameter 'qids' is missing",
                           items=[],
                           isa_count=[])

    qids = []
    for qid in qids_arg.upper().split(","):
        qid = qid.strip()
        m = re_qid.match(qid)
        if not m:
            continue
        qids.append(qid)
    if not qids:
        return jsonify(success=True, items=[], isa_count=[])

    lat, lon = request.args.get("lat"), request.args.get("lon")

    ret = api.missing_wikidata_items(qids, lat, lon)
    return cors_jsonify(success=True, **ret)


@app.route("/api/1/search")
def api_search():
    q = request.args["q"]
    hits = nominatim.lookup(q)
    for hit in hits:
        hit["name"] = nominatim.get_hit_name(hit)
        hit["label"] = nominatim.get_hit_label(hit)
        hit["address"] = list(hit["address"].items())
        hit["identifier"] = f"{hit['osm_type']}/{hit['osm_id']}"

    return cors_jsonify(success=True, hits=hits)

@app.route("/refresh/Q<int:item_id>")
def refresh_item(item_id):
    assert not model.Item.query.get(item_id)

    qid = f'Q{item_id}'
    entity = wikidata_api.get_entity(qid)
    entity_qid = entity.pop("id")
    assert qid == entity_qid

    coords = wikidata.get_entity_coords(entity["claims"])
    assert coords

    obj = {k: v for k, v in entity.items() if k in entity_keys}
    item = model.Item(item_id=item_id, **obj)
    print(item)
    item.locations = model.location_objects(coords)
    database.session.add(item)
    database.session.commit()

    return 'done'

@app.route('/login')
def login_openstreetmap():
    return redirect(url_for('start_oauth',
                            next=request.args.get('next')))

@app.route('/logout')
def logout():
    next_url = request.args.get('next') or url_for('map_start_page')
    flask_login.logout_user()
    flash('you are logged out')
    return redirect(next_url)

@app.route('/done/')
def done():
    flash('login successful')
    return redirect(url_for('map_start_page'))

@app.route('/oauth/start')
def start_oauth():
    next_page = request.args.get('next')
    if next_page:
        session['next'] = next_page

    client_key = app.config['CLIENT_KEY']
    client_secret = app.config['CLIENT_SECRET']

    request_token_url = 'https://www.openstreetmap.org/oauth/request_token'

    callback = url_for('oauth_callback', _external=True)

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          callback_uri=callback)
    fetch_response = oauth.fetch_request_token(request_token_url)

    session['owner_key'] = fetch_response.get('oauth_token')
    session['owner_secret'] = fetch_response.get('oauth_token_secret')

    base_authorization_url = 'https://www.openstreetmap.org/oauth/authorize'
    authorization_url = oauth.authorization_url(base_authorization_url,
                                                oauth_consumer_key=client_key)
    return redirect(authorization_url)

@login_manager.user_loader
def load_user(user_id):
    return model.User.query.get(user_id)

@app.route("/oauth/callback", methods=["GET"])
def oauth_callback():
    client_key = app.config['CLIENT_KEY']
    client_secret = app.config['CLIENT_SECRET']

    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'])

    oauth_response = oauth.parse_authorization_response(request.url)
    verifier = oauth_response.get('oauth_verifier')
    access_token_url = 'https://www.openstreetmap.org/oauth/access_token'
    oauth = OAuth1Session(client_key,
                          client_secret=client_secret,
                          resource_owner_key=session['owner_key'],
                          resource_owner_secret=session['owner_secret'],
                          verifier=verifier)

    oauth_tokens = oauth.fetch_access_token(access_token_url)
    session['owner_key'] = oauth_tokens.get('oauth_token')
    session['owner_secret'] = oauth_tokens.get('oauth_token_secret')

    r = oauth.get(osm_api_base + '/user/details')
    info = osm_oauth.parse_userinfo_call(r.content)

    user = model.User.query.filter_by(osm_id=info['id']).one_or_none()

    if user:
        user.osm_oauth_token = oauth_tokens.get('oauth_token')
        user.osm_oauth_token_secret = oauth_tokens.get('oauth_token_secret')
    else:
        user = model.User(
            username=info['username'],
            description=info['description'],
            img=info['img'],
            osm_id=info['id'],
            osm_account_created=info['account_created'],
        )
        database.session.add(user)
    database.session.commit()
    flask_login.login_user(user)

    next_page = session.get('next') or url_for('map_start_page')
    return redirect(next_page)


def validate_edit_list(edits):
    for e in edits:
        assert model.Item.get_by_qid(e["qid"])
        assert e["op"] in {"add", "remove"}
        osm_type, _, osm_id = e['osm'].partition('/')
        osm_id = int(osm_id)
        if osm_type == 'node':
            assert model.Point.get(osm_id)
        else:
            src_id = osm_id if osm_type == "way" else -osm_id
            assert (model.Line.query.get(src_id)
                    or model.Polygon.query.get(src_id))


@app.route("/api/1/edit", methods=["POST"])
def api_new_edit_session():
    user = flask_login.current_user
    incoming = request.json

    validate_edit_list(incoming["edit_list"])
    es = model.EditSession(user=user,
                           edit_list=incoming['edit_list'],
                           comment=incoming['comment'])
    database.session.add(es)
    database.session.commit()

    session_id = es.id

    return cors_jsonify(success=True, session_id=session_id)

@app.route("/api/1/edit/<int:session_id>", methods=["POST"])
def api_edit_session(session_id):
    es = model.EditSession.query.get(session_id)
    assert flask_login.current_user.id == es.user_id
    incoming = request.json

    for f in 'edit_list', 'comment':
        if f not in incoming:
            continue
        setattr(es, f, incoming[f])
    database.session.commit()

    return cors_jsonify(success=True, session_id=session_id)

@app.route("/api/1/real_save/<int:session_id>")
def api_save_changeset(session_id):
    es = model.EditSession.query.get(session_id)

    def send_message(event, **data):
        data["type"] = event
        return f"data: {json.dumps(data)}\n\n"

    def stream():
        changeset = edit.new_changeset(es.comment)
        r = edit.create_changeset(changeset)
        reply = r.text.strip()

        if reply == "Couldn't authenticate you":
            mail.open_changeset_error(session_id, changeset, r)
            yield send_message("auth-fail", error=reply)
            return

        if not reply.isdigit():
            mail.open_changeset_error(session_id, changeset, r)
            yield send_message("changeset-error", error=reply)
            return

        changeset_id = int(reply)
        yield send_message("open", id=changeset_id)

        update_count = 0

        edit.record_changeset(
            id=changeset_id, comment=es.comment, update_count=update_count
        )

        for e in es.edit_list:
            pass

    return Response(stream(), mimetype='text/event-stream')

@app.route("/api/1/save/<int:session_id>")
def mock_api_save_changeset(session_id):
    es = model.EditSession.query.get(session_id)

    def send(event, **data):
        data["type"] = event
        return f"data: {json.dumps(data)}\n\n"

    def stream(user):
        print('stream')
        changeset_id = database.session.query(func.max(model.Changeset.id) + 1).scalar()
        sleep(1)
        yield send("open", id=changeset_id)
        sleep(1)

        update_count = 0

        print('record_changeset', changeset_id)
        edit.record_changeset(
            id=changeset_id, user=user, comment=es.comment, update_count=update_count
        )

        print('edits')

        for num, e in enumerate(es.edit_list):
            print(num, e)
            yield send("progress", edit=e, num=num)
            sleep(1)
            yield send("saved", edit=e, num=num)
            sleep(1)

        print('closing')
        yield send("closing")
        sleep(1)
        yield send("done")

    return Response(stream(g.user), mimetype='text/event-stream')


if __name__ == "__main__":
    app.run(host="0.0.0.0")
