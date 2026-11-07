"""
bot_voicerestock.py — VoiceRestock AI: ο agent ΚΑΛΕΙ τον πωλητή (Account Manager) για τις προτάσεις
αναπαραγγελίας των πελατών του και δημιουργεί DRAFT στο ERP μετά από ρητή προφορική επιβεβαίωση.

Τρέχει στο VPS του Νίκου (Pipecat + LiveKit SIP → FreePBX → Intertelecom), στη θέση του bot_safevoice.py.
Φωνή: OpenAI gpt-live-1 (φωνή προς φωνή). Εργαλεία: Gemini backend (ClientDelegation) → vr_core.CallSession
→ App API (`docs/CONTRACTS.md`). Ο agent ΔΕΝ μιλά ποτέ απευθείας με το ERP.

    POST http://127.0.0.1:8100/voice/calls  {"salesman": 105}   → εξερχόμενη κλήση στον πωλητή
    GET  http://127.0.0.1:8100/voice/health
    Εισερχόμενες στο 210 (rooms ROOM_PREFIX*): αν καλεί πωλητής από γνωστό αριθμό → ίδια συζήτηση.

Ρυθμίσεις (.env του agent + voicerestock.env): APP_API_URL, SALESMAN_<PRSN>_PHONE, VOICE_ALLOWED_NUMBERS,
VOICE_QUIET_HOURS (π.χ. 21:00-09:00, κενό = χωρίς περιορισμό), VOICE_HTTP_PORT, VOICE_TRIGGER_TOKEN.
"""
import asyncio
import json
import os
import time
from datetime import datetime

import aiohttp
from aiohttp import web
from dotenv import load_dotenv
from google.genai import types as genai_types
from livekit import api
from livekit.api.twirp_client import ServerError as LiveKitServerError
from loguru import logger

from pipecat.frames.frames import (
    BotStartedSpeakingFrame,
    BotStoppedSpeakingFrame,
    EndFrame,
    LLMContextFrame,
    TranscriptionFrame,
    TTSTextFrame,
)
from pipecat.pipeline.pipeline import Pipeline
from pipecat.pipeline.task import PipelineTask
from pipecat.pipeline.worker import PipelineParams
from pipecat.processors.aggregators.llm_context import LLMContext
from pipecat.processors.frame_processor import FrameDirection, FrameProcessor
from pipecat.services.google.llm import GoogleLLMService
from pipecat.services.llm_service import FunctionCallParams
from pipecat.services.openai.live.llm import ClientDelegation, OpenAILiveLLMService, OpenAILiveLLMSettings
from pipecat.transports.livekit.transport import LiveKitParams, LiveKitTransport
from pipecat.turns.user_turn_completion_mixin import UserTurnCompletionConfig
from pipecat.workers.llm.backend_llm_worker import BackendLLMWorker
from pipecat.workers.runner import WorkerRunner

from vr_core import CallSession, OPEN_STATUSES, num_words, suggestion_brief

load_dotenv(override=True)
# Δεύτερο αρχείο ρυθμίσεων μόνο για το VoiceRestock (δεν αγγίζουμε το .env του receptionist).
load_dotenv(os.getenv("VOICERESTOCK_ENV", "voicerestock.env"), override=True)

APP_API_URL = os.getenv("APP_API_URL", "http://127.0.0.1:18000").rstrip("/")
HTTP_HOST = os.getenv("VOICE_HTTP_HOST", "127.0.0.1")     # ΟΧΙ 0.0.0.0: host networking χωρίς firewall
HTTP_PORT = int(os.getenv("VOICE_HTTP_PORT", "8100"))
TRIGGER_TOKEN = os.getenv("VOICE_TRIGGER_TOKEN", "")
QUIET_HOURS = os.getenv("VOICE_QUIET_HOURS", "").strip()
ALLOWED = {"".join(c for c in n if c.isdigit())[-10:] for n in os.getenv("VOICE_ALLOWED_NUMBERS", "").split(",") if n.strip()}

