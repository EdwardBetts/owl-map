import json
import re
import typing
from collections import defaultdict
from typing import Any

from flask_login import UserMixin
from geoalchemy2 import Geometry
from sqlalchemy import func
from sqlalchemy.dialects import postgresql
from sqlalchemy.ext.associationproxy import association_proxy
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy.ext.hybrid import hybrid_property
from sqlalchemy.orm import backref, column_property, deferred, registry, relationship
from sqlalchemy.orm.collections import attribute_mapped_collection
from sqlalchemy.orm.decl_api import DeclarativeMeta
from sqlalchemy.schema import Column, ForeignKey
from sqlalchemy.sql.expression import cast
from sqlalchemy.types import BigInteger, Boolean, DateTime, Float, Integer, String, Text

from . import mail, utils, wikidata
from .database import now_utc, session

mapper_registry = registry()


class Base(metaclass=DeclarativeMeta):
    __abstract__ = True

    registry = mapper_registry
    metadata = mapper_registry.metadata
    query = session.query_property()

    __init__ = mapper_registry.constructor


re_point = re.compile(r"^POINT\((.+) (.+)\)$")

osm_type_enum = postgresql.ENUM(
    "node", "way", "relation", name="osm_type_enum", metadata=Base.metadata
)

re_lau_code = re.compile(r"^[A-Z]{2}([^A-Z].+)$")  # 'LAU (local administrative unit)'

