from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import ForeignKey, Column
from sqlalchemy.orm import relationship, column_property, deferred, backref
from sqlalchemy import func
from sqlalchemy.types import Integer, String, Float, Boolean, DateTime, Text, BigInteger
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.expression import cast
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.declarative import declared_attr
from geoalchemy2 import Geometry
from collections import defaultdict
from flask_login import UserMixin
from .database import session, now_utc
from . import wikidata, utils
import json
import re

Base = declarative_base()
Base.query = session.query_property()

re_point = re.compile(r'^POINT\((.+) (.+)\)$')

osm_type_enum = postgresql.ENUM('node', 'way', 'relation',
                                name='osm_type_enum',
                                metadata=Base.metadata)

class Item(Base):
    __tablename__ = "item"
    item_id = Column(Integer, primary_key=True, autoincrement=False)
    labels = Column(postgresql.JSONB)
    descriptions = Column(postgresql.JSONB)
    aliases = Column(postgresql.JSONB)
    sitelinks = Column(postgresql.JSONB)
    claims = Column(postgresql.JSONB)
    lastrevid = Column(Integer, nullable=False, unique=True)
    locations = relationship("ItemLocation", cascade="all, delete-orphan", backref="item")
    qid = column_property("Q" + cast(item_id, String))

    @classmethod
    def get_by_qid(cls, qid):
        if qid and len(qid) > 1 and qid[0].upper() == "Q" and qid[1:].isdigit():
            return cls.query.get(qid[1:])

    @property
    def wd_url(self):
        return f"https://www.wikidata.org/wiki/{self.qid}"

    def get_claim(self, pid):
        return [i["mainsnak"]["datavalue"]["value"] if "datavalue" in i["mainsnak"] else None
                for i in self.claims.get(pid, [])]

    def label(self, lang='en'):
        if lang in self.labels:
            return self.labels[lang]['value']
        elif 'en' in self.labels:
            return self.labels['en']['value']

        label_list = list(self.labels.values())
        return label_list[0]['value'] if label_list else '[no label]'

    def description(self, lang='en'):
        if lang in self.descriptions:
            return self.descriptions[lang]['value']
        elif 'en' in self.descriptions:
            return self.descriptions['en']['value']
        return

        d_list = list(self.descriptions.values())
        if d_list:
            return d_list[0]['value']

    def get_aliases(self, lang='en'):
        if lang not in self.aliases:
            if 'en' not in self.aliases:
                return []
            lang = 'en'
        return [a['value'] for a in self.aliases[lang]]

    def get_part_of_names(self):
        if not self.claims:
            return set()

        part_of_names = set()
        for p361 in self.claims.get('P361', []):
            try:
                part_of_id = p361['mainsnak']['datavalue']['value']['numeric-id']
            except KeyError:
                continue
            if part_of_id == self.item_id:
                continue  # avoid loop for 'part of' self-reference
            # TODO: download item if it doesn't exist
            part_of_item = Item.query.get(part_of_id)
            if part_of_item:
                names = part_of_item.names(check_part_of=False)
                if names:
                    part_of_names |= names.keys()
        return part_of_names

    @property
    def entity(self):
        keys = ['labels', 'aliases', 'descriptions', 'sitelinks', 'claims']
        return {key: getattr(self, key) for key in keys}

    def names(self, check_part_of=True):
        part_of_names = self.get_part_of_names() if check_part_of else set()

        d = wikidata.names_from_entity(self.entity) or defaultdict(list)

        for name, sources in list(d.items()):
            if len(sources) == 1 and sources[0][0] == 'image':
                continue
            for part_of_name in part_of_names:
                if not name.startswith(part_of_name):
                    continue
                prefix_removed = name[len(part_of_name):].strip()
                if prefix_removed not in d:
                    d[prefix_removed] = sources

        if self.claims:
            for p6375 in self.claims.get('P6375', []):
                try:
                    street_address = p6375['mainsnak']['datavalue']['value']
                except KeyError:
                    continue
                d[street_address['text']].append(('P6375', street_address.get('language')))

        # A terrace of buildings can be illustrated with a photo of a single building.
        # We try to determine if this is the case and avoid using the filename of the
        # single building photo as a name for matching.

        def has_digit(s):
            return any(c.isdigit() for c in s)

        image_names = {name for name, sources in d.items()
                       if len(sources) == 1 and sources[0][0] == 'image' and has_digit(name)}
        if not image_names:
            return dict(d) or None

        other_names = {n for n in d.keys() if n not in image_names and has_digit(n)}
        for image_name in image_names:
            for other in other_names:
                if not utils.is_in_range(other, image_name):
                    continue
                del d[image_name]
                break

        return dict(d) or None

    def get_isa_qids(self):
        return [v["id"] for v in self.get_claim("P31") if v]

    def is_street(self):
        street_items = {
            'Q34442',  # road
            'Q79007',  # street
            'Q83620',  # thoroughfare
            'Q21000333',  # shopping street
        }
        return bool(street_items & set(self.get_isa_qids()))

    def is_tram_stop(self):
        return 'Q2175765' in self.get_isa_qids()

    def closed(self):
        return [utils.format_wikibase_time(v) for v in self.get_claim("P3999") if v]