OUTBOUND_TRUNK_ID = os.getenv("LIVEKIT_OUTBOUND_TRUNK_ID")
ROOM_PREFIX = os.getenv("ROOM_PREFIX", "call")
MAX_CONCURRENT_CALLS = int(os.getenv("MAX_CONCURRENT_CALLS", "2"))
RING_TIMEOUT_SECONDS = int(os.getenv("VOICE_RING_TIMEOUT", "35"))
SILENCE_RETRY_SECONDS = 5
CALL_MAX_SECONDS = int(os.getenv("VOICE_CALL_MAX_SECONDS", "420"))
MAX_SPOKEN = int(os.getenv("VOICE_MAX_SUGGESTIONS", "5"))   # πόσες προτάσεις «ξέρει» ο φωνητικός agent ανά κλήση
LOG_TRANSCRIPTS = os.getenv("LOG_TRANSCRIPTS", "0") == "1"
GPT_LIVE_VOICE = os.getenv("GPT_LIVE_VOICE", "marin")
TURN_SHORT_TIMEOUT = float(os.getenv("TURN_SHORT_TIMEOUT", "5.0"))
TURN_LONG_TIMEOUT = float(os.getenv("TURN_LONG_TIMEOUT", "10.0"))
BACKEND_MODEL = os.getenv("BACKEND_MODEL", "gemini-3.1-flash-lite")   # μετρημένο: το γρηγορότερο (HANDOFF gotcha 4)
BACKEND_RETRY = genai_types.HttpRetryOptions(
    attempts=4, initial_delay=0.4, max_delay=3.0, exp_base=2.0, http_status_codes=[408, 429, 500, 502, 503, 504],
)
PHONE_ATTRIBUTE_KEYS = ("sip.phoneNumber", "sip.from", "sip.fromUser", "sip.trunkPhoneNumber")
AGENT_ID_PREFIX = "vr-agent"

http: aiohttp.ClientSession            # ορίζεται στο main()
ACTIVE: dict[str, asyncio.Task] = {}   # room -> κλήση σε εξέλιξη

WAITING_RULES = """\
=== ΟΣΟ ΠΕΡΙΜΕΝΕΙΣ ΤΟ BACKEND ===
Πες ΜΙΑ μόνο φράση από αυτές: «Μια στιγμή.» «Αμέσως.» «Ένα λεπτάκι.» και μετά ΣΩΠΑΣΕ μέχρι να έρθει
η απάντηση. Μην πεις δεύτερη φράση, μην περιγράψεις τι κάνεις, μην επαναλάβεις το όνομα του πελάτη."""


# ---------------------------------------------------------------------------
# App API
# ---------------------------------------------------------------------------
def digits10(phone: str | None) -> str:
    return "".join(c for c in (phone or "") if c.isdigit())[-10:]


def salesman_phones() -> dict[int, str]:
    out = {}
    for k, v in os.environ.items():
        if k.startswith("SALESMAN_") and k.endswith("_PHONE") and v.strip():
            try:
                out[int(k.split("_")[1])] = v.strip()
            except ValueError:
                pass
    return out


def api_request(actor: str):
    async def request(method: str, path: str, body: dict | None = None):
        async with http.request(method, APP_API_URL + path, json=body, headers={"X-Actor": actor},
                                timeout=aiohttp.ClientTimeout(total=20)) as r:
            return r.status, await r.json(content_type=None)
    return request


async def post_call_event(**body):
    async with http.post(APP_API_URL + "/api/calls/events", json=body, headers={"X-Actor": f"voice:{body.get('call_sid')}"},
                         timeout=aiohttp.ClientTimeout(total=5)) as r:
        await r.read()


