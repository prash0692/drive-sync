"""sync.py: copy new or changed files from Drive A (source) to Drive B (dest).
 
Piece 1: load settings, connect to both accounts, and refuse to run
if either token belongs to the wrong account.
 
Q: How is authorize.py used with sync.py?
A: They never call each other. They're connected only through the token
   files in ~/.drive-sync:
     authorize.py (run by hand, once per account) WRITES token_*.json
     sync.py      (runs every time)                READS  token_*.json
   authorize.py = getting the keys cut. sync.py = using the keys every day.
   Go back to authorize.py only if a token stops working (7-day Testing-mode
   limit, revoked access, or switching account B).
"""

import os
import sys
import io
import re
import json

from datetime import datetime, timezone
from pathlib import Path
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

SECRETS_DIR = Path.home() / ".drive-sync"

# Write one log line as JSON: time, file name, outcome (and a reason if there is one).
# json.dumps escapes line breaks and quotes, so a file name can't fake extra log lines.
def log(outcome, name, reason=""):
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "file": name,
        "outcome": outcome,
    }
    if reason:
        record["reason"] = reason
    print(json.dumps(record), flush=True)

# Read settings from environment variables; stop if any are missing
def load_config():
    config = {
        "source_folder_id": os.environ.get("SOURCE_FOLDER_ID", ""),
        "expected_source": os.environ.get("EXPECTED_SOURCE_EMAIL", ""),
        "expected_dest": os.environ.get("EXPECTED_DEST_EMAIL", ""),
    }
    missing = [name for name, value in config.items() if not value]
    if missing:
        sys.exit(f"Missing settings: {missing}")
    return config


# Load a saved token from ~/.drive-sync and make a Drive API client with it
def connect(account):
    token_file = SECRETS_DIR / f"token_{account}.json"
    creds = Credentials.from_authorized_user_file(str(token_file))
    return build("drive", "v3", credentials=creds)


# Ask Google whose token this client is using
def who_am_i(drive):
    about = drive.about().get(fields="user(emailAddress)").execute()
    return about["user"]["emailAddress"]
# A Drive ID is only letters, digits, - and _. Anything else is rejected
# before it can reach a Drive query.
ID_PATTERN = re.compile(r"^[A-Za-z0-9_-]+$")


# List the files directly inside the source folder (subfolders are not included)
def list_source_files(drive, folder_id):
    if not ID_PATTERN.match(folder_id):
        sys.exit("STOP: SOURCE_FOLDER_ID doesn't look like a Drive folder ID")

    files = []
    page_token = None
    while True:
        response = drive.files().list(
            q=f"'{folder_id}' in parents and trashed = false", 
            #Token A can read the entire Drive, because drive.readonly can’t be limited to a folder. So the query’s '<folder>' in parents is where my code limits itself to one folder: least privilege enforced in code, on top of the scope.
            fields="nextPageToken, files(id, name, mimeType, size, md5Checksum, modifiedTime)",
            pageToken=page_token,
        ).execute()
        files.extend(response.get("files", []))
        page_token = response.get("nextPageToken")
        if not page_token:
            return files

FOLDER_MIME = "application/vnd.google-apps.folder"


# Find the app's own folder in Drive B, or create it the first time.
# drive.file means the app can only see folders it created, so it makes its own.
def get_dest_folder(drive):
    response = drive.files().list(    # search Drive B for a folder with tag role=drive-sync-root
        q="mimeType = 'application/vnd.google-apps.folder' and "
          "appProperties has { key='role' and value='drive-sync-root' } and trashed = false",
        fields="files(id)",           # in the reply, only include each folder's ID
    ).execute()
    found = response.get("files", [])  # list of matching folders; [] if none (no crash)
    if found:
        return found[0]["id"]          # folder exists: return its ID and stop here
    # no folder found: carry on and create one
    folder = drive.files().create(     # create the folder and tag it role=drive-sync-root
        body={"name": "drive-sync copies", "mimeType": FOLDER_MIME,
              "appProperties": {"role": "drive-sync-root"}},
        fields="id",                   # in the reply, only include the new folder's ID
    ).execute()
    print("Created destination folder in Drive B")
    return folder["id"]                # return the new folder's ID


# Look in Drive B for a copy tagged with this source file's ID (None if not copied yet)
def find_copy(drive, source_file_id):
    response = drive.files().list(
        q="appProperties has { key='source_file_id' and value='" + source_file_id + "' } and trashed = false",
        fields="files(id, appProperties)",
    ).execute()
    found = response.get("files", [])
    return found[0] if found else None      


# Download a file's contents into memory (never to disk)
def download(drive, file_id):
    buffer = io.BytesIO()
    downloader = MediaIoBaseDownload(buffer, drive.files().get_media(fileId=file_id))
    done = False
    while not done:   # keep going until the file is complete
        _, done = downloader.next_chunk()  # get the next piece; done = True when finished
    return buffer.getvalue()


# Upload the bytes to Drive B as a new file, tagged with the source file's ID and checksum
def upload_copy(drive, f, data, dest_folder_id):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=f["mimeType"])
    drive.files().create(
        body={
            "name": f["name"],
            "parents": [dest_folder_id],
            "appProperties": {"source_file_id": f["id"], "source_md5": f.get("md5Checksum", "")},
        },
        media_body=media,
        fields="id",
    ).execute()

# Replace an existing copy's contents with the new version, and update its fingerprint tag
def update_copy(drive, copy_id, f, data):
    media = MediaIoBaseUpload(io.BytesIO(data), mimetype=f["mimeType"])
    drive.files().update(
        fileId=copy_id,
        body={"name": f["name"],
              "appProperties": {"source_md5": f.get("md5Checksum", "")}},
        media_body=media,
        fields="id",
    ).execute()

if __name__ == "__main__":
    config = load_config()
    source = connect("source")
    dest = connect("dest")

    # Mismatch guard: refuse to run if a token belongs to the wrong account
    source_email = who_am_i(source)
    dest_email = who_am_i(dest)
    if source_email.lower() != config["expected_source"].lower():
        sys.exit(f"STOP: source token is for {source_email}, expected {config['expected_source']}")
    if dest_email.lower() != config["expected_dest"].lower():
        sys.exit(f"STOP: dest token is for {dest_email}, expected {config['expected_dest']}")

    print("Tokens OK:", source_email, "->", dest_email)

    files = list_source_files(source, config["source_folder_id"])
    print(f"Found {len(files)} files in the source folder:")

    dest_folder_id = get_dest_folder(dest) 

    for f in files:
        if not ID_PATTERN.match(f["id"]):
            log("skipped", f["name"], "unexpected ID format")
            continue
        if f["mimeType"].startswith("application/vnd.google-apps."):
           log("skipped", f["name"], "Google-native type")
           continue

        existing = find_copy(dest, f["id"])
        if existing and existing["appProperties"].get("source_md5") == f.get("md5Checksum", ""):
            log("unchanged", f["name"])
            continue

        data = download(source, f["id"])            # token A: read from Drive A
        if existing:
            update_copy(dest, existing["id"], f, data)
            log("updated", f["name"])
        else:
            upload_copy(dest, f, data, dest_folder_id)
            log("copied", f["name"])