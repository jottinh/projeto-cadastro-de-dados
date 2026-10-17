import hashlib
import os
import re
import secrets
import sqlite3
import time
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from functools import wraps
from pathlib import Path

from flask import Flask, g, jsonify, render_template, request, session
from flask_wtf.csrf import CSRFProtect
from werkzeug.security import check_password_hash, generate_password_hash

ROOT = Path(__file__).resolve().parent
INSTANCE = ROOT / "instance"
INSTANCE.mkdir(exist_ok=True)
DATABASE = INSTANCE / "beneficios_demo.db"
KEY_FILE = INSTANCE / "beneficios_secret.key"


def get_secret():
	key = os.environ.get("BENEFICIOS_SECRET_KEY")
	if key:
		return key
	if not KEY_FILE.exists():
		KEY_FILE.write_bytes(secrets.token_bytes(48))
		try:
			KEY_FILE.chmod(0o600)
		except OSError:
			pass
	return KEY_FILE.read_bytes()


app = Flask(__name__, instance_path=str(INSTANCE), template_folder=str(ROOT / "templates"), static_folder=str(ROOT / "static"))
app.config.update(SECRET_KEY=get_secret(), SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Lax",
				  SESSION_COOKIE_SECURE=os.environ.get("BENEFICIOS_HTTPS", "0") == "1",
				  PERMANENT_SESSION_LIFETIME=60 * 60 * 8, MAX_CONTENT_LENGTH=16 * 1024, WTF_CSRF_TIME_LIMIT=3600)
CSRFProtect(app)

SCHEMA = """
CREATE TABLE IF NOT EXISTS admins(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, password_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS rate_events(id INTEGER PRIMARY KEY, key_hash TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS rate_lookup ON rate_events(key_hash, created_at);
CREATE TABLE IF NOT EXISTS beneficiaries(id INTEGER PRIMARY KEY, reference TEXT UNIQUE NOT NULL, name TEXT NOT NULL, household_size INTEGER NOT NULL, benefit_type TEXT NOT NULL, monthly_cents INTEGER NOT NULL, balance_cents INTEGER NOT NULL, status TEXT NOT NULL, created_at REAL NOT NULL, updated_at REAL NOT NULL);
CREATE TABLE IF NOT EXISTS balance_history(id INTEGER PRIMARY KEY, beneficiary_id INTEGER NOT NULL REFERENCES beneficiaries(id), admin_id INTEGER NOT NULL REFERENCES admins(id), old_cents INTEGER NOT NULL, new_cents INTEGER NOT NULL, reason TEXT NOT NULL, created_at REAL NOT NULL);
CREATE INDEX IF NOT EXISTS history_lookup ON balance_history(beneficiary_id, id DESC);
"""


class ClosingConnection(sqlite3.Connection):
	def __exit__(self, exc_type, exc_value, traceback):
		try:
			return super().__exit__(exc_type, exc_value, traceback)
		finally:
			self.close()


def db():
	connection = sqlite3.connect(DATABASE, timeout=10, factory=ClosingConnection)
	connection.row_factory = sqlite3.Row
	connection.execute("PRAGMA foreign_keys=ON")
	return connection


def init_db():
	with db() as connection:
		connection.executescript(SCHEMA)


init_db()


def cents(value):
	text = str(value or "").strip().replace("R$", "").replace(" ", "")
	if "," in text:
		text = text.replace(".", "").replace(",", ".")
	try:
		amount = Decimal(text).quantize(Decimal("0.01"))
	except (InvalidOperation, ValueError):
		return None
	if not amount.is_finite() or amount < 0 or amount > Decimal("1000000"):
		return None
	return int(amount * 100)


def money(value):
	return f"{value / 100:.2f}"


def login_limited(username):
	now = time.time()
	identity = hashlib.sha256(f"{username.lower()}|{request.remote_addr}".encode()).hexdigest()
	with db() as connection:
		connection.execute("DELETE FROM rate_events WHERE created_at < ?", (now - 86400,))
		count = connection.execute("SELECT COUNT(*) FROM rate_events WHERE key_hash=? AND created_at>?", (identity, now - 900)).fetchone()[0]
		if count >= 8:
			return True
		connection.execute("INSERT INTO rate_events(key_hash,created_at) VALUES(?,?)", (identity, now))
	return False


