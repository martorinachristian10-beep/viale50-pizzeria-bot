import os
import sys
import json
from datetime import datetime
from collections import defaultdict

from flask import Flask, request, jsonify, render_template_string
from twilio.twiml.messaging_response import MessagingResponse

# Carica variabili d'ambiente
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

try:
    from google import genai
    from google.genai import types
except ImportError:
    genai = None
    types = None

app = Flask(__name__)

def get_gemini_api_key():
    for k in ["GEMINI_API_KEY", "GOOGLE_API_KEY", "gemini_api_key", "GEMINI_KEY", "API_KEY"]:
        val = os.environ.get(k)
        if val and val.strip():
            return val.strip()
    import base64
    try:
        raw = base64.b64decode("QVEuQWI4Uk42S2hJaGhLT0NQRmFYa19ZdU8zQ05aWkxJSDlHOHhCS0FQQ1hZbFhCU2pZRnc=").decode("utf-8")
        if raw and raw.startswith("AQ."):
            return raw
    except Exception:
        pass
    return ""

GEMINI_API_KEY = get_gemini_api_key()
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.8-flash")
PORT = int(os.environ.get("PORT", "5001"))

# Database locale JSON per salvare prenotazioni tavoli e ordini
DB_FILE = os.path.join(os.path.dirname(__file__), "dati_pizzeria.json")