property_map = [
    ("P238", ["iata"], "IATA airport code"),
    ("P239", ["icao"], "ICAO airport code"),
    ("P240", ["faa", "ref"], "FAA airport code"),
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

T = typing.TypeVar("T", bound="Item")


class Item(Base):
    """Wikidata item."""

    __tablename__ = "item"
    item_id = Column(Integer, primary_key=True, autoincrement=False)
    labels = Column(postgresql.JSONB)
    descriptions = Column(postgresql.JSONB)
    aliases = Column(postgresql.JSONB)
    sitelinks = Column(postgresql.JSONB)
    claims = Column(postgresql.JSONB, nullable=False)
    lastrevid = Column(Integer, nullable=False, unique=True)
    locations = relationship(
        "ItemLocation", cascade="all, delete-orphan", backref="item"
    )
    qid = column_property("Q" + cast(item_id, String))

    wiki_extracts = relationship(
        "Extract",
        collection_class=attribute_mapped_collection("site"),
        cascade="save-update, merge, delete, delete-orphan",
        backref="item",
    )
    extracts = association_proxy("wiki_extracts", "extract")

    @classmethod
    def get_by_qid(cls: typing.Type[T], qid: str) -> T | None:
        if qid and len(qid) > 1 and qid[0].upper() == "Q" and qid[1:].isdigit():
            obj: T = cls.query.get(qid[1:])
            return obj
        return None

    @property
    def wd_url(self) -> str:
        """Wikidata URL for item."""
        return f"https://www.wikidata.org/wiki/{self.qid}"

    def get_claim(self, pid: str) -> list[str | int | dict[str, str | int] | None]:
        """List of claims for given Wikidata property ID."""
        claims = typing.cast(wikidata.Claims, self.claims)
        return [
            i["mainsnak"]["datavalue"]["value"]
            if "datavalue" in i["mainsnak"]
            else None
            for i in claims.get(pid, [])
        ]

    def label(self, lang: str = "en") -> str:
        """Label for this Wikidata item."""
        labels = typing.cast(dict[str, dict[str, Any]], self.labels)
        if lang in labels:
            return typing.cast(str, labels[lang]["value"])
        elif "en" in labels:
            return typing.cast(str, labels["en"]["value"])

        label_list = list(labels.values())
        return typing.cast(str, label_list[0]["value"]) if label_list else "[no label]"

    def description(self, lang: str = "en") -> str | None:
        """Return a description of the item."""
        descriptions = typing.cast(dict[str, dict[str, Any]], self.descriptions)
        if lang in descriptions:
            return typing.cast(str, descriptions[lang]["value"])
        elif "en" in descriptions:
            return typing.cast(str, descriptions["en"]["value"])
        return None

        d_list = list(self.descriptions.values())
        if d_list:
            return d_list[0]["value"]

    def get_aliases(self, lang="en"):
        if lang not in self.aliases:
            if "en" not in self.aliases:
                return []
            lang = "en"
        return [a["value"] for a in self.aliases[lang]]

    def get_part_of_names(self):
        if not self.claims:
            return set()

        part_of_names = set()
        for p361 in self.claims.get("P361", []):
            try:
                part_of_id = p361["mainsnak"]["datavalue"]["value"]["numeric-id"]
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
        keys = ["labels", "aliases", "descriptions", "sitelinks", "claims"]
        return {key: getattr(self, key) for key in keys}

    def names(self, check_part_of=True):
        part_of_names = self.get_part_of_names() if check_part_of else set()

        d = wikidata.names_from_entity(self.entity) or defaultdict(list)

        for name, sources in list(d.items()):
            if len(sources) == 1 and sources[0][0] == "image":
                continue
            for part_of_name in part_of_names:
                if not name.startswith(part_of_name):
                    continue
                prefix_removed = name[len(part_of_name) :].strip()
                if prefix_removed not in d:
                    d[prefix_removed] = sources

        if self.claims:
            for p6375 in self.claims.get("P6375", []):
                try:
                    street_address = p6375["mainsnak"]["datavalue"]["value"]
                except KeyError:
                    continue
                d[street_address["text"]].append(
                    ("P6375", street_address.get("language"))
                )

        # A terrace of buildings can be illustrated with a photo of a single building.
        # We try to determine if this is the case and avoid using the filename of the
        # single building photo as a name for matching.

        def has_digit(s):
            return any(c.isdigit() for c in s)

        image_names = {
            name
            for name, sources in d.items()
            if len(sources) == 1 and sources[0][0] == "image" and has_digit(name)
        }
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

    def get_isa(self) -> list[dict[str, int | str]]:
        """Get item IDs of IsA items for this item."""
        isa_list = []
        of_property = "P642"
        claims = typing.cast(wikidata.Claims, self.claims)
        for claim in claims.get("P31", []):
            qualifiers = claim.get("qualifiers", {})
            if "datavalue" in claim["mainsnak"]:
                isa_list.append(claim["mainsnak"]["datavalue"]["value"])
            for of_qualifier in qualifiers.get(of_property, []):
                if "datavalue" in of_qualifier:
                    isa_list.append(of_qualifier["datavalue"]["value"])
        return isa_list

    def get_isa_qids(self):
        return [isa["id"] for isa in self.get_isa()]

    def is_street(self, isa_qids=None):
        if isa_qids is None:
            isa_qids = self.get_isa_qids()

        matching_types = {
            "Q12731",  # dead end street
            "Q34442",  # road
            "Q79007",  # street
            "Q83620",  # thoroughfare
            "Q21000333",  # shopping street
            "Q62685721",  # pedestrian street
        }
        return bool(matching_types & set(isa_qids))

    def is_watercourse(self, isa_qids=None):
        if isa_qids is None:
            isa_qids = self.get_isa_qids()
        matching_types = {
            "Q355304",  # watercourse
            "Q4022",  # river
            "Q47521",  # stream
            "Q1437299",  # creek
            "Q63565252",  # brook
            "Q12284",  # canal
            "Q55659167",  # natural watercourse
        }
        return bool(matching_types & set(isa_qids))

    def is_linear_feature(self):
        isa_qids = set(self.get_isa_qids())
        return self.is_street(isa_qids) or self.is_watercourse(isa_qids)

    def is_tram_stop(self):
        return "Q2175765" in self.get_isa_qids()

    def alert_admin_about_bad_time(self, v):
        body = (
            "Wikidata item has an unsupported time precision\n\n"
            + self.wd_url
            + "\n\n"
            + "Value:\n\n"
            + json.dumps(v, indent=2)
        )
        mail.send_mail(f"OWL Map: bad time value in {self.qid}", body)

    def time_claim(self, pid):
        ret = []
        for v in self.get_claim(pid):
            if not v:
                continue
            try:
                t = utils.format_wikibase_time(v)
            except Exception:
                self.alert_admin_about_bad_time(v)
                raise

            if t:
                ret.append(t)
            else:
                self.alert_admin_about_bad_time(v)

        return ret

    def closed(self):
        return self.time_claim("P3999")

    def first_paragraph_language(self, lang):
        if lang not in self.sitelinks():
            return
        extract = self.extracts.get(lang)
        if not extract:
            return

        empty_list = [
            "<p><span></span></p>",
            "<p><span></span>\n</p>",
            "<p><span></span>\n\n</p>",
            "<p>\n<span></span>\n</p>",
            "<p>\n\n<span></span>\n</p>",
            "<p>.\n</p>",
            "<p><br></p>",
            '<p class="mw-empty-elt">\n</p>',
            '<p class="mw-empty-elt">\n\n</p>',
            '<p class="mw-empty-elt">\n\n\n</p>',
        ]

        text = extract.strip()
        while True:
            found_empty = False
            for empty in empty_list:
                if text.startswith(empty):
                    text = text[len(empty) :].strip()
                    found_empty = True
            if not found_empty:
                break

        close_tag = "</p>"
        first_end_p_tag = text.find(close_tag)
        if first_end_p_tag == -1:
            # FIXME: e-mail admin
            return text

        return text[: first_end_p_tag + len(close_tag)]

    def get_identifiers_tags(self):
        tags = defaultdict(list)
        for claim, osm_keys, label in property_map:
            values = [
                i["mainsnak"]["datavalue"]["value"]
                for i in self.claims.get(claim, [])
                if "datavalue" in i["mainsnak"]
            ]
            if not values:
                continue
            if claim == "P782":
                values += [
                    m.group(1) for m in (re_lau_code.match(v) for v in values) if m
                ]
            for osm_key in osm_keys:
                tags[osm_key].append((values, label))
        return dict(tags)

    def get_identifiers(self):
        ret = {}
        for claim, osm_keys, label in property_map:
            values = [
                i["mainsnak"]["datavalue"]["value"]
                for i in self.claims.get(claim, [])
                if "datavalue" in i["mainsnak"]
            ]
            if not values:
                continue
            if claim == "P782":
                values += [
                    m.group(1) for m in (re_lau_code.match(v) for v in values) if m
                ]
            for osm_key in osm_keys:
                ret[label] = values
        return ret


# class Claim(Base):
#     __tablename__ = "claim"
#     item_id = Column(Integer, primary_key=True)
#     property_id = Column(Integer, primary_key=True)
#     position = Column(Integer, primary_key=True)
#     mainsnak = Column(postgresql.JSONB)


class ItemIsA(Base):
    __tablename__ = "item_isa"
    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    isa_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)

    item = relationship("Item", foreign_keys=[item_id])
    isa = relationship("Item", foreign_keys=[isa_id])