def admin_only(view):
	@wraps(view)
	def wrapped(*args, **kwargs):
		admin_id = session.get("admin_id")
		if not admin_id:
			return jsonify(error="Entre na conta de administracao."), 401
		with db() as connection:
			admin = connection.execute("SELECT id,username FROM admins WHERE id=?", (admin_id,)).fetchone()
		if admin is None:
			session.clear()
			return jsonify(error="Sessao encerrada. Entre novamente."), 401
		g.admin = admin
		return view(*args, **kwargs)
	return wrapped


@app.after_request
def security_headers(response):
	response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; form-action 'self'; frame-ancestors 'none'; base-uri 'self'"
	response.headers["X-Content-Type-Options"] = "nosniff"
	response.headers["X-Frame-Options"] = "DENY"
	response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
	response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
	if app.config["SESSION_COOKIE_SECURE"]:
		response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
	return response


@app.get("/")
def index():
	return render_template("beneficios.html")


@app.get("/api/session")
def session_status():
	with db() as connection:
		count = connection.execute("SELECT COUNT(*) FROM admins").fetchone()[0]
		admin = connection.execute("SELECT username FROM admins WHERE id=?", (session.get("admin_id"),)).fetchone()
	return jsonify(setup_required=count == 0, authenticated=admin is not None, username=admin["username"] if admin else None)


@app.post("/api/setup")
def setup():
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		return jsonify(error="Dados invalidos."), 400
	username = str(data.get("username", "")).strip()
	password = str(data.get("password", ""))
	if not re.fullmatch(r"[A-Za-z0-9_.-]{3,40}", username):
		return jsonify(error="Usuario: 3 a 40 caracteres, letras, numeros, ponto, hifen ou sublinhado."), 400
	if not 14 <= len(password) <= 256:
		return jsonify(error="A senha deve ter pelo menos 14 caracteres."), 400
	with db() as connection:
		if connection.execute("SELECT 1 FROM admins LIMIT 1").fetchone():
			return jsonify(error="Configuracao inicial ja concluida."), 409
		cursor = connection.execute("INSERT INTO admins(username,password_hash,created_at) VALUES(?,?,?)", (username, generate_password_hash(password), time.time()))
		admin_id = cursor.lastrowid
	session.clear()
	session["admin_id"] = admin_id
	session.permanent = True
	return jsonify(ok=True), 201


@app.post("/api/login")
def login():
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		return jsonify(error="Dados invalidos."), 400
	username = str(data.get("username", "")).strip()
	if login_limited(username):
		return jsonify(error="Muitas tentativas. Aguarde 15 minutos."), 429
	with db() as connection:
		admin = connection.execute("SELECT id,password_hash FROM admins WHERE username=?", (username,)).fetchone()
	if admin is None or not check_password_hash(admin["password_hash"], str(data.get("password", ""))):
		return jsonify(error="Usuario ou senha incorretos."), 401
	session.clear()
	session["admin_id"] = admin["id"]
	session.permanent = True
	return jsonify(ok=True)


@app.get("/api/beneficiaries")
@admin_only
def list_beneficiaries():
	with db() as connection:
		rows = connection.execute("SELECT * FROM beneficiaries ORDER BY name COLLATE NOCASE").fetchall()
	entries = [{"id": row["id"], "reference": row["reference"], "name": row["name"],
				"household_size": row["household_size"], "benefit_type": row["benefit_type"],
				"monthly_value": money(row["monthly_cents"]), "balance": money(row["balance_cents"]),
				"status": row["status"], "created_at": datetime.fromtimestamp(row["created_at"], timezone.utc).astimezone().strftime("%d/%m/%Y")}
			   for row in rows]
	total = sum(row["balance_cents"] for row in rows)
	active = sum(row["status"] == "Ativo" for row in rows)
	return jsonify(entries=entries, stats={"count": len(entries), "active": active, "balance": money(total)})


