from sqlalchemy import Boolean, Column, Float, Integer, String

from .config import config
from .orm import Base


class ServerMap(Base):
    __tablename__ = config['database']['prefix'] + "server_maps"

    id = Column(Integer, primary_key=True)
    filename = Column(String(64))
    detected = Column(Integer)
    likes = Column(Integer)
    dislikes = Column(Integer)
    man_hours = Column(Float)
    av_session_len = Column(Float)