class ItemLocation(Base):
    __tablename__ = "item_location"
    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    property_id = Column(Integer, primary_key=True)
    statement_order = Column(Integer, primary_key=True)
    location = Column(Geometry("POINT", srid=4326, spatial_index=True), nullable=False)

    qid = column_property("Q" + cast(item_id, String))
    pid = column_property("P" + cast(item_id, String))

    def get_lat_lon(self) -> tuple[float, float]:
        """Get latitude and longitude of item."""
        loc: tuple[float, float]
        loc = session.query(func.ST_Y(self.location), func.ST_X(self.location)).one()
        return loc


def location_objects(
    coords_dict: dict[str, list[wikidata.Coords]]
) -> list[ItemLocation]:
    """Create location objects with the given coordinates."""
    locations: list[ItemLocation] = []
    for pid, coord_list in coords_dict.items():
        for num, coords in enumerate(coord_list):
            point = f"POINT({coords['longitude']} {coords['latitude']})"
            loc: ItemLocation = ItemLocation(
                property_id=int(pid[1:]), statement_order=num, location=point
            )
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
            func.ST_AsGeoJSON(cls.way, maxdecimaldigits=6), deferred=True
        )

    @declared_attr
    def as_EWKT(cls):
        return column_property(func.ST_AsEWKT(cls.way), deferred=True)

    @hybrid_property
    def has_street_address(self):
        return "addr:housenumber" in self.tags and "addr:street" in self.tags

    def display_name(self):
        for key in "bridge:name", "tunnel:name", "lock_name":
            if key in self.tags:
                return self.tags[key]

        return (
            self.name or self.tags.get("addr:housename") or self.tags.get("inscription")
        )

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
        src_id = osm_id * {"way": 1, "relation": -1}[osm_type]
        return cls.query.get(src_id)


