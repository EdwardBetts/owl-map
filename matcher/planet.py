from sqlalchemy import Table, Column, Integer, String, Float, MetaData
from sqlalchemy.dialects import postgresql
from geoalchemy2 import Geometry

metadata = MetaData()

point = Table("planet_osm_point", metadata,
    Column("osm_id", Integer),
    Column("name", String),
    Column("tags", postgresql.HSTORE),
    Column("way", Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False),
)

line = Table("planet_osm_line", metadata,
    Column("osm_id", Integer),
    Column("name", String),
    Column("tags", postgresql.HSTORE),
    Column("way", Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False),
)

polygon = Table("planet_osm_polygon", metadata,
    Column("osm_id", Integer),
    Column("name", String),
    Column("tags", postgresql.HSTORE),
    Column("way", Geometry("GEOMETRY", srid=4326, spatial_index=True), nullable=False),
    Column("way_area", Float),
)
