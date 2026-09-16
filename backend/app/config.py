from pathlib import Path
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

# Make local .env credentials available to Boto3 as well as application settings.
load_dotenv(".env", override=False)

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', extra='ignore')
    database_url: str = 'postgresql://demobank:demobank@localhost:5432/demobank'
    ai_mode: Literal['demo', 'bedrock'] = 'demo'
    aws_region: str = 'us-east-1'
    bedrock_model_id: str = ''
    embedding_model_id: str = 'amazon.titan-embed-text-v2:0'
    documents_dir: Path = Path(__file__).resolve().parents[1] / 'documents'

settings = Settings()
