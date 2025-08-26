import os
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

# 🔹 Ruta al client_secret.json que descargaste
CLIENT_SECRET = r"C:\Projects\Bias\chatbot_agent_fwk\zChatbotAgentFwk\config\client_secret_186464463107-ga6pk2655frmkql18o9rih98uvfh7am9.apps.googleusercontent.com.json"

# 🔹 Archivo donde se guardará el token la primera vez (se crea solo)
TOKEN_FILE    = r"/config/token.json"

# 🔹 Permiso solo para subir archivos
SCOPES = ["https://www.googleapis.com/auth/drive.file"]

# 🔹 ID de la carpeta "document_upload" en tu Drive
FOLDER_ID = "1hJOsSgUqdtSKs2DtEg7rMAN9yhNWMqVE"

# 🔹 Archivo a subir
FILE_PATH = r"../../exports/caba_venta_ALLPORTALS_20250826_1339.txt"

def get_creds():
    creds = None
    if os.path.exists(TOKEN_FILE):
        creds = Credentials.from_authorized_user_file(TOKEN_FILE, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CLIENT_SECRET, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(TOKEN_FILE, "w", encoding="utf-8") as f:
            f.write(creds.to_json())
    return creds

creds = get_creds()
drive = build("drive", "v3", credentials=creds)

media = MediaFileUpload(FILE_PATH, resumable=True)
meta = {"name": os.path.basename(FILE_PATH), "parents": [FOLDER_ID]}
f = drive.files().create(body=meta, media_body=media, fields="id,webViewLink").execute()

print("✅ Subido:", f["webViewLink"])