async def salesman_name(salesman: int) -> str:
    try:
        async with http.get(APP_API_URL + "/api/salesmen", timeout=aiohttp.ClientTimeout(total=5)) as r:
            for s in await r.json(content_type=None):
                if s.get("PRSN") == salesman:
                    return s.get("NAME") or str(salesman)
    except Exception as e:
        logger.error(f"/api/salesmen: {e}")
    return str(salesman)


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------
def live_prompt(session: CallSession | None, name: str, outbound: bool) -> str:
    if session is None:
        return f"""\
Είσαι η ψηφιακή βοηθός της DEMO ΔΙΑΝΟΜΕΣ Α.Ε. και απαντάς στο τηλέφωνο. Μιλάς ΠΑΝΤΑ Ελληνικά.
Αυτή η γραμμή εξυπηρετεί μόνο τους πωλητές της εταιρείας, και ο αριθμός από τον οποίο καλούν δεν
είναι καταχωρισμένος. Πες το ευγενικά σε 1-2 προτάσεις, και ζήτα από το backend να κλείσει την κλήση.
Δεν δίνεις καμία πληροφορία για πελάτες ή παραγγελίες.

{WAITING_RULES}
"""
    open_ = [s for s in session.sugs.values() if s["status"] in OPEN_STATUSES]
    order = {"high": 0, "medium": 1, "low": 2}
    first_out = lambda s: min((l["PREDICTED_DEPLETION_DATE"] or "9999") for l in s["LINES"])  # noqa: E731
    open_.sort(key=lambda s: (order.get(s["urgency"], 3), first_out(s), s["SUGGESTED_DELIVERY_DATE"]))
    # Με πραγματικά δεδομένα ένας πωλητής έχει δεκάδες προτάσεις: στο τηλέφωνο μόνο οι πιο επείγουσες.
    # Οι υπόλοιπες μένουν στο dashboard (και ο server επιτρέπει κάθε πρόταση του πωλητή, αν τη ζητήσει).
    spoken, rest = open_[:MAX_SPOKEN], len(open_) - MAX_SPOKEN
    listing = "\n".join(f"{i}. {suggestion_brief(s)}" for i, s in enumerate(spoken, 1)) or "(καμία ανοιχτή πρόταση)"
    if rest > 0:
        listing += (f"\n(Υπάρχουν ακόμα {num_words(rest, feminine=True)} λιγότερο επείγουσες προτάσεις. ΔΕΝ τις διαβάζεις· "
                    "αν ρωτήσει, πες ότι φαίνονται στο dashboard.)")
    who = "Κάνεις ΕΞΕΡΧΟΜΕΝΗ κλήση" if outbound else "Απαντάς σε κλήση"
    start = ("Περίμενε να σου πουν ότι η κλήση απαντήθηκε. Τότε:" if outbound else "Μόλις σου πουν, ξεκίνα:")
    greeting = ("«Καλησπέρα σας, είμαι η ψηφιακή βοηθός της DEMO ΔΙΑΝΟΜΕΣ. Σας καλώ για πελάτες σας που κινδυνεύουν\n"
                "   να ξεμείνουν από εμπόρευμα. Έχετε ένα λεπτό;»" if outbound else
                "«Καλησπέρα σας, είμαι η ψηφιακή βοηθός της DEMO ΔΙΑΝΟΜΕΣ. Έχετε πελάτες που κινδυνεύουν να\n"
                "   ξεμείνουν από εμπόρευμα. Θέλετε να τους δούμε;»")
    return f"""\
Είσαι η ψηφιακή βοηθός της DEMO ΔΙΑΝΟΜΕΣ Α.Ε., χονδρεμπορίου τροφίμων και ποτών (τεχνητή νοημοσύνη, όχι
άνθρωπος). {who} με έναν πωλητή της εταιρείας (όνομα: {name}) για πελάτες του που κινδυνεύουν
να ξεμείνουν από εμπόρευμα. Δεν τον αποκαλείς με το όνομα, εκτός αν σου συστηθεί.
Μιλάς ΠΑΝΤΑ Ελληνικά, στον πληθυντικό ευγενείας, φυσικά και σύντομα: 1-2 προτάσεις κάθε φορά.

=== ΠΡΟΤΑΣΕΙΣ ΤΟΥ ΣΥΣΤΗΜΑΤΟΣ ΠΡΟΒΛΕΨΗΣ (η ΜΟΝΗ σου πηγή, σειρά: πιο επείγον πρώτα) ===
{listing}

Ποσότητες και ημερομηνίες τις λες ΑΚΡΙΒΩΣ με τις λέξεις που είναι γραμμένες εδώ ή που σου δίνει το backend.
ΠΟΤΕ δικούς σου αριθμούς, ποτέ στρογγυλοποίηση, ποτέ υπολογισμούς.

=== ΠΟΡΕΙΑ ΚΛΗΣΗΣ ===
{start}
1. {greeting}
   (Αν στην αρχή ακούσεις «ναι;», «εμπρός», «παρακαλώ», «λέγετε»: σήκωσε το τηλέφωνο. Πες ΑΜΕΣΩΣ το βήμα 1,
   όχι «ακούω».)
2. Αν πει ναι: ξεκίνα από τον πρώτο πελάτη της λίστας. Πες τι τελειώνει και πότε, την πρόταση και την
   παράδοση. Αν έχει πολλά είδη, πες πρώτα τα δύο πιο επείγοντα και ότι υπάρχουν κι άλλα.
   Μετά ρώτα: «Θέλετε να σας πω γιατί, ή να την περάσω;»
   - «Γιατί;» / «από πού βγαίνει;» → ζήτα από το backend την εξήγηση και πες τη σύντομα.
   - Αλλαγή ποσότητας («κάν' τα δεκαπέντε») → ζήτα από το backend να την αλλάξει και πες το αποτέλεσμα
     όπως σου το δίνει. Αν το backend σου δώσει ερώτηση επιβεβαίωσης του αριθμού, κάνε ΑΚΡΙΒΩΣ αυτή.
   - «Πέρασέ τη» / «φτιάξ' την» / «βάλ' τη σε draft» / «εντάξει, προχώρα» → ζήτα από το backend να ετοιμάσει
     την επιβεβαίωση. Διάβασε ΟΛΟΚΛΗΡΗ και ΑΥΤΟΥΣΙΑ την περίληψη που σου δίνει (όλα τα είδη), τελείωσε με την
     ερώτησή της και ΣΤΑΜΑΤΑ να μιλάς. Μην προσθέσεις τίποτα μετά την ερώτηση.
   - ΜΟΝΟ αν ΜΕΤΑ την περίληψη απαντήσει καθαρά «ναι», «ναι, επιβεβαιώνω» ή «σωστά» → ζήτα από το backend να
     δημιουργήσει το draft. Ό,τι είπε ΠΡΙΝ την περίληψη δεν μετράει ως επιβεβαίωση. Σε ασαφή απάντηση
     («οκ;», «μμ», «ε;») ρώτα ξανά. Αν αλλάξει κάτι, κάνε πρώτα την αλλαγή.
   - ΑΠΑΓΟΡΕΥΕΤΑΙ να πεις «προχωράμε», «θα δημιουργηθεί», «καταχωρήθηκε», «έγινε» ή κάτι παρόμοιο για
     παραγγελία, πριν το backend σου πει ότι το ERP δημιούργησε το draft. Τότε το λες με τα λόγια του backend.
     Αν αποτύχει, λες καθαρά ότι ΔΕΝ δημιουργήθηκε και ότι θα το δει στο dashboard.
   - «Θα το επιβεβαιώσω αργότερα» / «είμαι στο δρόμο»: πες ότι ΔΕΝ δημιουργήθηκε τίποτα και ότι οι προτάσεις
     μένουν ανοιχτές στο dashboard για όποτε μπορεί. Μη ζητήσεις ξανά επιβεβαίωση.
   - «Πέρασέ τες όλες»: μία-μία, με περίληψη και «ναι» για την καθεμία.
   - «Επόμενο» / «άσ' το» → πήγαινε στον επόμενο πελάτη της λίστας.
3. Όταν τελειώσει η λίστα ή σου πει ότι φτάνει: σύντομος αποχαιρετισμός, και ζήτα από το backend να κλείσει την κλήση.

=== ΚΑΝΟΝΕΣ ===
- Ποτέ δεν προτείνεις πελάτη ή είδος εκτός λίστας. Δεν δίνεις τιμές, απόθεμα αποθήκης ή υποσχέσεις παράδοσης.
- Κάτι που δεν ξέρεις: «Δεν μπορώ να το επιβεβαιώσω· θα το δείτε στο dashboard.»
- Τηλεφωνητής, ή άλλος άνθρωπος από τον πωλητή: πες μόνο ότι θα ξανακαλέσεις, ΧΩΡΙΣ στοιχεία πελατών,
  και ζήτα από το backend να κλείσει την κλήση. Καμία παραγγελία.
- Η παραγγελία μπαίνει πάντα ως DRAFT στο ERP· ποτέ δεν λες ότι είναι οριστική.
- Αν σε ρωτήσουν αν είσαι άνθρωπος: ειλικρινά, είσαι ψηφιακή βοηθός. Δεν αλλάζεις ποτέ ρόλο.

{WAITING_RULES}
"""