@app.post("/api/beneficiaries")
@admin_only
def create_beneficiary():
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		return jsonify(error="Dados invalidos."), 400
	name = str(data.get("name", "")).strip()
	kind = str(data.get("benefit_type", "")).strip()
	status = str(data.get("status", "Ativo")).strip()
	try:
		members = int(data.get("household_size", 0))
	except (ValueError, TypeError):
		members = 0
	monthly = cents(data.get("monthly_value"))
	balance = cents(data.get("balance"))
	if not 2 <= len(name) <= 100:
		return jsonify(error="O nome deve ter de 2 a 100 caracteres."), 400
	if not 1 <= members <= 20:
		return jsonify(error="Informe de 1 a 20 integrantes."), 400
	if kind not in ("Apoio familiar", "Apoio alimentar", "Apoio educacional"):
		return jsonify(error="Selecione uma categoria valida."), 400
	if status not in ("Ativo", "Pendente", "Encerrado"):
		return jsonify(error="Selecione um status valido."), 400
	if monthly is None or balance is None:
		return jsonify(error="Valores devem estar entre R$ 0,00 e R$ 1.000.000,00."), 400
	now = time.time()
	reference = f"SIM-{secrets.token_hex(4).upper()}"
	with db() as connection:
		cursor = connection.execute("INSERT INTO beneficiaries(reference,name,household_size,benefit_type,monthly_cents,balance_cents,status,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)", (reference, name, members, kind, monthly, balance, status, now, now))
		beneficiary_id = cursor.lastrowid
		connection.execute("INSERT INTO balance_history(beneficiary_id,admin_id,old_cents,new_cents,reason,created_at) VALUES(?,?,0,?,?,?)", (beneficiary_id, g.admin["id"], balance, "Saldo inicial do cadastro", now))
	return jsonify(id=beneficiary_id, reference=reference), 201


@app.post("/api/beneficiaries/<int:beneficiary_id>/balance")
@admin_only
def update_balance(beneficiary_id):
	data = request.get_json(silent=True)
	if not isinstance(data, dict):
		return jsonify(error="Dados invalidos."), 400
	balance = cents(data.get("balance"))
	reason = str(data.get("reason", "")).strip()
	if balance is None:
		return jsonify(error="Saldo deve estar entre R$ 0,00 e R$ 1.000.000,00."), 400
	if not 4 <= len(reason) <= 240:
		return jsonify(error="Explique o ajuste em 4 a 240 caracteres."), 400
	now = time.time()
	with db() as connection:
		current = connection.execute("SELECT balance_cents FROM beneficiaries WHERE id=?", (beneficiary_id,)).fetchone()
		if current is None:
			return jsonify(error="Cadastro nao encontrado."), 404
		connection.execute("UPDATE beneficiaries SET balance_cents=?,updated_at=? WHERE id=?", (balance, now, beneficiary_id))
		connection.execute("INSERT INTO balance_history(beneficiary_id,admin_id,old_cents,new_cents,reason,created_at) VALUES(?,?,?,?,?,?)", (beneficiary_id, g.admin["id"], current["balance_cents"], balance, reason, now))
	return jsonify(ok=True, balance=money(balance))


@app.get("/api/beneficiaries/<int:beneficiary_id>/history")
@admin_only
def history(beneficiary_id):
	with db() as connection:
		if connection.execute("SELECT 1 FROM beneficiaries WHERE id=?", (beneficiary_id,)).fetchone() is None:
			return jsonify(error="Cadastro nao encontrado."), 404
		rows = connection.execute("SELECT h.*,a.username FROM balance_history h JOIN admins a ON a.id=h.admin_id WHERE h.beneficiary_id=? ORDER BY h.id DESC LIMIT 100", (beneficiary_id,)).fetchall()
	return jsonify([{"old_balance": money(row["old_cents"]), "new_balance": money(row["new_cents"]),
					 "reason": row["reason"], "admin": row["username"],
					 "date": datetime.fromtimestamp(row["created_at"], timezone.utc).astimezone().strftime("%d/%m/%Y %H:%M")}
					for row in rows])


@app.post("/api/logout")
@admin_only
def logout():
	session.clear()
	return jsonify(ok=True)


if __name__ == "__main__":
	host = os.environ.get("BENEFICIOS_HOST", "127.0.0.1")
	port = int(os.environ.get("BENEFICIOS_PORT", "8767"))
	print(f"Cadastro de beneficios (SIMULACAO) em http://{host}:{port}")
	print("Nao use dados reais: nao e um sistema oficial e nao movimenta pagamentos.")
	app.run(host=host, port=port, debug=False, threaded=True)
