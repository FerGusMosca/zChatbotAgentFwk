import os
from pathlib import Path
import pytest
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# ⚙️ Relative paths from repo root
REPO_ROOT = Path(__file__).resolve().parents[1]
CONFIG_DIR = REPO_ROOT / "config"
EXPORTS_DIR = REPO_ROOT / "exports"

CLIENT_SECRET = CONFIG_DIR / "client_secret_new.json"
TOKEN_FILE = CONFIG_DIR / "token.json"
FILE_PATH = EXPORTS_DIR / "upload_test_file.txt"

# 🔹 Google Drive scope (upload only)
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# 🔹 Target Drive folder ID
FOLDER_ID = "1hJOsSgUqdtSKs2DtEg7rMAN9yhNWMqVE"


def check_path(path: Path, desc: str):
    """Utility to check paths and log nicely"""
    if not path.exists():
        raise FileNotFoundError(f"❌ {desc} not found: {path}")
    print(f"✅ Found {desc}: {path}")
    return path


def get_creds():
    creds = None

    # Ensure client_secret exists
    check_path(CLIENT_SECRET, "Google client_secret.json")

    if TOKEN_FILE.exists():
        print(f"🔑 Using existing token: {TOKEN_FILE}")
        creds = Credentials.from_authorized_user_file(str(TOKEN_FILE), SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            print("♻️ Refreshing expired token...")
            creds.refresh(Request())
        else:
            print("🌐 Starting OAuth flow...")
            flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES)
            creds = flow.run_local_server(port=0)

        # Save token for next runs
        TOKEN_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
        print(f"💾 Saved new token to: {TOKEN_FILE}")

    return creds


@pytest.mark.drive
def test_drive_upload():
    """Test uploading a file to Google Drive"""
    creds = get_creds()
    drive = build("drive", "v3", credentials=creds)

    # Ensure the file exists before trying upload
    check_path(FILE_PATH, "File to upload")

    media = MediaFileUpload(str(FILE_PATH), resumable=True)
    meta = {"name": FILE_PATH.name, "parents": [FOLDER_ID]}

    print(f"📤 Uploading {FILE_PATH.name} to Drive folder {FOLDER_ID} ...")
    f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()

    assert "id" in f
    assert "webViewLink" in f
    print("✅ Upload complete:", f["webViewLink"])