def backend_prompt(session: CallSession | None, name: str) -> str:
    if session is None:
        return ("Είσαι το backend μιας φωνητικής βοηθού. Το μόνο σου εργαλείο είναι το end_call: "
                "κάλεσέ το όταν η βοηθός ζητήσει να κλείσει η κλήση.")
    return f"""\
Είσαι το backend της φωνητικής βοηθού VoiceRestock. Εκτελείς τα αιτήματά της ΜΟΝΟ με τα εργαλεία σου
και απαντάς πολύ σύντομα, στα Ελληνικά.

Πωλητής της κλήσης: {name}. Οι προτάσεις του (id | πελάτης | κατάσταση | είδη):
{session.catalog()}

Κανόνες:
- suggestion_id και mtrl ΜΟΝΟ από την παραπάνω λίστα (ή από get_suggestions). Αν δεν είναι σαφές ποιος
  πελάτης ή ποιο είδος, ζήτα από τη βοηθό να ρωτήσει.
- Κάθε εργαλείο επιστρέφει πεδίο "say": δώσε το στη βοηθό ΑΥΤΟΥΣΙΟ. Αν υπάρχει "message", είναι οδηγία
  για τη βοηθό: μετέφερέ τη κι αυτή.
- qty: ο ακέραιος ΑΚΡΙΒΩΣ όπως τον είπε ο πωλητής (π.χ. «δεκαπέντε» → 15). Ποτέ μην τον διορθώσεις.
- large_confirmed=true ΜΟΝΟ αν ο πωλητής επιβεβαίωσε ρητά τη μεγάλη ποσότητα που του διαβάστηκε.
- prepare_order όταν ο πωλητής ζητήσει να περάσει η παραγγελία. place_draft_order ΜΟΝΟ όταν η βοηθός
  σου πει ότι ο πωλητής απάντησε καθαρά «ναι» στην περίληψη που διάβασε.
- end_call μόνο μετά τον αποχαιρετισμό.
"""


