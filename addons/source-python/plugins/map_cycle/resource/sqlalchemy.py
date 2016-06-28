from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

from .config import config
from .paths import MC_DATA_PATH


engine = create_engine(config['database']['uri'].format(
    mc_data_path=MC_DATA_PATH,
))
Base = declarative_base()
Session = sessionmaker(bind=engine)