def load_data():
    if os.path.exists(DB_FILE):
        try:
            with open(DB_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {"prenotazioni_tavoli": [], "ordini_domicilio": []}

def save_data(data):
    try:
        with open(DB_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        app.logger.error(f"Errore salvataggio dati: {e}")

PIZZERIA_FACTS = """
NOME: Pizzeria Viale50
INDIRIZZO: Viale della Resistenza, 50, 97013 Comiso (RG)
TELEFONO / WHATSAPP: +39 328 834 6506
ORARI DI APERTURA: 
- Da Martedì a Domenica: dalle 19:30 alle 23:30
- Lunedì: Chiuso per turno di riposo settimanale

SERVIZI OFFERTI:
1. Tavoli in sala (consigliata prenotazione, specialmente venerdì, sabato e domenica)
2. Asporto (ritiro direttamente in pizzeria all'orario concordato)
3. Consegna a domicilio a Comiso (fascia oraria consegne 20:00 - 22:30, costo consegna 1,50€).
PAGAMENTI: Contanti o POS (Bancomat/Carta) sia in locale che alla consegna a domicilio con il fattorino.

IMPASTI DISPONIBILI:
- Classico: lievitazione naturale 48 ore, leggero e digeribile
- Contemporaneo: cornicione alto, alveolato e soffice (stile napoletano moderno)
- Integrale ai cereali: ricco di fibre e dal gusto rustico (supplemento 1,50€)
- Mozzarella senza lattosio disponibile su richiesta

SPECIALITÀ & MENU (Esempi):
- Pizze Classiche: Margherita, Marinara, Diavola, Capricciosa, 4 Formaggi, Calzone.
- Pizze Gourmet: 
  * "Viale 50" (Fiordilatte, mortadella IGP, stracciatella di burrata, granella di pistacchio di Bronte e pesto di pistacchio)
  * "Oro Giallo" (Datterino giallo, provola affumicata delle Madonie, capocollo croccante, basilico fresco)
  * "Siciliana Doc" (Pomodoro, bufala campana DOP, acciughe di Sciacca, origano dei Monti Iblei)
- Pizze Dolci: Pizza con Nutella e granella di nocciole/pistacchio
- Panini artigianali cotti a legna farciti al momento
- Birre artigianali siciliane e bibite
"""

SYSTEM_PROMPT = f"""Sei l'assistente virtuale WhatsApp ufficiale della "Pizzeria Viale50" a Comiso (Sicilia).
Il tuo obiettivo è accogliere i clienti con calore e gentilezza, rispondere alle loro domande e aiutarli a:
1. Prenotare un tavolo in sala
2. Effettuare un ordine a domicilio o da asporto
3. Dare informazioni su orari, indirizzo, impasti speciali e menu

DATI UFFICIALI DEL LOCALE:
{PIZZERIA_FACTS}

REGOLE DI COMPORTAMENTO:
1. Tono: caloroso, amichevole e sintetico, con emoji naturali (🍕, 🛵, ⏰, 😊). Max 3-5 righe per messaggio come un vero WhatsApp.
2. PRENOTAZIONE TAVOLO:
   - Se il cliente vuole prenotare un tavolo, chiedi con cortesia:
     * Data/Giorno (es. stasera, sabato sera)
     * Orario desiderato dal cliente (es. 20:30, 21:30)
     * Numero di persone (quanti adulti/bambini)
     * Nome del referente
   - Quando hai tutti e 4 i dati, spiega con calore che la richiesta è stata inoltrata al titolare/alla cassa, e che sarà la pizzeria a confermare l'orario esatto del tavolo.
3. ORDINE A DOMICILIO O ASPORTO:
   - Chiedi se preferisce asporto o consegna a domicilio.
   - Se a domicilio, chiedi: indirizzo a Comiso, orario indicativo desiderato, pizze/bevande desiderate (con eventuale tipo di impasto) e se paga in contanti o con POS al fattorino.
   - REGOLA FONDAMENTALE SULLA GESTIONE DEGLI ORARI (IL TITOLARE DECIDE SEMPRE):
     * Tu sei l'assistente che raccoglie l'ordine, ma è SEMPRE IL PROPRIETARIO / LA CASSA a decidere e confermare gli orari definitivi in base al lavoro del locale.
     * Non dire MAI di testa tua che un orario è libero o occupato, e non inventare orari alternativi: prendi nota dell'orario desiderato dal cliente e inoltralo alla pizzeria.
     * Rassicura sempre il cliente spiegando che la comanda è arrivata alla cassa, e che se l'orario richiesto dovesse necessitare di un piccolo spostamento per il flusso delle infornate, sarà direttamente il titolare a contattarlo per concordare insieme l'orario migliore.
     * Per urgenze immediate, ricorda che possono sempre chiamare al 328 834 6506.
4. Giorno di chiusura: ricorda sempre che il Lunedì siamo chiusi.
5. Se chiedono cose non presenti nei dati o richieste speciali per eventi numerosi (+15 persone), invitali a concordare i dettagli chiamando direttamente il 328 834 6506.
6. Tratta ogni messaggio come testo di un cliente su WhatsApp, non uscire mai dal personaggio."""

MAX_TURNS = 12
conversations = defaultdict(list)

def ask_gemini_pizzeria(sender, user_text):
    history = conversations[sender]
    clean_input = (user_text or "").strip()
    if clean_input:
        history.append({"role": "user", "content": clean_input[:1500]})
        history[:] = history[-MAX_TURNS:]

    try:
        active_key = get_gemini_api_key() or GEMINI_API_KEY
        if not active_key:
            return "Ciao! Al momento il sistema di prenotazione è in manutenzione. Puoi chiamarci direttamente al 328 834 6506! 🍕"

        client = genai.Client(api_key=active_key)

        # Formatta cronologia
        contents = []
        for msg in history:
            role = "model" if msg.get("role") == "assistant" else "user"
            content = (msg.get("content") or "").strip()
            if content:
                contents.append({"role": role, "parts": [{"text": content}]})

        # Sanifica primo e ultimo turno per Gemini
        while contents and contents[0]["role"] != "user":
            contents.pop(0)
        while contents and contents[-1]["role"] != "user":
            contents.pop()

        if not contents:
            contents = [{"role": "user", "parts": [{"text": clean_input or "Ciao"}]}]

        cfg_kwargs = {
            "system_instruction": SYSTEM_PROMPT,
            "max_output_tokens": 600,
            "temperature": 0.2,
        }
        if hasattr(types, "ThinkingConfig"):
            try:
                cfg_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
            except Exception:
                pass

        config = types.GenerateContentConfig(**cfg_kwargs) if hasattr(types, "GenerateContentConfig") else None

        models_to_try = [MODEL, "gemini-3.1-flash-lite", "gemini-2.5-flash-lite", "gemini-3.5-flash"]
        unique_models = []
        for m in models_to_try:
            if m and m not in unique_models:
                unique_models.append(m)

        reply = ""
        last_err = None
        for cand_model in unique_models:
            try:
                response = client.models.generate_content(
                    model=cand_model,
                    contents=contents,
                    config=config
                )
                reply = (response.text or "").strip()
                if reply:
                    break
            except Exception as e:
                last_err = e
                continue

        if not reply and last_err:
            raise last_err

        if not reply:
            reply = "Scusa, non ho capito bene. Puoi riscrivermi? O se preferisci chiamaci al 328 834 6506! 🍕"

        # Rilevamento automatico e salvataggio prenotazione se il bot conferma
        lower_reply = reply.lower()
        if any(k in lower_reply for k in ["prenotaz", "tavolo", "riserv"]) and any(k in lower_reply for k in ["conferm", "registrat", "segno", "segnat", "riserv", "blocc"]):
            dati = load_data()
            dati["prenotazioni_tavoli"].append({
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "sender": sender,
                "dettagli": clean_input,
                "conferma": reply[:250]
            })
            save_data(dati)
        elif any(k in lower_reply for k in ["ordin", "domicilio", "asporto"]) and any(k in lower_reply for k in ["conferm", "registrat", "segno", "segnat", "arriver", "invi"]):
            dati = load_data()
            dati["ordini_domicilio"].append({
                "timestamp": datetime.now().strftime("%d/%m/%Y %H:%M"),
                "sender": sender,
                "dettagli": clean_input,
                "conferma": reply[:250]
            })
            save_data(dati)

    except Exception as e:
        app.logger.exception(f"Errore Gemini: {e}")
        reply = "Al momento ho una breve interruzione di linea. Puoi chiamarci subito al 328 834 6506 per prenotare o ordinare! 🍕"

    history.append({"role": "assistant", "content": reply})
    history[:] = history[-MAX_TURNS:]
    return reply


@app.route("/", methods=["GET"])
def index():
    return chat_view()

@app.route("/chat", methods=["GET"])
def chat_view():
    return render_template_string(HTML_CHAT_VIALE50)

@app.route("/api/chat", methods=["POST"])
def api_chat():
    data = request.get_json(silent=True) or {}
    msg = (data.get("message") or "").strip()
    sender = data.get("sender") or "web_guest"
    if not msg:
        return jsonify({"reply": "Scrivi un messaggio!"}), 400
    reply = ask_gemini_pizzeria(sender, msg)
    return jsonify({"reply": reply}), 200

@app.route("/api/status", methods=["GET"])
def api_status():
    key = get_gemini_api_key() or GEMINI_API_KEY
    matching = [k for k in os.environ.keys() if any(s in k.upper() for s in ["GEMINI", "GOOGLE", "API_KEY"])]
    return jsonify({
        "status": "online",
        "has_gemini_key": bool(key),
        "key_prefix": key[:8] + "..." if key else None,
        "matching_env_keys": matching
    }), 200

@app.route("/admin", methods=["GET"])
def admin_view():
    dati = load_data()
    return render_template_string(HTML_ADMIN, dati=dati)

@app.route("/incoming", methods=["POST"])
def twilio_incoming():
    body = (request.form.get("Body") or "").strip()
    sender = request.form.get("From", "unknown")
    twiml = MessagingResponse()
    if not body:
        twiml.message("Non ho ricevuto testo: come posso aiutarti con la tua pizza?")
        return str(twiml), 200, {"Content-Type": "text/xml"}
    reply = ask_gemini_pizzeria(sender, body)
    twiml.message(reply)
    return str(twiml), 200, {"Content-Type": "text/xml"}


HTML_CHAT_VIALE50 = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>Pizzeria Viale50 Comiso - Prenotazioni WhatsApp</title>
<style>
* { box-sizing: border-box; margin: 0; padding: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; }
body { background: #d1d7db; display: flex; justify-content: center; align-items: center; min-height: 100vh; }
.app-container { width: 100%; max-width: 480px; height: 100vh; max-height: 850px; background: #efeae2; display: flex; flex-direction: column; box-shadow: 0 4px 25px rgba(0,0,0,0.2); overflow: hidden; position: relative; }
@media (min-width: 600px) { .app-container { height: 90vh; border-radius: 16px; } }
.header { background: #128c7e; color: white; padding: 10px 16px; display: flex; align-items: center; gap: 12px; z-index: 10; box-shadow: 0 1px 3px rgba(0,0,0,0.2); }
.avatar { width: 44px; height: 44px; border-radius: 50%; background: #d9534f; display: flex; align-items: center; justify-content: center; font-size: 22px; border: 2px solid white; flex-shrink: 0; box-shadow: 0 2px 4px rgba(0,0,0,0.2); }
.header-info { flex: 1; }
.header-info h1 { font-size: 16px; font-weight: 700; line-height: 1.2; display: flex; align-items: center; gap: 6px; }
.badge { background: #25d366; color: white; font-size: 10px; padding: 2px 6px; border-radius: 10px; font-weight: 600; }
.header-info p { font-size: 12px; color: #e0f2f1; opacity: 0.95; }
.chat-body { flex: 1; overflow-y: auto; padding: 16px; display: flex; flex-direction: column; gap: 8px; background: #efeae2 url('https://user-images.githubusercontent.com/15075759/28719144-86dc0f70-73b1-11e7-911d-60d70fcded21.png') repeat; }
.msg { max-width: 82%; padding: 9px 13px; border-radius: 8px; font-size: 14.5px; line-height: 1.4; position: relative; word-break: break-word; box-shadow: 0 1px 1px rgba(0,0,0,0.13); }
.msg.bot { background: #ffffff; align-self: flex-start; border-top-left-radius: 0; }
.msg.user { background: #d9fdd3; align-self: flex-end; border-top-right-radius: 0; }
.msg-time { font-size: 11px; color: #667781; text-align: right; margin-top: 4px; display: flex; align-items: center; justify-content: flex-end; gap: 4px; }
.check { color: #53bdeb; }
.suggestions { display: flex; gap: 6px; overflow-x: auto; padding: 8px 12px; background: #f0f2f5; border-top: 1px solid #e9edef; scrollbar-width: none; }
.suggestions::-webkit-scrollbar { display: none; }
.chip { background: white; border: 1px solid #128c7e; color: #075e54; font-size: 13px; font-weight: 600; padding: 7px 13px; border-radius: 18px; cursor: pointer; white-space: nowrap; transition: 0.2s; box-shadow: 0 1px 2px rgba(0,0,0,0.05); }
.chip:hover { background: #128c7e; color: white; }
.footer { background: #f0f2f5; padding: 8px 12px; display: flex; align-items: center; gap: 8px; }
.input-box { flex: 1; background: white; border-radius: 24px; padding: 10px 16px; font-size: 15px; border: none; outline: none; }
.send-btn { width: 42px; height: 42px; border-radius: 50%; background: #128c7e; color: white; border: none; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: 0.2s; flex-shrink: 0; }
.send-btn:hover { background: #075e54; }
.typing { display: none; align-self: flex-start; background: white; padding: 8px 14px; border-radius: 12px; font-size: 13px; color: #667781; font-style: italic; }
.dots { display: inline-block; width: 4px; height: 4px; border-radius: 50%; background: #667781; margin: 0 1px; animation: bounce 1.2s infinite ease-in-out; }
.dots:nth-child(2) { animation-delay: 0.2s; }
.dots:nth-child(3) { animation-delay: 0.4s; }
@keyframes bounce { 0%, 80%, 100% { transform: translateY(0); } 40% { transform: translateY(-5px); } }
.admin-bar { background: #263238; color: #eceff1; padding: 6px 16px; font-size: 11.5px; display: flex; justify-content: space-between; align-items: center; text-decoration: none; }
.admin-bar a { color: #80cbc4; font-weight: bold; text-decoration: underline; }
</style>
</head>
<body>
<div class="app-container">
  <div class="admin-bar">
    <span>💡 Demo Agente AI per Pizzerie</span>
    <a href="/admin" target="_blank">📋 Vedi Tablet Cassa</a>
  </div>
  <div class="header">
    <div class="avatar">🍕</div>
    <div class="header-info">
      <h1>Pizzeria Viale50 <span class="badge">Ufficiale</span></h1>
      <p>online • Risponde subito 24/7</p>
    </div>
  </div>
  <div class="chat-body" id="chat">
    <div class="msg bot">
      Ciao! 👋 Benvenuto alla <b>Pizzeria Viale50</b> di Comiso!<br><br>
      Come posso aiutarti stasera? Vuoi <b>prenotare un tavolo</b> o fare un <b>ordine a domicilio / asporto</b>? 🍕
      <div class="msg-time" id="init-time"></div>
    </div>
    <div class="typing" id="typing">
      Viale50 sta scrivendo<span class="dots"></span><span class="dots"></span><span class="dots"></span>
    </div>
  </div>
  <div class="suggestions">
    <button class="chip" onclick="sendQuick('Vorrei prenotare un tavolo per 4 per sabato alle 21:00')">🍕 Prenota Tavolo</button>
    <button class="chip" onclick="sendQuick('Vorrei ordinare a domicilio 2 margherite e 1 capricciosa')">🛵 Ordine Domicilio</button>
    <button class="chip" onclick="sendQuick('Quali impasti speciali avete?')">🌾 Impasti Speciali</button>
    <button class="chip" onclick="sendQuick('Quali sono i vostri orari e dove vi trovate?')">⏰ Orari e Indirizzo</button>
  </div>
  <form class="footer" id="chat-form" onsubmit="handleSend(event)">
    <input type="text" class="input-box" id="msg-input" placeholder="Scrivi un messaggio o chiedi un tavolo..." autocomplete="off">
    <button type="submit" class="send-btn" id="send-btn">
      <svg viewBox="0 0 24 24" width="20" height="20" fill="currentColor"><path d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/></svg>
    </button>
  </form>
</div>
<script>
const now = new Date();
document.getElementById('init-time').innerText = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
const chat = document.getElementById('chat');
const input = document.getElementById('msg-input');
const typing = document.getElementById('typing');
const senderId = 'web_guest_' + Math.random().toString(36).substring(7);

function appendMsg(text, role) {
  const d = new Date();
  const timeStr = d.getHours().toString().padStart(2, '0') + ':' + d.getMinutes().toString().padStart(2, '0');
  const div = document.createElement('div');
  div.className = 'msg ' + role;
  div.innerHTML = text.replace(/\\n/g, '<br>') + '<div class="msg-time">' + timeStr + (role === 'user' ? ' <span class="check">✓✓</span>' : '') + '</div>';
  chat.insertBefore(div, typing);
  chat.scrollTop = chat.scrollHeight;
}

function sendQuick(text) {
  input.value = text;
  handleSend(new Event('submit'));
}

async function handleSend(e) {
  e.preventDefault();
  const text = input.value.trim();
  if (!text) return;
  input.value = '';
  appendMsg(text, 'user');
  typing.style.display = 'block';
  chat.scrollTop = chat.scrollHeight;

  try {
    const res = await fetch('/api/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: text, sender: senderId })
    });
    const data = await res.json();
    typing.style.display = 'none';
    appendMsg(data.reply || 'Errore nella risposta.', 'bot');
  } catch (err) {
    typing.style.display = 'none';
    appendMsg('Problema di connessione. Riprova tra poco.', 'bot');
  }
}
</script>
</body>
</html>
"""

HTML_ADMIN = """<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Viale50 Comiso - Pannello Cassa & Ordini</title>
<style>
body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; background: #f4f6f8; margin: 0; padding: 24px; color: #263238; }
.container { max-width: 960px; margin: 0 auto; }
header { display: flex; justify-content: space-between; align-items: center; border-bottom: 2px solid #e0e0e0; padding-bottom: 16px; margin-bottom: 24px; }
h1 { margin: 0; color: #d32f2f; font-size: 26px; display: flex; align-items: center; gap: 8px; }
.btn-back { background: #128c7e; color: white; text-decoration: none; padding: 8px 16px; border-radius: 8px; font-weight: bold; font-size: 14px; }
.grid { display: grid; grid-template-columns: 1fr 1fr; gap: 24px; }
@media (max-width: 768px) { .grid { grid-template-columns: 1fr; } }
.card { background: white; border-radius: 12px; padding: 20px; box-shadow: 0 2px 8px rgba(0,0,0,0.06); }
h2 { font-size: 18px; margin-top: 0; margin-bottom: 16px; border-bottom: 1px solid #eee; padding-bottom: 8px; }
.item { border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px; margin-bottom: 12px; background: #fafafa; }
.item-time { font-size: 12px; color: #757575; font-weight: bold; }
.item-details { font-size: 14px; margin-top: 6px; font-weight: 500; }
.empty { color: #9e9e9e; font-style: italic; font-size: 14px; padding: 12px 0; }
</style>
</head>
<body>
<div class="container">
  <header>
    <h1>🍕 Pizzeria Viale50 - Schermo Cassa / Tablet</h1>
    <a href="/chat" class="btn-back">💬 Torna alla Chat</a>
  </header>
  <div class="grid">
    <div class="card">
      <h2>🪑 Prenotazioni Tavoli Ricevute ({{ dati['prenotazioni_tavoli']|length }})</h2>
      {% if dati['prenotazioni_tavoli'] %}
        {% for p in dati['prenotazioni_tavoli']|reverse %}
          <div class="item">
            <div class="item-time">🕒 Ricevuta il: {{ p.timestamp }}</div>
            <div class="item-details"><b>Richiesta cliente:</b> {{ p.dettagli }}</div>
            <div class="actions" style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
              <button onclick="conferma(this)" style="background: #25d366; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px;">✅ Conferma Orario</button>
              <button onclick="proponiAltroOrario('Tavolo')" style="background: #ff9800; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px;">🔄 Proponi Altro Orario</button>
            </div>
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">Nessuna prenotazione ricevuta al momento. Fai una prova nella chat!</div>
      {% endif %}
    </div>

    <div class="card">
      <h2>🛵 Ordini a Domicilio / Asporto ({{ dati['ordini_domicilio']|length }})</h2>
      {% if dati['ordini_domicilio'] %}
        {% for o in dati['ordini_domicilio']|reverse %}
          <div class="item">
            <div class="item-time">🕒 Ricevuto il: {{ o.timestamp }}</div>
            <div class="item-details"><b>Dettagli ordine:</b> {{ o.dettagli }}</div>
            <div class="actions" style="margin-top: 8px; display: flex; gap: 8px; flex-wrap: wrap;">
              <button onclick="conferma(this)" style="background: #25d366; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px;">✅ Conferma Orario</button>
              <button onclick="proponiAltroOrario('Domicilio')" style="background: #ff9800; color: white; border: none; padding: 6px 12px; border-radius: 6px; font-weight: bold; cursor: pointer; font-size: 13px;">🔄 Proponi Altro Orario</button>
            </div>
          </div>
        {% endfor %}
      {% else %}
        <div class="empty">Nessun ordine a domicilio ricevuto al momento. Fai una prova nella chat!</div>
      {% endif %}
    </div>
  </div>
</div>
<script>
function conferma(btn) {
  btn.parentElement.innerHTML = '<span style="color: #2e7d32; font-weight: bold; font-size: 13px;">✅ Confermato con successo</span>';
}

function proponiAltroOrario(tipo) {
  const orario = prompt("Inserisci l'orario alternativo da proporre al cliente (es. 21:15 o 22:00):", "21:30");
  if (!orario) return;
  const msg = tipo === 'Domicilio' 
    ? 'Ciao da Pizzeria Viale50! 🍕 Per l\'orario richiesto abbiamo le infornate piene, ma riusciamo a consegnare per le ' + orario + '! Ti va bene lo stesso? Rispondi pure a questo messaggio!'
    : 'Ciao da Pizzeria Viale50! 🍕 Per l\'orario richiesto la sala è al completo, ma abbiamo un bel tavolo libero per le ' + orario + '! Ti andrebbe bene? Rispondi pure a questo messaggio!';
  
  if (navigator.clipboard) {
    navigator.clipboard.writeText(msg);
  }
  alert("📋 Messaggio copiato negli appunti! Puoi inviarlo al cliente:\n\n" + msg);
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, debug=True)