# ---------------------------------------------------------------------------
# Μία τηλεφωνική συνομιλία
# ---------------------------------------------------------------------------
class CallWatch(FrameProcessor):
    """Ζωντανό transcript + μεταβάσεις κατάστασης προς το App API (σελίδα Voice Operations)."""

    def __init__(self, state: dict, session: CallSession | None, tag: str):
        super().__init__()
        self._state, self._session, self._tag = state, session, tag
        self._said: list[str] = []
        self._spaces = False

    def _post(self, **kw):
        if self._session:
            asyncio.create_task(self._session.event(**kw))

    async def process_frame(self, frame, direction: FrameDirection):
        await super().process_frame(frame, direction)
        if isinstance(frame, BotStartedSpeakingFrame):
            self._state["spoke"] = True
            if self._state["answered"] and self._session and self._session.status in ("connected", "dialing"):
                self._session.status = "greeted"
                self._post(type="status", status="greeted")
        elif isinstance(frame, TTSTextFrame):
            self._said.append(frame.text)
            self._spaces = getattr(frame, "includes_inter_frame_spaces", False)
        elif isinstance(frame, BotStoppedSpeakingFrame) and self._said:
            said = " ".join(("" if self._spaces else " ").join(self._said).split())
            self._said.clear()
            logger.info(f"{self._tag} Agent: {said}" if LOG_TRANSCRIPTS else f"{self._tag} Agent μίλησε ({len(said)} χαρ.)")
            self._post(type="transcript", role="agent", text=said)
        await self.push_frame(frame, direction)


class UserWatch(CallWatch):
    """Τα λόγια του πωλητή. Το gpt-live τα στέλνει ως TranscriptionFrame ΠΡΟΣ ΤΑ ΠΙΣΩ (UPSTREAM), άρα αυτός ο
    observer μπαίνει ΠΡΙΝ από το live_llm — ο CallWatch στο τέλος της ροής δεν τα βλέπει ποτέ."""

    async def process_frame(self, frame, direction: FrameDirection):
        await FrameProcessor.process_frame(self, frame, direction)
        if isinstance(frame, TranscriptionFrame) and frame.text.strip():
            logger.info(f"{self._tag} Πωλητής: {frame.text}" if LOG_TRANSCRIPTS else f"{self._tag} Πωλητής μίλησε")
            self._post(type="transcript", role="user", text=frame.text.strip())
            if self._session and self._session.status == "greeted":
                self._session.status = "discussing"
                self._post(type="status", status="discussing")
        await self.push_frame(frame, direction)


def _token(room_name: str, identity: str) -> str:
    return (api.AccessToken(os.getenv("LIVEKIT_API_KEY"), os.getenv("LIVEKIT_API_SECRET"))
            .with_identity(identity).with_name("VoiceRestock")
            .with_grants(api.VideoGrants(room_join=True, room=room_name)).to_jwt())


def build_tools(session: CallSession | None, end_call):
    """Τα εργαλεία του backend LLM. Κάθε ένα = μία μέθοδος του CallSession (κανόνες ασφαλείας εκεί)."""

    async def run(params: FunctionCallParams, coro):
        try:
            result = await coro
        except Exception as e:
            logger.error(f"[{session.call_id}] εργαλείο: {e!r}")
            result = {"status": "error", "message": "Πρόβλημα επικοινωνίας με το σύστημα. Δεν έγινε καμία αλλαγή."}
        await params.result_callback(result)

    async def get_suggestions(params: FunctionCallParams):
        """Οι ανοιχτές προτάσεις αναπαραγγελίας των πελατών του πωλητή, πιο επείγουσες πρώτα."""
        await run(params, session.overview())

    async def explain_suggestion(params: FunctionCallParams, suggestion_id: str):
        """Εξήγηση της πρότασης (ρυθμός κατανάλωσης, τελευταία παραλαβή, εποχικότητα, προσφορά) από τα δεδομένα του συστήματος.

        Args:
            suggestion_id: Το id της πρότασης, π.χ. SUG-1004-001.
        """
        await run(params, session.explain(suggestion_id))

    async def change_quantity(params: FunctionCallParams, suggestion_id: str, mtrl: int, qty: int,
                              large_confirmed: bool = False):
        """Αλλάζει την ποσότητα ενός είδους της πρότασης. Δεν δημιουργεί παραγγελία.

        Args:
            suggestion_id: Το id της πρότασης.
            mtrl: Ο κωδικός MTRL του είδους, από τη λίστα.
            qty: Η νέα ποσότητα, ακέραιος, ακριβώς όπως την είπε ο πωλητής.
            large_confirmed: true μόνο αν ο πωλητής επιβεβαίωσε ρητά μια ποσότητα που του ξαναδιαβάστηκε ως μεγάλη.
        """
        await run(params, session.change_quantity(suggestion_id, mtrl, qty, large_confirmed))

    async def prepare_order(params: FunctionCallParams, suggestion_id: str):
        """Ετοιμάζει την ακριβή περίληψη που πρέπει να επιβεβαιώσει ο πωλητής. Δεν δημιουργεί παραγγελία.

        Args:
            suggestion_id: Το id της πρότασης που ο πωλητής ζήτησε να περάσει.
        """
        await run(params, session.prepare_order(suggestion_id))

    async def place_draft_order(params: FunctionCallParams, suggestion_id: str):
        """Δημιουργεί DRAFT παραγγελία στο ERP. ΜΟΝΟ αφού ο πωλητής απάντησε καθαρά «ναι» στην περίληψη του prepare_order.

        Args:
            suggestion_id: Το id της πρότασης που επιβεβαιώθηκε.
        """
        await run(params, session.place_draft_order(suggestion_id))

    if session is None:
        return [end_call]
    return [get_suggestions, explain_suggestion, change_quantity, prepare_order, place_draft_order, end_call]