# class Claim(Base):
#     __tablename__ = "claim"
#     item_id = Column(Integer, primary_key=True)
#     property_id = Column(Integer, primary_key=True)
#     position = Column(Integer, primary_key=True)
#     mainsnak = Column(postgresql.JSONB)

class ItemIsA(Base):
    __tablename__ = 'item_isa'
    item_id = Column(Integer, ForeignKey('item.item_id'), primary_key=True)
    isa_id = Column(Integer, ForeignKey('item.item_id'), primary_key=True)

    item = relationship('Item', foreign_keys=[item_id])
    isa = relationship('Item', foreign_keys=[isa_id])


class ItemLocation(Base):
    __tablename__ = "item_location"
    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    property_id = Column(Integer, primary_key=True)
    statement_order = Column(Integer, primary_key=True)
    location = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)

    qid = column_property("Q" + cast(item_id, String))
    pid = column_property("P" + cast(item_id, String))

    def get_lat_lon(self):
        return session.query(func.ST_Y(self.location),
                             func.ST_X(self.location)).one()

def location_objects(coords):
    locations = []
    for pid, coord_list in coords.items():
        for num, coords in enumerate(coord_list):
            point = f"POINT({coords['longitude']} {coords['latitude']})"
            loc = ItemLocation(property_id=int(pid[1:]),
                               statement_order=num,
                               location=point)
            locations.append(loc)
    return locations


class MapMixin:
    @declared_attr
    def __tablename__(cls):
        return "planet_osm_" + cls.__name__.lower()

    src_id = Column("osm_id", Integer, primary_key=True, autoincrement=False)
    name = Column(String)
    admin_level = Column(String)
    boundary = Column(String)

    tags = Column(postgresql.HSTORE)

    @declared_attr
    def way(cls):
        return deferred(
            Column(Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False)
        )

    @declared_attr
    def kml(cls):
        return column_property(func.ST_AsKML(cls.way), deferred=True)

    @declared_attr
    def geojson_str(cls):
        return column_property(
            func.ST_AsGeoJSON(cls.way, maxdecimaldigits=6),
            deferred=True
        )

    @declared_attr
    def as_EWKT(cls):
        return column_property(func.ST_AsEWKT(cls.way), deferred=True)

    @hybrid_property
    def has_street_address(self):
        return ("addr:housenumber" in self.tags
                and "addr:street" in self.tags)

    def display_name(self):
        for key in 'bridge:name', 'tunnel:name', 'lock_name':
            if key in self.tags:
                return self.tags[key]

        return (self.name
                or self.tags.get("addr:housename")
                or self.tags.get("inscription"))

    def geojson(self):
        return json.loads(self.geojson_str)

    def get_centroid(self):
        centroid = session.query(func.ST_AsText(func.ST_Centroid(self.way))).scalar()
        lon, lat = re_point.match(centroid).groups()
        return (float(lat), float(lon))

    @classmethod
    def coords_within(cls, lat, lon):
        point = func.ST_SetSRID(func.ST_MakePoint(lon, lat), 4326)
        return cls.query.filter(
            cls.admin_level.isnot(None), func.ST_Within(point, cls.way)
        ).order_by(cls.area)

    @property
    def id(self):
        return abs(self.src_id)  # relations have negative IDs

    @property
    def identifier(self):
        return f"{self.type}/{self.id}"

    @property
    def osm_url(self):
        return f"https://www.openstreetmap.org/{self.type}/{self.id}"


