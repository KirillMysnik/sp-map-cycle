from sqlalchemy import Boolean, Column, Float, Integer, String

from ..resource.config import config
from ..resource.sqlalchemy import Base


class ServerMap(Base):
    __tablename__ = config['database']['prefix'] + "server_maps"

    id = Column(Integer, primary_key=True)
    filename = Column(String(64))
    detected = Column(Integer)
    force_old = Column(Boolean)
    likes = Column(Integer)
    dislikes = Column(Integer)
    man_hours = Column(Float)
    av_session_len = Column(Float)
