import os
from supabase import create_client, Client
from dotenv import load_dotenv
from fastapi import HTTPException # För felhantering
import base64
import mimetypes
import logging
from typing import Optional

logger = logging.getLogger(__name__)
load_dotenv()

SUPABASE_URL: str = os.getenv("SUPABASE_URL")
SUPABASE_KEY: str = os.getenv("SUPABASE_KEY")
BUCKET_NAME: str = os.getenv("SUPABASE_BUCKET_NAME", "garden-images")

if not (SUPABASE_URL and SUPABASE_KEY):
    logger.error("Supabase URL eller Key är inte konfigurerad i .env")
    # Du kan välja att kasta ett fel här om Supabase är kritiskt vid start
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


async def upload_image_from_data_url(image_data_url: str, file_name_stem: str) -> str:
    logger.info(f"Försöker ladda upp bild med stamnamn: {file_name_stem}")
    try:
        header, encoded = image_data_url.split(",", 1)
        mime_type = header.split(":")[1].split(";")[0]
        file_extension = mimetypes.guess_extension(mime_type) or ".png"
        image_data = base64.b64decode(encoded)
        
        # Anpassa sökvägen i bucketen om du vill
        full_file_name = f"uploads/{file_name_stem}{file_extension}"

        # Supabase Python client v2.x.x syntax
        response = supabase.storage.from_(BUCKET_NAME).upload(
            path=full_file_name,
            file=image_data,
            file_options={"content-type": mime_type, "upsert": "true"}
        )
        # Vissa versioner av klienten kan kasta ett fel här om det misslyckas,
        # andra kan returnera ett response-objekt som behöver kontrolleras.

        public_url_data = supabase.storage.from_(BUCKET_NAME).get_public_url(full_file_name)
        
        # Hantera olika möjliga returvärden från get_public_url
        public_url = None
        if isinstance(public_url_data, str):
            public_url = public_url_data
        elif isinstance(public_url_data, dict): # Vanligt i äldre versioner
            public_url = public_url_data.get('publicURL', public_url_data.get('publicUrl'))

        if not public_url:
            logger.error(f"Kunde inte hämta public URL för {full_file_name}. Svar från get_public_url: {public_url_data}")
            raise Exception("Misslyckades att hämta public URL från Supabase efter uppladdning.")

        logger.info(f"Bild uppladdad till Supabase: {public_url}")
        return public_url

    except Exception as e:
        logger.error(f"Fel vid uppladdning till Supabase Storage: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Kunde inte ladda upp bilden till molnet: {e}")

async def save_garden_advice_to_db(user_input: dict, image_analysis: str, text_advice: str, svg_plan_str: str, image_supabase_url: Optional[str] = None):
    # ... (samma som tidigare, se till att tabellen "garden_designs" finns) ...
    # Lägg till loggning och felhantering om det behövs mer specifikt här
    logger.info("Försöker spara råd till databasen.")
    try:
        data_to_insert = {
            "user_location": user_input.get("location"),
            "user_preferences": user_input.get("preferences"),
            "image_url": image_supabase_url,
            "image_analysis_result": image_analysis,
            "llm_text_advice": text_advice,
            "svg_plan": svg_plan_str
        }
        response = supabase.table("garden_designs").insert(data_to_insert).execute()
        if response.data:
            logger.info(f"Råd sparat till DB, id: {response.data[0].get('id')}")
            return response.data[0]
        else: # Om insert inte returnerar data eller misslyckas tyst
            logger.warning(f"Inget data returnerades vid sparande till DB, eller så misslyckades det tyst. Response: {response}")
            return None # Eller kasta ett fel om det är kritiskt
    except Exception as e:
        logger.error(f"Fel vid sparande till Supabase DB: {e}", exc_info=True)
        # Välj om detta ska vara ett hårt fel eller bara en varning
        # raise HTTPException(status_code=500, detail="Kunde inte spara rådet i databasen.")
        return None # Låt appen fortsätta om DB-sparande misslyckas (icke-kritiskt)
