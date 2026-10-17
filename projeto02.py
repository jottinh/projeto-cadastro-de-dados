import json
import threading
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse


PASTA = Path(__file__).resolve().parent
ARQUIVO_HTML = PASTA / "mensageiro.html"
ARQUIVO_DADOS = PASTA / "mensageiro_dados.json"
TRAVA = threading.Lock()


def hora_atual():
	return datetime.now().strftime("%H:%M")


def conversas_de_exemplo():
	exemplos = [
		("Marina Costa", "marina@email.com", 47, True, 2, [
			("them", "Você viu as fotos do fim de semana?", "09:38"),
			("me", "Vi sim! Ficaram incríveis 📸", "09:41"),
			("them", "Vou te mandar o álbum completo mais tarde", "09:42"),
		]),
		("Rafael Mendes", "rafa@email.com", 12, False, 0, [
			("them", "Fechado, nos vemos às 19h!", "09:15"),
			("me", "Combinado. Já reservei a mesa", "09:18"),
		]),
		("Lia Oliveira", "lia@email.com", 44, True, 1, [
			("them", "Obrigada pela ajuda de hoje 💛", "08:56"),
			("me", "Sempre que precisar!", "09:02"),
		]),
		("Grupo: Casa 204", "4 participantes", 5, False, 0, [
			("them", "Pedro: alguém traz sobremesa?", "Ontem"),
			("me", "Eu levo! 🍰", "Ontem"),
		]),
	]

	conversas = []
	for nome, identificador, avatar, online, nao_lidas, mensagens in exemplos:
		itens = [
			{"id": uuid.uuid4().hex, "sender": remetente, "text": texto, "time": horario}
			for remetente, texto, horario in mensagens
		]
		conversas.append({
			"id": uuid.uuid4().hex,
			"name": nome,
			"handle": identificador,
			"avatar": f"https://i.pravatar.cc/96?img={avatar}",
			"online": online,
			"unread": nao_lidas,
			"messages": itens,
		})
	return conversas


def carregar_conversas():
	if not ARQUIVO_DADOS.exists():
		conversas = conversas_de_exemplo()
		salvar_conversas(conversas)
		return conversas

	try:
		with ARQUIVO_DADOS.open("r", encoding="utf-8") as arquivo:
			conversas = json.load(arquivo)
	except (OSError, json.JSONDecodeError) as erro:
		raise RuntimeError(f"Nao foi possivel ler {ARQUIVO_DADOS.name}: {erro}") from erro

	if not isinstance(conversas, list):
		raise RuntimeError(f"{ARQUIVO_DADOS.name} deve conter uma lista de conversas.")
	return conversas


def salvar_conversas(conversas):
	temporario = ARQUIVO_DADOS.with_suffix(".tmp")
	with temporario.open("w", encoding="utf-8") as arquivo:
		json.dump(conversas, arquivo, ensure_ascii=False, indent=2)
	temporario.replace(ARQUIVO_DADOS)


CONVERSAS = carregar_conversas()


class MensageiroHandler(BaseHTTPRequestHandler):
	def responder_json(self, status, dados):
		conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
		self.send_response(status)
		self.send_header("Content-Type", "application/json; charset=utf-8")
		self.send_header("Content-Length", str(len(conteudo)))
		self.end_headers()
		self.wfile.write(conteudo)

	def ler_json(self):
		tamanho = int(self.headers.get("Content-Length", "0"))
		if tamanho > 65536:
			raise ValueError("A requisicao excede o limite permitido.")
		return json.loads(self.rfile.read(tamanho).decode("utf-8"))

	def do_GET(self):
		caminho = urlparse(self.path).path
		if caminho == "/":
			try:
				conteudo = ARQUIVO_HTML.read_bytes()
			except OSError:
				self.send_error(500, "Arquivo mensageiro.html nao encontrado")
				return
			self.send_response(200)
			self.send_header("Content-Type", "text/html; charset=utf-8")
			self.send_header("Content-Length", str(len(conteudo)))
			self.end_headers()
			self.wfile.write(conteudo)
		elif caminho == "/api/chats":
			with TRAVA:
				self.responder_json(200, CONVERSAS)
		else:
			self.responder_json(404, {"error": "Rota nao encontrada."})

	def do_POST(self):
		caminho = urlparse(self.path).path
		try:
			dados = self.ler_json()
		except (ValueError, UnicodeDecodeError, json.JSONDecodeError) as erro:
			self.responder_json(400, {"error": f"Dados invalidos: {erro}"})
			return

		if not isinstance(dados, dict):
			self.responder_json(400, {"error": "Envie um objeto JSON."})
			return

		if caminho == "/api/chats":
			nome = str(dados.get("name", "")).strip()
			if not nome:
				self.responder_json(400, {"error": "Informe o nome do contato."})
				return
			conversa = {
				"id": uuid.uuid4().hex,
				"name": nome[:80],
				"handle": str(dados.get("handle", "Novo contato")).strip()[:100],
				"avatar": f"https://i.pravatar.cc/96?img={len(CONVERSAS) + 20}",
				"online": False,
				"unread": 0,
				"messages": [],
			}
			with TRAVA:
				CONVERSAS.insert(0, conversa)
				salvar_conversas(CONVERSAS)
			self.responder_json(201, conversa)
			return

		if caminho == "/api/messages":
			conversa_id = str(dados.get("chatId", ""))
			texto = str(dados.get("text", "")).strip()
			if not texto or len(texto) > 4000:
				self.responder_json(400, {"error": "A mensagem deve ter entre 1 e 4000 caracteres."})
				return
			with TRAVA:
				conversa = next((item for item in CONVERSAS if item["id"] == conversa_id), None)
				if conversa is None:
					self.responder_json(404, {"error": "Conversa nao encontrada."})
					return
				mensagem = {
					"id": uuid.uuid4().hex,
					"sender": "me",
					"text": texto,
					"time": hora_atual(),
				}
				conversa["messages"].append(mensagem)
				salvar_conversas(CONVERSAS)
			self.responder_json(201, mensagem)
			return

		if caminho == "/api/read":
			conversa_id = str(dados.get("chatId", ""))
			with TRAVA:
				conversa = next((item for item in CONVERSAS if item["id"] == conversa_id), None)
				if conversa is None:
					self.responder_json(404, {"error": "Conversa nao encontrada."})
					return
				conversa["unread"] = 0
				salvar_conversas(CONVERSAS)
			self.responder_json(200, {"ok": True})
			return

		self.responder_json(404, {"error": "Rota nao encontrada."})


def iniciar_servidor():
	porta = 8765
	try:
		servidor = ThreadingHTTPServer(("127.0.0.1", porta), MensageiroHandler)
	except OSError:
		servidor = ThreadingHTTPServer(("127.0.0.1", 0), MensageiroHandler)
		porta = servidor.server_address[1]

	print(f"Mensageiro local disponivel em http://127.0.0.1:{porta}")
	print("Pressione Ctrl+C para encerrar.")
	try:
		servidor.serve_forever()
	except KeyboardInterrupt:
		print("\nServidor encerrado.")
	finally:
		servidor.server_close()


if __name__ == "__main__":
	iniciar_servidor()