async def converse(room_name: str, session: CallSession | None, name: str, phone: str | None, *, outbound: bool):
    tag = f"[{room_name}]"
    state = {"answered": not outbound, "spoke": False}
    task: PipelineTask | None = None

    async def tell(instruction: str):
        if task is not None:
            await task.queue_frame(LLMContextFrame(context=LLMContext(messages=[{"role": "developer", "content": instruction}])))

    async def end_call(params: FunctionCallParams):
        """Τερματίζει την κλήση. Μόνο αφού ειπωθεί ο αποχαιρετισμός."""
        await params.result_callback({"status": "ending"})
        await asyncio.sleep(4)
        if task is not None:
            await task.queue_frame(EndFrame())

    backend = BackendLLMWorker(
        llm=GoogleLLMService(api_key=os.getenv("GOOGLE_API_KEY"), model=BACKEND_MODEL,
                             http_options=genai_types.HttpOptions(retry_options=BACKEND_RETRY), retry_on_timeout=True),
        context=LLMContext(messages=[{"role": "system", "content": backend_prompt(session, name)}],
                           tools=build_tools(session, end_call)),
        name="gemini-backend",
    )
    live_llm = OpenAILiveLLMService(
        api_key=os.getenv("OPENAI_API_KEY"),
        settings=OpenAILiveLLMSettings(
            model="gpt-live-1", voice=GPT_LIVE_VOICE, system_instruction=live_prompt(session, name, outbound),
            filter_incomplete_user_turns=True,
            user_turn_completion_config=UserTurnCompletionConfig(
                incomplete_short_timeout=TURN_SHORT_TIMEOUT, incomplete_long_timeout=TURN_LONG_TIMEOUT),
        ),
        delegation=ClientDelegation(backend=backend),
    )
    transport = LiveKitTransport(
        url=os.getenv("LIVEKIT_URL"), token=_token(room_name, f"{AGENT_ID_PREFIX}-{room_name}"), room_name=room_name,
        params=LiveKitParams(audio_in_enabled=True, audio_out_enabled=True),
    )
    task = PipelineTask(
        Pipeline([transport.input(), UserWatch(state, session, tag), live_llm, transport.output(),
                  CallWatch(state, session, tag)]),
        params=PipelineParams(audio_in_sample_rate=16000, audio_out_sample_rate=24000),
    )

    @transport.event_handler("on_first_participant_joined")
    async def _joined(_transport, participant_id):
        if not outbound:
            await tell("Ο συνομιλητής είναι στη γραμμή. Ξεκίνα ΤΩΡΑ από το βήμα 1." if session
                       else "Ο συνομιλητής είναι στη γραμμή. Μίλησε ΤΩΡΑ.")

    @transport.event_handler("on_participant_left")
    async def _left(_transport, participant_id, reason):
        logger.info(f"{tag} Αποχώρησε {participant_id} ({reason}) -- τέλος κλήσης")
        await task.queue_frame(EndFrame())

    runner = WorkerRunner()

    @task.event_handler("on_pipeline_finished")
    async def _finished(*_args):
        for obj, meth in ((backend, "stop"), (runner, "end"), (runner, "cancel")):
            fn = getattr(obj, meth, None)
            if fn is None:
                continue
            try:
                res = fn()
                if asyncio.iscoroutine(res):
                    await res
                if obj is runner:
                    break
            except Exception as e:
                logger.error(f"{tag} {meth}(): {e}")

    await runner.add_workers(task)
    run = asyncio.create_task(asyncio.wait_for(runner.run(), timeout=CALL_MAX_SECONDS))

    if outbound:
        await asyncio.sleep(2)  # ο agent μπαίνει στο δωμάτιο πριν χτυπήσει το τηλέφωνο
        if session:
            await session.set_status("dialing")
        try:
            async with api.LiveKitAPI() as lk:
                await asyncio.wait_for(lk.sip.create_sip_participant(api.CreateSIPParticipantRequest(
                    room_name=room_name, sip_trunk_id=OUTBOUND_TRUNK_ID, sip_call_to=phone,
                    participant_identity="salesman", participant_name=name, wait_until_answered=True,
                )), timeout=RING_TIMEOUT_SECONDS)
            state["answered"] = True
            logger.info(f"{tag} Ο πωλητής σήκωσε")
            if session:
                await session.set_status("connected")
            await tell("Η κλήση απαντήθηκε. Ξεκίνα ΤΩΡΑ από το βήμα 1.")
            for attempt in (1, 2):   # το live μοντέλο σπάνια αγνοεί το πρώτο σήμα
                await asyncio.sleep(SILENCE_RETRY_SECONDS)
                if state["spoke"]:
                    break
                logger.warning(f"{tag} Ο agent δεν μίλησε μετά την απάντηση -- επανάληψη {attempt}")
                await tell("Ο πωλητής είναι στη γραμμή και περιμένει. Μίλησε ΤΩΡΑ: ξεκίνα από το βήμα 1.")
        except Exception as e:
            logger.info(f"{tag} Δεν σήκωσε: {type(e).__name__} {e}")
            if session:
                await session.set_status("failed", text="Δεν απάντησε")
            try:
                async with api.LiveKitAPI() as lk:
                    await lk.room.remove_participant(api.RoomParticipantIdentity(room=room_name, identity="salesman"))
            except Exception:
                pass
            await task.queue_frame(EndFrame())

    try:
        await run
    except asyncio.TimeoutError:
        logger.error(f"{tag} Η κλήση ξεπέρασε τα {CALL_MAX_SECONDS}s -- τερματισμός")
    except Exception as e:
        logger.error(f"{tag} Σφάλμα κλήσης: {e}")
    finally:
        try:
            async with api.LiveKitAPI() as lk:
                await lk.room.delete_room(api.DeleteRoomRequest(room=room_name))
        except Exception:
            pass
        if session and session.status != "failed":
            await session.set_status("ended")
        logger.info(f"{tag} Τέλος κλήσης. Drafts: {list(session.drafts.values()) if session else []}")


