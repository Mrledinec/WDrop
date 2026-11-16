"""Authenticated LAN transfer API and receive queue."""

import asyncio
import hashlib
import hmac
import os
import re
import secrets
import shutil
import socket
import threading
import time
from contextlib import closing, suppress
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from sqlite3 import connect
from typing import Literal

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from ..storage.sqlite_manager import SQLiteManager, TransferHistory

API = "/api/v1"
DEFAULT_LIMIT = 2 * 1024**3
OFFER_TIMEOUT = 60
TERMINAL = {"completed", "rejected", "expired", "failed"}
CHUNK_SIZE = 256 * 1024


def local_ipv4():
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
        try:
            sock.connect(("192.0.2.1", 9))
            return sock.getsockname()[0]
        except OSError:
            return "127.0.0.1"


def tls_identity(home):
    home.mkdir(parents=True, exist_ok=True)
    cert_path, key_path = home / "certificate.pem", home / "private-key.pem"
    if not cert_path.exists() or not key_path.exists():
        key = ec.generate_private_key(ec.SECP256R1())
        name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, socket.gethostname())])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(name)
            .issuer_name(name)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1))
            .not_valid_after(now + timedelta(days=3650))
            .sign(key, hashes.SHA256())
        )
        key_path.write_bytes(key.private_bytes(
            serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        ))
        cert_path.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    cert = x509.load_pem_x509_certificate(cert_path.read_bytes())
    return cert_path, key_path, cert.fingerprint(hashes.SHA256()).hex()


def safe_name(name):
    cleaned = re.sub(r'[\x00-\x1f<>:"/\\|?*]', "_", name).strip(" .")
    stem = cleaned.split(".", 1)[0].upper()
    if stem in {"CON", "PRN", "AUX", "NUL"} or re.fullmatch(r"(COM|LPT)[1-9¹²³]", stem):
        cleaned = "_" + cleaned
    return cleaned[:180].rstrip(" .") or "file"


def secret_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


class PairRequest(BaseModel):
    token: str = Field(min_length=6, max_length=100)
    name: str = Field(min_length=1, max_length=80)