class Polygon(MapMixin, Base):
    way_area = Column(Float)

    @classmethod
    def get_osm(cls, osm_type, osm_id):
        src_id = osm_id * {"way": 1, "relation": -1}[osm_type]
        return cls.query.get(src_id)

    @property
    def type(self) -> str:
        """Polygon is either a way or a relation."""
        return "way" if self.src_id > 0 else "relation"

    @declared_attr
    def area(cls):
        return column_property(func.ST_Area(cls.way, False), deferred=True)

    @hybrid_property
    def area_in_sq_km(self) -> float:
        """Size of area in square km."""
        return self.area / (1000 * 1000)


class User(Base, UserMixin):
    """User."""

    __tablename__ = "user"
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

    def is_active(self) -> bool:
        """User is active."""
        return self.active


class EditSession(Base):
    __tablename__ = "edit_session"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id))
    created = Column(DateTime, default=now_utc(), nullable=False)
    edit_list = Column(postgresql.JSONB)
    comment = Column(String)

    user = relationship("User")
    changeset = relationship("Changeset", back_populates="edit_session", uselist=False)


class Changeset(Base):
    """An OSM Changeset generated by this tool."""

    __tablename__ = "changeset"
    id = Column(BigInteger, primary_key=True)
    created = Column(DateTime)
    comment = Column(String)
    user_id = Column(Integer, ForeignKey(User.id))
    update_count = Column(Integer, nullable=False)
    edit_session_id = Column(Integer, ForeignKey(EditSession.id))

    user = relationship(
        "User",
        backref=backref(
            "changesets", lazy="dynamic", order_by="Changeset.created.desc()"
        ),
    )

    edit_session = relationship("EditSession", back_populates="changeset")


class ChangesetEdit(Base):
    """Record details of edits within a changeset."""

    __tablename__ = "changeset_edit"

    changeset_id = Column(BigInteger, ForeignKey("changeset.id"), primary_key=True)
    item_id = Column(Integer, primary_key=True)
    osm_id = Column(BigInteger, primary_key=True)
    osm_type = Column(osm_type_enum, primary_key=True)
    saved = Column(DateTime, default=now_utc(), nullable=False)

    changeset = relationship("Changeset", backref=backref("edits", lazy="dynamic"))


class SkipIsA(Base):
    """Ignore this item type when walking the Wikidata subclass graph."""

    __tablename__ = "skip_isa"
    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    qid = column_property("Q" + cast(item_id, String))

    item = relationship("Item")


class ItemExtraKeys(Base):
    """Extra tag or key to consider for an Wikidata item type."""

    __tablename__ = "item_extra_keys"
    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    tag_or_key = Column(String, primary_key=True)
    note = Column(String)
    qid = column_property("Q" + cast(item_id, String))

    item = relationship("Item")


class Extract(Base):
    """First paragraph from Wikipedia."""

    __tablename__ = "extract"

    item_id = Column(Integer, ForeignKey("item.item_id"), primary_key=True)
    site = Column(String, primary_key=True)
    extract = Column(String, nullable=False)

    def __init__(self, site: str, extract: str):
        """Initialise the object."""
        self.site = site
        self.extract = extract