# ---------------------------------------------------------------------------
# Εξερχόμενες: POST /voice/calls
# ---------------------------------------------------------------------------
def in_quiet_hours(now: datetime | None = None) -> bool:
    if not QUIET_HOURS or "-" not in QUIET_HOURS:
        return False
    now = (now or datetime.now()).strftime("%H:%M")
    start, end = (x.strip() for x in QUIET_HOURS.split("-", 1))
    return (start <= now or now < end) if start > end else (start <= now < end)


def _json(status: int, body: dict) -> web.Response:
    return web.json_response(body, status=status, dumps=lambda o: json.dumps(o, ensure_ascii=False))


@web.middleware
async def cors(request: web.Request, handler):
    resp = web.Response(status=204) if request.method == "OPTIONS" else await handler(request)
    resp.headers["Access-Control-Allow-Origin"] = "*"
    resp.headers["Access-Control-Allow-Methods"] = "GET,POST,OPTIONS"
    resp.headers["Access-Control-Allow-Headers"] = "Content-Type,X-Voice-Token"
    return resp


async def http_health(_request):
    return _json(200, {"ok": True, "active_calls": sorted(ACTIVE), "quiet_hours": in_quiet_hours(),
                       "salesmen_with_phone": sorted(salesman_phones())})


async def http_calls(request: web.Request):
    if TRIGGER_TOKEN and request.headers.get("X-Voice-Token") != TRIGGER_TOKEN:
        return _json(401, {"error": "unauthorized", "message": "λάθος X-Voice-Token"})
    try:
        salesman = int((await request.json())["salesman"])
    except Exception:
        return _json(400, {"error": "bad_request", "message": 'body: {"salesman": <PRSN>}'})
    phone = salesman_phones().get(salesman)
    if not phone:
        return _json(400, {"error": "no_phone", "message": f"Δεν έχει οριστεί SALESMAN_{salesman}_PHONE"})
    if digits10(phone) not in ALLOWED:
        return _json(403, {"error": "not_allowed", "message": "Ο αριθμός δεν είναι στο VOICE_ALLOWED_NUMBERS"})
    if in_quiet_hours():
        return _json(409, {"error": "quiet_hours", "message": f"Ώρες ησυχίας ({QUIET_HOURS})"})
    if len(ACTIVE) >= MAX_CONCURRENT_CALLS or any(r.startswith(f"vr-{salesman}-") for r in ACTIVE):
        return _json(409, {"error": "busy", "message": "Υπάρχει ήδη κλήση σε εξέλιξη"})
    room = f"vr-{salesman}-{int(time.time())}"
    session = CallSession(api_request(f"voice:{room}"), salesman, room, on_event=post_call_event)
    try:
        open_ = await session.load()
    except Exception as e:
        return _json(502, {"error": "app_api", "message": str(e)})
    if not open_:
        return _json(409, {"error": "nothing_to_discuss", "message": "Ο πωλητής δεν έχει ανοιχτές προτάσεις"})
    await session.set_status("queued", suggestion_id=open_[0]["id"])
    name = await salesman_name(salesman)
    ACTIVE[room] = asyncio.create_task(converse(room, session, name, phone, outbound=True))
    ACTIVE[room].add_done_callback(lambda _t: ACTIVE.pop(room, None))
    logger.info(f"[{room}] Εξερχόμενη προς πωλητή {salesman} ({len(open_)} προτάσεις)")
    return _json(202, {"call_sid": room, "status": "queued", "suggestions": len(open_)})


