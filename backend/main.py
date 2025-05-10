from fastapi import FastAPI, HTTPException, File, UploadFile, Form
from fastapi.middleware.cors import CORSMiddleware
import backend.llm_services as llm_services # Ändrat alias för tydlighet
import backend.supabase_services as supabase_services # Ändrat alias för tydlighet
import backend.svg_generator as svg_generator # Ändrat alias för tydlighet
from backend.models import UserInput, AdviceResponse, LLMDesignOutput
import uuid
import logging
from typing import Optional # För UploadFile
import base64 # Importerad för base64-kodning

# Konfigurera loggning
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trädgårdsrådgivare AI API")

# CORS-inställningar
allowed_origins = [
    "https://www.edenpaths.se",
    "https://edenpaths.se",
    "https://garden-advisor-project.onrender.com",
    "http://127.0.0.1:5500",
    "http://localhost:5500",
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["POST", "GET", "OPTIONS"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    logger.info("Root endpoint anropad (health check).")
    return {"message": "Trädgårdsrådgivare AI API är igång!"}

@app.post("/get_advice", response_model=AdviceResponse)
async def get_garden_advice_endpoint(
    location: str = Form(...),
    preferences: str = Form(...),
    imageFile: Optional[UploadFile] = File(None)
):
    request_id = str(uuid.uuid4())
    logger.info(f"Request [{request_id}]: Startar. Plats='{location}', Bild: {'Ja' if imageFile and imageFile.filename else 'Nej'}")

    image_supabase_url: Optional[str] = None
    image_analysis_result: str = "Ingen bildanalys utförd (ingen bild skickad)."
    # Ny variabel för att hålla den faktiska MIME-typen från den uppladdade filen
    actual_image_mime_type: Optional[str] = None

    try:
        if imageFile and imageFile.filename: # Kontrollera också att filename inte är tomt
            if imageFile.size == 0:
                logger.info(f"Request [{request_id}]: Mottagen bildfil har storlek 0, ingen bild behandlas.")
                image_analysis_result = "Bildanalys kunde inte utföras (tom fil)."
            else:
                logger.info(f"Request [{request_id}]: Bearbetar uppladdad bild: {imageFile.filename}, Storlek: {imageFile.size}, Typ: {imageFile.content_type}")
                
                # Spara den faktiska MIME-typen från UploadFile-objektet
                actual_image_mime_type = imageFile.content_type

                unique_filename_stem = f"garden_image_{request_id}"
                contents = await imageFile.read()

                if not contents:
                    logger.warning(f"Request [{request_id}]: Innehållet i den uppladdade filen är tomt efter läsning.")
                    image_analysis_result = "Bildanalys kunde inte utföras (tomt filinnehåll)."
                elif not actual_image_mime_type:
                    logger.warning(f"Request [{request_id}]: MIME-typ saknas för uppladdad fil, kan inte skapa data_url eller analysera.")
                    image_analysis_result = "Bildanalys kunde inte utföras (MIME-typ saknas)."
                else:
                    encoded_string = base64.b64encode(contents).decode('utf-8')
                    data_url = f"data:{actual_image_mime_type};base64,{encoded_string}"
                    
                    # Antag att upload_image_from_data_url i supabase_services.py
                    # har uppdaterats för att returnera (url, mime_type_from_data_url)
                    # eller så använder vi actual_image_mime_type direkt.
                    # För enkelhetens skull, om upload_image_from_data_url bara returnerar URL:
                    temp_url, mime_type_from_upload = await supabase_services.upload_image_from_data_url(data_url, unique_filename_stem)
                    image_supabase_url = temp_url
                    # Vi litar på MIME-typen från den ursprungliga UploadFile om möjligt,
                    # men mime_type_from_upload kan användas som fallback eller för verifiering.
                    # För nu använder vi den direkt från UploadFile.

                    logger.info(f"Request [{request_id}]: Bild uppladdad till: {image_supabase_url}")

                    # ---- VIKTIG ÄNDRING HÄR ----
                    # Anropa analyze_image_with_google_llm med den faktiska MIME-typen
                    image_analysis_result = await llm_services.analyze_image_with_google_llm(
                        image_url=image_supabase_url,
                        actual_mime_type=actual_image_mime_type # Skicka med den korrekta MIME-typen
                    )
                    logger.info(f"Request [{request_id}]: Bildanalys klar: {image_analysis_result[:100]}...") # Logga början av resultatet
        else:
            logger.info(f"Request [{request_id}]: Ingen bildfil skickades med eller filnamn saknas.")


        user_data = UserInput(location=location, preferences=preferences, image_supabase_url=image_supabase_url)
        
        logger.info(f"Request [{request_id}]: Hämtar trädgårdsråd från LLM.")
        llm_output: LLMDesignOutput = await llm_services.get_garden_advice_from_google_llm(
            image_analysis_text=image_analysis_result, # Använd resultatet från bildanalysen
            user_location=user_data.location,
            user_preferences=user_data.preferences
        )
        logger.info(f"Request [{request_id}]: LLM-råd mottaget.")
        
        logger.info(f"Request [{request_id}]: Genererar SVG-plan.")
        svg_plan_str = svg_generator.create_2d_garden_svg(llm_output.garden_plan_data)
        logger.info(f"Request [{request_id}]: SVG-plan genererad.")

        try:
            await supabase_services.save_garden_advice_to_db(
                user_input=user_data.dict(), # Skicka som dict
                image_analysis=image_analysis_result,
                text_advice=llm_output.text_advice,
                svg_plan_str=svg_plan_str,
                image_supabase_url=image_supabase_url
            )
            logger.info(f"Request [{request_id}]: Resultat sparat till DB.")
        except Exception as db_e:
            logger.error(f"Request [{request_id}]: Fel vid sparande till DB (icke-kritiskt): {db_e}", exc_info=True)

        logger.info(f"Request [{request_id}]: Skickar framgångsrikt svar.")
        return AdviceResponse(
            text_advice=llm_output.text_advice,
            svg_plan=svg_plan_str,
            image_analysis_text=image_analysis_result
        )

    except HTTPException as http_exc:
        logger.warning(f"Request [{request_id}]: Hanterat fel (HTTPException): {http_exc.status_code} - {http_exc.detail}")
        raise http_exc
    except Exception as e:
        logger.error(f"Request [{request_id}]: Oväntat serverfel: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Ett oväntat internt fel uppstod (ID: {request_id}). Kontakta support om problemet kvarstår.")

