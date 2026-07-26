from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, DeclarativeBase
from dotenv import load_dotenv
from pathlib import Path
import os

# Securely get DATABASE_URL
BASE_DIR = Path(__file__).resolve().parent
env_path = BASE_DIR / "../.env"
load_dotenv(dotenv_path=env_path)  # Load environment variables from .env file
DATABASE_URL = os.getenv("DATABASE_URL")

engine = create_engine(DATABASE_URL)  # Create db engine

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine) # Start db session

class Base(DeclarativeBase):
    pass

# Define the funtion to actually load the db that we will use everytime in the routers files!

def get_db():
    with SessionLocal() as db:
        yield db