from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase

from backend.rag.config import get_settings

settings = get_settings()

engine = create_engine(settings.database_url)  # Create db engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) # Start db session

class Base(DeclarativeBase):
    pass

# Define the funtion to actually load the db that we will use everytime in the routers files!

def get_db():
    with SessionLocal() as db:
        yield db