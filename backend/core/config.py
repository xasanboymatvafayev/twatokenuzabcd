from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    DATABASE_URL: str = "postgresql+asyncpg://casino:casino123@localhost/casino_db"
    SECRET_KEY: str = "your-super-secret-key-change-this-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 10080  # 7 days
    
    BOT_TOKEN: str = "YOUR_BOT_TOKEN_HERE"

    
    HOUSE_EDGE: float = 0.05  # 5% house edge
    
    @property
    def ADMIN_IDS(self) -> list:
        raw = os.getenv("ADMIN_IDS", "")
        return [int(x.strip()) for x in raw.split(",") if x.strip()]
    
    class Config:
        env_file = ".env"

settings = Settings()