class Point(MapMixin, Base):
    type = "node"


class Line(MapMixin, Base):
    @property
    def type(self):
        return "way" if self.src_id > 0 else "relation"

    @classmethod
    def get_osm(cls, osm_type, osm_id):
        src_id = osm_id * {'way': 1, 'relation': -1}[osm_type]
        return cls.query.get(src_id)


class Polygon(MapMixin, Base):
    way_area = Column(Float)

    @classmethod
    def get_osm(cls, osm_type, osm_id):
        src_id = osm_id * {'way': 1, 'relation': -1}[osm_type]
        return cls.query.get(src_id)

    @property
    def type(self):
        return "way" if self.src_id > 0 else "relation"

    @declared_attr
    def area(cls):
        return column_property(func.ST_Area(cls.way, False), deferred=True)

    @hybrid_property
    def area_in_sq_km(self):
        return self.area / (1000 * 1000)


class User(Base, UserMixin):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True)
    username = Column(String)
    password = Column(String)
    name = Column(String)
    email = Column(String)
    active = Column(Boolean, default=True)
    sign_up = Column(DateTime, default=now_utc())
    is_admin = Column(Boolean, default=False)
    description = Column(Text)
    img = Column(String)  # OSM avatar
    languages = Column(postgresql.ARRAY(String))
    single = Column(String)
    multi = Column(String)
    units = Column(String)
    wikipedia_tag = Column(Boolean, default=False)
    mock_upload = Column(Boolean, default=False)

    osm_id = Column(Integer, index=True)
    osm_account_created = Column(DateTime)
    osm_oauth_token = Column(String)
    osm_oauth_token_secret = Column(String)

    def is_active(self):
        return self.active

class EditSession(Base):
    __tablename__ = 'edit_session'
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id))
    created = Column(DateTime, default=now_utc(), nullable=False)
    edit_list = Column(postgresql.JSONB)
    comment = Column(String)

    user = relationship('User')
    changeset = relationship('Changeset', back_populates='edit_session', uselist=False)


class Changeset(Base):
    __tablename__ = 'changeset'
    id = Column(BigInteger, primary_key=True)
    created = Column(DateTime)
    comment = Column(String)
    user_id = Column(Integer, ForeignKey(User.id))
    update_count = Column(Integer, nullable=False)
    edit_session_id = Column(Integer, ForeignKey(EditSession.id))

    user = relationship('User',
                        backref=backref('changesets',
                                        lazy='dynamic',
                                        order_by='Changeset.created.desc()'))

    edit_session = relationship('EditSession', back_populates='changeset')


class ChangesetEdit(Base):
    __tablename__ = 'changeset_edit'

    changeset_id = Column(BigInteger,
                          ForeignKey('changeset.id'),
                          primary_key=True)
    item_id = Column(Integer, primary_key=True)
    osm_id = Column(BigInteger, primary_key=True)
    osm_type = Column(osm_type_enum, primary_key=True)
    saved = Column(DateTime, default=now_utc(), nullable=False)

    changeset = relationship('Changeset',
                             backref=backref('edits', lazy='dynamic'))

class SkipIsA(Base):
    __tablename__ = 'skip_isa'
    item_id = Column(Integer, ForeignKey('item.item_id'), primary_key=True)

    item = relationship('Item')
