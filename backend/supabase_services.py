import os
from supabase import create_client, Client
from dotenv import load_dotenv
from fastapi import HTTPException # För felhantering
import base64
import mimetypes
import logging
from typing import Optional, Tuple # Importera Tuple för returtypen

logger = logging.getLogger(__name__)
load_dotenv() # Laddar variabler från .env för lokal utveckling

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "garden-images")

if not (SUPABASE_URL and SUPABASE_KEY):
    logger.error("Supabase URL eller Key är inte konfigurerad i miljövariabler!")
    # I en produktionsmiljö kanske du vill att appen inte startar om dessa saknas.
    # För lokal utveckling kan load_dotenv() ha laddat dem.
    # Om du är säker på att Render har dem, kan detta vara en varning.
    # raise RuntimeError("Supabase URL eller Key måste vara konfigurerade.")

# Initiera Supabase-klienten endast om URL och Key finns
# Detta förhindrar krasch vid uppstart om variabler saknas (t.ex. under lokal testning utan .env)
try:
    if SUPABASE_URL and SUPABASE_KEY:
        supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    else:
        supabase: Client = None # Sätt till None om konfiguration saknas
        logger.warning("Supabase-klienten kunde inte initieras p.g.a. saknade URL/Key.")
except Exception as e:
    logger.error(f"Fel vid initiering av Supabase-klient: {e}")
    supabase: Client = None


async def upload_image_from_data_url(image_data_url: str, file_name_stem: str) -> Tuple[Optional[str], Optional[str]]:
    if not supabase:
        logger.error("Supabase-klienten är inte initierad. Kan inte ladda upp bild.")
        raise HTTPException(status_code=500, detail="Bildlagringstjänsten är inte konfigurerad.")

    logger.info(f"Försöker ladda upp bild med stamnamn: {file_name_stem}")
    try:
        # Extrahera MIME-typ och base64-data från data URL
        # Exempel: "data:image/png;base64,iVBORw0KGgo..."
        header, encoded = image_data_url.split(",", 1)
        mime_type_part = header.split(":")[1] # "image/png;base64"
        mime_type = mime_type_part.split(";")[0] # "image/png"

        file_extension = mimetypes.guess_extension(mime_type)
        if not file_extension:
            logger.warning(f"Kunde inte gissa filändelse för MIME-typ: {mime_type}. Använder '.png'.")
            file_extension = ".png"
        
        image_data = base64.b64decode(encoded)
        
        # Skapa ett unikt filnamn med korrekt filändelse
        full_file_name = f"uploads/{file_name_stem}{file_extension}"

        logger.info(f"Laddar upp {full_file_name} till bucket '{BUCKET_NAME}' med MIME-typ '{mime_type}'.")

        # Supabase Python client v2.x.x syntax
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=full_file_name,
            file=image_data,
            file_options={"content-type": mime_type, "upsert": "true"} # upsert: true skriver över om filen finns
        )
        # I Supabase Python client v2, om uppladdningen misslyckas, kastas ett undantag (t.ex. StorageApiError).
        # Om det lyckas, innehåller response oftast bara metadata eller är None, så vi behöver inte kolla response.data här.

        # Hämta den publika URL:en till den uppladdade filen
        public_url_data = supabase.storage.from_(BUCKET_NAME).get_public_url(full_file_name)
        
        public_url = None
        if isinstance(public_url_data, str): # Nyare klienter returnerar oftast strängen direkt
            public_url = public_url_data
        # Hantering för äldre klientversioner eller oväntade returvärden (mindre troligt nu)
        elif isinstance(public_url_data, dict) and 'publicURL' in public_url_data:
            public_url = public_url_data['publicURL']
        elif isinstance(public_url_data, dict) and 'publicUrl' in public_url_data:
            public_url = public_url_data['publicUrl']


        if not public_url:
            logger.error(f"Kunde inte hämta public URL för {full_file_name} efter uppladdning. Svar från get_public_url: {public_url_data}")
            # Det är bättre att kasta ett fel här om URL:en är kritisk
            raise Exception("Misslyckades att hämta public URL från Supabase efter uppladdning.")

        logger.info(f"Bild uppladdad till Supabase: {public_url} med MIME-typ: {mime_type}")
        return public_url, mime_type # ---- VIKTIG ÄNDRING: Returnera både URL och MIME-typ ----

    except Exception as e:
        logger.error(f"Fel vid uppladdning till Supabase Storage: {e}", exc_info=True)
        # Skicka tillbaka ett mer generellt fel till klienten istället för detaljer
        raise HTTPException(status_code=500, detail=f"Kunde inte ladda upp bilden till molnet.")


async def save_garden_advice_to_db(user_input: dict, image_analysis: str, text_advice: str, svg_plan_str: str, image_supabase_url: Optional[str] = None):
    if not supabase:
        logger.error("Supabase-klienten är inte initierad. Kan inte spara råd till DB.")
        # Du kan välja att returnera None tyst eller kasta ett fel
        # beroende på hur kritiskt DB-sparandet är.
        return None 

    logger.info("Försöker spara råd till databasen.")
    try:
        data_to_insert = {
            # Se till att dessa nycklar exakt matchar dina kolumnnamn i Supabase-tabellen 'garden_designs'
            "user_location": user_input.get("location"),
            "user_preferences": user_input.get("preferences"),
            "image_url": image_supabase_url, # Kommer från upload_image_from_data_url
            "image_analysis_result": image_analysis,
            "llm_text_advice": text_advice,
            "svg_plan": svg_plan_str
            # 'created_at' och 'id' hanteras troligen automatiskt av Supabase
        }
        response = supabase.table("garden_designs").insert(data_to_insert).execute()
        
        # Kontrollera om data faktiskt returnerades och om det finns ett id
        if response.data and len(response.data) > 0 and response.data[0].get('id'):
            logger.info(f"Råd sparat till DB, id: {response.data[0].get('id')}")
            return response.data[0] # Returnera den sparade raden (eller dess id)
        else:
            # Detta kan hända om insert lyckas men inte returnerar data,
            # eller om det finns ett tyst fel (mindre vanligt med nyare klienter som kastar undantag).
            # PostgREST API returnerar oftast den infogade datan.
            logger.warning(f"Inget data (eller inget id) returnerades vid sparande till DB, eller så misslyckades det tyst. Response: {response}")
            # Du kan behöva undersöka `response.error` om det finns
            if hasattr(response, 'error') and response.error:
                 logger.error(f"Supabase DB insert error: {response.error}")
            return None # Eller kasta ett fel om det är kritiskt

    except Exception as e:
        logger.error(f"Fel vid sparande till Supabase DB: {e}", exc_info=True)
        # Välj om detta ska vara ett hårt fel som stoppar flödet eller bara en varning.
        # Om DB-sparande är kritiskt, kasta ett HTTPException:
        # raise HTTPException(status_code=500, detail="Kunde inte spara rådet i databasen.")
        return None # Låt appen fortsätta om DB-sparande misslyckas (om det är icke-kritiskt)