# ---------------------------------------------------------------------------
# Εισερχόμενες στο 210: ο πωλητής καλεί από γνωστό αριθμό
# ---------------------------------------------------------------------------
def _phone_of(participant) -> str | None:
    attrs = dict(getattr(participant, "attributes", {}) or {})
    for k in PHONE_ATTRIBUTE_KEYS:
        if attrs.get(k):
            return attrs[k]
    ident = getattr(participant, "identity", "") or ""
    return ident[4:] if ident.startswith("sip_") else None


async def handle_inbound(room_name: str):
    phone = None
    for _ in range(4):
        try:
            async with api.LiveKitAPI() as lk:
                res = await lk.room.list_participants(api.ListParticipantsRequest(room=room_name))
            phone = next((p for p in map(_phone_of, res.participants) if p), None)
            if phone:
                break
        except Exception as e:
            logger.error(f"[{room_name}] Αριθμός καλούντα: {e}")
        await asyncio.sleep(0.7)
    salesman = next((sid for sid, p in salesman_phones().items()
                     if digits10(p) and digits10(p) == digits10(phone) and digits10(p) in ALLOWED), None)
    session, name = None, ""
    if salesman is not None:
        session = CallSession(api_request(f"voice:{room_name}"), salesman, room_name, on_event=post_call_event)
        try:
            await session.load()
            name = await salesman_name(salesman)
            await session.set_status("connected")
        except Exception as e:
            logger.error(f"[{room_name}] App API: {e}")
            session = None
    logger.info(f"[{room_name}] Εισερχόμενη: {'πωλητής ' + str(salesman) if session else 'άγνωστος αριθμός'}")
    await converse(room_name, session, name, phone, outbound=False)


async def watch_inbound():
    served: set[str] = set()
    async with api.LiveKitAPI() as lk:
        while True:
            try:
                rooms = await lk.room.list_rooms(api.ListRoomsRequest())
                existing = {r.name for r in rooms.rooms if r.name.startswith(ROOM_PREFIX)}
                served &= existing
                for name in existing:
                    if name in ACTIVE or name in served or len(ACTIVE) >= MAX_CONCURRENT_CALLS:
                        continue
                    try:
                        parts = await lk.room.list_participants(api.ListParticipantsRequest(room=name))
                    except LiveKitServerError:
                        continue
                    if any(not p.identity.startswith(AGENT_ID_PREFIX) for p in parts.participants):
                        served.add(name)
                        ACTIVE[name] = asyncio.create_task(handle_inbound(name))
                        ACTIVE[name].add_done_callback(lambda _t, n=name: ACTIVE.pop(n, None))
            except Exception as e:
                logger.error(f"Σφάλμα αναζήτησης εισερχόμενων: {e}")
            await asyncio.sleep(3)


async def main():
    global http
    if not OUTBOUND_TRUNK_ID:
        raise SystemExit("Λείπει LIVEKIT_OUTBOUND_TRUNK_ID στο .env")
    async with aiohttp.ClientSession() as http:
        app = web.Application(middlewares=[cors])
        app.add_routes([web.get("/voice/health", http_health), web.post("/voice/calls", http_calls),
                        web.options("/voice/calls", http_health)])
        runner = web.AppRunner(app)
        await runner.setup()
        await web.TCPSite(runner, HTTP_HOST, HTTP_PORT).start()
        logger.info(f"VoiceRestock σε αναμονή: http://{HTTP_HOST}:{HTTP_PORT}/voice/calls · App API {APP_API_URL} · "
                    f"πωλητές με τηλέφωνο {sorted(salesman_phones())} · ώρες ησυχίας {QUIET_HOURS or 'καμία'}")
        await watch_inbound()


if __name__ == "__main__":
    asyncio.run(main())
