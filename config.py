from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    mongo_uri: str
    mongo_db_name: str = "gems"

    class Config:
        env_file = ".env"

settings = Settings()