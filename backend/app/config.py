from pydantic_settings import BaseSettings, SettingsConfigDict
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    firebase_project_id: str = ""
    firebase_storage_bucket: str = ""
    google_application_credentials: str = ""
    firebase_service_account_json: str = ""
    local_storage_dir: str = ""
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_storage_bucket: str = "assignment-submissions"
    allowed_origins: str = "http://localhost:5173"
    max_upload_bytes: int = 16 * 1024 * 1024
    allow_late_submissions: bool = True
    allow_resubmissions: bool = True
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()