class Metadata(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    size: int = Field(ge=0, le=2**63 - 1)
    sha256: str = Field(pattern=r"^[0-9a-f]{64}$")


class Paired(BaseModel):
    id: str
    token: str
    name: str


class TransferStatus(Metadata):
    id: str
    direction: Literal["upload", "download"]
    state: Literal["pending", "accepted", "transferring", "completed", "rejected", "expired", "failed"]
    received: int
    seconds_left: int


class Decision(BaseModel):
    accept: bool


class Receipt(BaseModel):
    success: bool


@dataclass
class Pairing:
    name: str
    created: float = field(default_factory=time.monotonic)
    credentials: dict | None = None
    declined: bool = False


@dataclass
class Offer:
    id: str
    peer_id: str
    direction: str
    metadata: Metadata
    path: Path | None = None
    created: float = field(default_factory=time.monotonic)
    updated: float = field(default_factory=time.monotonic)
    state: str = "pending"
    received: int = 0

    def payload(self):
        return {
            "id": self.id,
            "direction": self.direction,
            **self.metadata.model_dump(),
            "state": self.state,
            "received": self.received,
            "seconds_left": max(0, int(OFFER_TIMEOUT - (time.monotonic() - self.created) + 0.999)),
        }


class TrackedFileResponse(FileResponse):
    def __init__(self, path, on_progress):
        super().__init__(path, media_type="application/octet-stream")
        self.on_progress = on_progress

    async def __call__(self, scope, receive, send):
        sent = 0
        full_response = False

        async def track(message):
            nonlocal sent, full_response
            await send(message)
            if message["type"] == "http.response.start":
                full_response = message["status"] == 200
            elif full_response and message["type"] == "http.response.body":
                sent += len(message.get("body", b""))
                self.on_progress(sent)
            elif full_response and message["type"] == "http.response.pathsend":
                self.on_progress(self.path.stat().st_size)

        await super().__call__(scope, receive, track)


class TransferService:
    def __init__(self, home, inbox, port):
        self.inbox = inbox
        inbox.mkdir(parents=True, exist_ok=True)
        self.cert, self.key, self.pin = tls_identity(home)
        self.name = socket.gethostname()
        self.port = port
        self.db_path = str(home / "connections.db")
        self.history = SQLiteManager(self.db_path)
        self.lock = threading.RLock()
        self.invite_token = None
        self.manual_invite = None
        self.manual_attempts = 0
        self.invite_expires = 0.0
        self.pairing = None
        self.offers = {}
        self.last_seen = {}
        with closing(connect(self.db_path)) as db, db:
            db.execute("""CREATE TABLE IF NOT EXISTS transfer_peers (
                id TEXT PRIMARY KEY, name TEXT NOT NULL, secret TEXT UNIQUE NOT NULL,
                trusted INTEGER NOT NULL DEFAULT 0, alias TEXT
            )""")
            columns = {row[1] for row in db.execute("PRAGMA table_info(transfer_peers)")}
            if "alias" not in columns:
                db.execute("ALTER TABLE transfer_peers ADD COLUMN alias TEXT")
            db.execute("CREATE TABLE IF NOT EXISTS transfer_settings (key TEXT PRIMARY KEY, value INTEGER)")
        self.limit = self.get_limit()

    def get_limit(self):
        with closing(connect(self.db_path)) as db:
            row = db.execute("SELECT value FROM transfer_settings WHERE key='limit'").fetchone()
        return DEFAULT_LIMIT if row is None else row[0]

    def set_limit(self, value):
        with self.lock, closing(connect(self.db_path)) as db, db:
            db.execute("INSERT OR REPLACE INTO transfer_settings VALUES ('limit', ?)", (value,))
            self.limit = value

    def peers(self):
        with closing(connect(self.db_path)) as db:
            return db.execute(
                "SELECT id, COALESCE(alias, name) AS display_name, trusted "
                "FROM transfer_peers ORDER BY display_name, id"
            ).fetchall()

    def rename(self, peer_id, name):
        name = name.strip()
        if not 1 <= len(name) <= 80:
            raise ValueError("Введите имя длиной от 1 до 80 символов")
        with self.lock, closing(connect(self.db_path)) as db, db:
            db.execute("UPDATE transfer_peers SET alias=? WHERE id=?", (name, peer_id))

    def trust(self, peer_id, value):
        with self.lock, closing(connect(self.db_path)) as db, db:
            db.execute("UPDATE transfer_peers SET trusted=? WHERE id=?", (int(value), peer_id))

    def revoke(self, peer_id):
        with self.lock, closing(connect(self.db_path)) as db, db:
            if any(offer.peer_id == peer_id and offer.state == "transferring" for offer in self.offers.values()):
                raise ValueError("Дождитесь завершения активной передачи")
            db.execute("DELETE FROM transfer_peers WHERE id=?", (peer_id,))
            for offer in self.offers.values():
                if offer.peer_id == peer_id and offer.state not in TERMINAL:
                    self.set_state(offer, "rejected")

    def new_invite(self, address):
        with self.lock:
            if self.pairing:
                self.pairing.declined = True
            self.pairing = None
            self.invite_token = secrets.token_urlsafe(24)
            self.manual_invite = f"{secrets.randbelow(10**6):06d}"
            self.manual_attempts = 5
            self.invite_expires = time.monotonic() + 120
            return {
                "v": 1, "host": address, "port": self.port, "name": self.name,
                "pin": self.pin, "token": self.invite_token,
            }

    def pairing_available(self):
        with self.lock:
            return bool(self.invite_token and time.monotonic() < self.invite_expires)

    def has_recent_contact(self, peer_id):
        return time.monotonic() - self.last_seen.get(peer_id, float("-inf")) < 12

    def begin_pairing(self, data):
        with self.lock:
            qr_matches = self.invite_token and hmac.compare_digest(self.invite_token.encode(), data.token.encode())
            manual_matches = False
            if len(data.token) == 6 and self.manual_attempts and self.manual_invite and self.pairing_available():
                self.manual_attempts -= 1
                manual_matches = hmac.compare_digest(self.manual_invite.encode(), data.token.encode())
            if (
                not self.pairing_available()
                or not (qr_matches or manual_matches)
            ):
                raise HTTPException(403, "Код неверный, истёк или уже использован. При необходимости создайте новый код.")
            self.invite_token = None
            self.manual_invite = None
            request = Pairing(data.name.strip() or "Android")
            self.pairing = request
            return request

    def reply_pairing(self, accept):
        with self.lock:
            request = self.pairing
            self.pairing = None
            if not request or request.declined or time.monotonic() - request.created >= OFFER_TIMEOUT:
                return
            if not accept:
                request.declined = True
                return
            peer_id, token = secrets.token_hex(16), secrets.token_urlsafe(32)
            with closing(connect(self.db_path)) as db, db:
                db.execute(
                    "INSERT INTO transfer_peers (id,name,secret) VALUES (?,?,?)",
                    (peer_id, request.name, secret_hash(token)),
                )
            request.credentials = {"id": peer_id, "token": token, "name": self.name}

    def authenticate(self, credential):
        if not credential:
            raise HTTPException(401, "Требуется сопряжение")
        with closing(connect(self.db_path)) as db:
            row = db.execute(
                "SELECT id FROM transfer_peers WHERE secret=?",
                (secret_hash(credential),),
            ).fetchone()
        if not row:
            raise HTTPException(401, "Сопряжение отозвано")
        with self.lock:
            self.last_seen[row[0]] = time.monotonic()
        return row[0]

    def check_capacity(self, size):
        if self.limit is not None and size > self.limit:
            raise HTTPException(413, "Получатель ограничил размер файла")
        try:
            free = shutil.disk_usage(self.inbox).free
        except OSError as error:
            raise HTTPException(507, "Выбранная папка приёма на компьютере недоступна") from error
        if size > free:
            raise HTTPException(507, "На компьютере не хватает места")

    def record_progress(self, offer, size):
        with self.lock:
            if offer.state == "transferring":
                offer.received = max(offer.received, size)
                offer.updated = time.monotonic()

    def set_state(self, offer, state):
        offer.state = state
        offer.updated = time.monotonic()

    def prune(self):
        now = time.monotonic()
        for offer in list(self.offers.values()):
            if offer.state == "pending" and now - offer.created >= OFFER_TIMEOUT:
                self.set_state(offer, "expired")
            if offer.state in {"accepted", "transferring"} and now - offer.updated > 1800:
                self.set_state(offer, "failed")
            if offer.state in TERMINAL and now - offer.updated > 600:
                del self.offers[offer.id]

    def add_offer(self, peer_id, direction, metadata, path=None):
        with self.lock:
            self.prune()
            if len(self.offers) >= 1000:
                raise HTTPException(503, "Очередь передач заполнена")
            with closing(connect(self.db_path)) as db:
                row = db.execute("SELECT trusted FROM transfer_peers WHERE id=?", (peer_id,)).fetchone()
            if row is None:
                raise HTTPException(401, "Сопряжение отозвано")
            if direction == "upload":
                self.check_capacity(metadata.size)
            offer = Offer(secrets.token_hex(16), peer_id, direction, metadata, path)
            if direction == "upload" and row[0]:
                self.set_state(offer, "accepted")
            self.offers[offer.id] = offer
            return offer

    def queue_file(self, peer_id, path):
        digest = hashlib.sha256()
        size = 0
        with path.open("rb") as file:
            while chunk := file.read(CHUNK_SIZE):
                digest.update(chunk)
                size += len(chunk)
        return self.add_offer(peer_id, "download", Metadata(
            name=path.name, size=size, sha256=digest.hexdigest(),
        ), path)

    def get_offer(self, offer_id, peer_id=None, direction=None):
        self.prune()
        offer = self.offers.get(offer_id)
        if not offer or (peer_id is not None and offer.peer_id != peer_id):
            raise HTTPException(404, "Передача не найдена")
        if direction and offer.direction != direction:
            raise HTTPException(409, "Неверное направление передачи")
        return offer

    def decide(self, offer_id, accept, direction, peer_id=None):
        with self.lock:
            offer = self.get_offer(offer_id, peer_id, direction)
            target = "accepted" if accept else "rejected"
            if offer.state == target:
                return offer
            if offer.state != "pending":
                raise HTTPException(409, "Запрос уже закрыт")
            if accept and direction == "upload":
                self.check_capacity(offer.metadata.size)
            self.set_state(offer, target)
            return offer

    def save_history(self, offer, path):
        source, target = (
            (offer.peer_id, self.pin) if offer.direction == "upload" else (self.pin, offer.peer_id)
        )
        self.history.add_transfer_record(TransferHistory(
            source_device_id=source, target_device_id=target, filename=offer.metadata.name,
            file_path=str(path), file_size=offer.metadata.size, mime_type="application/octet-stream",
            transferred_at=datetime.now(), status="completed",
        ))

    def publish_upload(self, temporary, offer):
        name = Path(safe_name(offer.metadata.name))
        with self.lock:
            if offer.state != "transferring":
                raise HTTPException(409, "Передача закрыта")
            directory = temporary.parent
            target = directory / name
            index = 1
            while target.exists():
                target = directory / f"{name.stem} ({index}){name.suffix}"
                index += 1
            temporary.rename(target)
            try:
                self.save_history(offer, target)
            except Exception:
                target.unlink(missing_ok=True)
                raise
            self.set_state(offer, "completed")


def make_api(service):
    app = FastAPI(title="Local Transfer", version="1", docs_url=None, redoc_url=None, openapi_url=None)
    bearer = HTTPBearer(auto_error=False)

    def peer(authorization: HTTPAuthorizationCredentials | None = Depends(bearer)):
        return service.authenticate(authorization.credentials if authorization else None)

    @app.get(API + "/health")
    def health():
        return {"version": 1, "name": service.name}

    @app.post(API + "/pair", response_model=Paired)
    async def pair(data: PairRequest):
        request = service.begin_pairing(data)
        try:
            while time.monotonic() - request.created < OFFER_TIMEOUT:
                if request.credentials:
                    return request.credentials
                if request.declined:
                    raise HTTPException(403, "Подключение отклонено на ПК")
                await asyncio.sleep(0.2)
            raise HTTPException(408, "Время подключения истекло")
        finally:
            with service.lock:
                if service.pairing is request:
                    service.pairing = None

    @app.get(API + "/offers", response_model=list[TransferStatus])
    def offers(identity=Depends(peer)):
        with service.lock:
            service.prune()
            return [
                offer.payload() for offer in service.offers.values()
                if offer.peer_id == identity and offer.direction == "download"
                and offer.state not in TERMINAL
            ]

    @app.post(API + "/offers", status_code=201, response_model=TransferStatus)
    def offer_upload(data: Metadata, identity=Depends(peer)):
        return service.add_offer(identity, "upload", data).payload()

    @app.get(API + "/offers/{offer_id}", response_model=TransferStatus)
    def status(offer_id: str, identity=Depends(peer)):
        with service.lock:
            return service.get_offer(offer_id, identity).payload()

    @app.post(API + "/offers/{offer_id}/decision", response_model=TransferStatus)
    def decision(offer_id: str, data: Decision, identity=Depends(peer)):
        return service.decide(offer_id, data.accept, "download", identity).payload()

    @app.put(
        API + "/offers/{offer_id}/content",
        response_model=TransferStatus,
        openapi_extra={"requestBody": {"required": True, "content": {
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        }}},
    )
    async def upload(offer_id: str, request: Request, identity=Depends(peer)):
        with service.lock:
            offer = service.get_offer(offer_id, identity, "upload")
            if offer.state != "accepted":
                raise HTTPException(409, "Передача не принята или уже началась")
            service.check_capacity(offer.metadata.size)
            content_length = request.headers.get("content-length")
            if content_length is not None and content_length != str(offer.metadata.size):
                raise HTTPException(422, "Объявленный размер не совпадает")
            service.set_state(offer, "transferring")
            temporary = service.inbox / f".{offer.id}.part"
        committed = False
        digest = hashlib.sha256()
        total = 0
        try:
            with temporary.open("xb") as output:
                async for chunk in request.stream():
                    total += len(chunk)
                    if total > offer.metadata.size:
                        raise HTTPException(413, "Получено больше заявленного размера")
                    if chunk:
                        await asyncio.to_thread(output.write, chunk)
                        digest.update(chunk)
                        service.record_progress(offer, total)
            if total != offer.metadata.size or digest.hexdigest() != offer.metadata.sha256:
                raise HTTPException(422, "Проверка целостности не пройдена")
            service.publish_upload(temporary, offer)
            committed = True
            return offer.payload()
        except OSError as error:
            raise HTTPException(507, "Не удалось записать файл на компьютер") from error
        finally:
            if not committed:
                with suppress(OSError):
                    temporary.unlink(missing_ok=True)
                with service.lock:
                    if offer.state == "transferring":
                        service.set_state(offer, "failed")

    @app.get(
        API + "/offers/{offer_id}/content", response_class=FileResponse,
        responses={200: {"content": {
            "application/octet-stream": {"schema": {"type": "string", "format": "binary"}},
        }}},
    )
    def download(offer_id: str, identity=Depends(peer)):
        with service.lock:
            offer = service.get_offer(offer_id, identity, "download")
            if offer.state not in {"accepted", "transferring"}:
                raise HTTPException(409, "Передача не принята или уже закрыта")
            if not offer.path or not offer.path.is_file() or offer.path.stat().st_size != offer.metadata.size:
                service.set_state(offer, "failed")
                raise HTTPException(410, "Исходный файл изменился или удалён")
            service.set_state(offer, "transferring")
            return TrackedFileResponse(offer.path, lambda size: service.record_progress(offer, size))

    @app.post(API + "/offers/{offer_id}/complete", response_model=TransferStatus)
    def complete(offer_id: str, data: Receipt, identity=Depends(peer)):
        with service.lock:
            offer = service.get_offer(offer_id, identity, "download")
            target = "completed" if data.success else "failed"
            if offer.state == target:
                return offer.payload()
            if offer.state not in {"accepted", "transferring"} or (data.success and offer.state != "transferring"):
                raise HTTPException(409, "Передача уже закрыта")
            if data.success:
                service.save_history(offer, offer.path)
                offer.received = offer.metadata.size
            service.set_state(offer, target)
            return offer.payload()

    return app

