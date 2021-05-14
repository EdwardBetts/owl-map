from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.schema import ForeignKey, Column
from sqlalchemy.orm import relationship, column_property, deferred
from sqlalchemy import func
from sqlalchemy.types import Integer, String, Float
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.expression import cast
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.ext.declarative import declared_attr
from geoalchemy2 import Geography, Geometry
from collections import defaultdict
from .database import session
from . import wikidata, utils
import json
import re

Base = declarative_base()
Base.query = session.query_property()

re_point = re.compile(r'^POINT\((.+) (.+)\)$')

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

    def get_claim(self, pid):
        return [i["mainsnak"]["datavalue"]["value"] if "datavalue" in i["mainsnak"] else None
                for i in self.claims.get(pid, [])]

    def label(self, lang='en'):
        if lang in self.labels:
            return self.labels[lang]['value']
        elif 'en' in self.labels:
            return self.labels['en']['value']
        return list(self.labels.values())[0]['value']

    def description(self, lang='en'):
        if lang in self.descriptions:
            return self.descriptions[lang]['value']
        elif 'en' in self.descriptions:
            return self.descriptions['en']['value']
        return

        d_list = list(self.descriptions.values())
        if d_list:
            return d_list[0]['value']

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


# class Claim(Base):
#     __tablename__ = "claim"
#     item_id = Column(Integer, primary_key=True)
#     property_id = Column(Integer, primary_key=True)
#     position = Column(Integer, primary_key=True)
#     mainsnak = Column(postgresql.JSONBB)

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
    location = Column(Geography("POINT", srid=4326, spatial_index=True), nullable=False)

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
        return column_property(func.ST_AsGeoJSON(cls.way), deferred=True)

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


class Polygon(MapMixin, Base):
    way_area = Column(Float)

    @property
    def type(self):
        return "way" if self.src_id > 0 else "relation"

    @declared_attr
    def area(cls):
        return column_property(func.ST_Area(cls.way, False), deferred=True)

    @hybrid_property
    def area_in_sq_km(self):
        return self.area / (1000 * 1000)