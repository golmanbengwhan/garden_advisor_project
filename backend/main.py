from fastapi import FastAPI, HTTPException, File, UploadFile, Form, Depends
from fastapi.middleware.cors import CORSMiddleware
import backend.llm_services as llm
import backend.supabase_services as supabase_db
import backend.svg_generator as svg_gen
from backend.models import UserInput, AdviceResponse, LLMDesignOutput
import uuid
import logging
from typing import Optional # För UploadFile

# Konfigurera loggning
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Trädgårdsrådgivare AI API")

# CORS-inställningar (ANPASSA allowed_origins)
allowed_origins = [
    "https://din-webnode-sida.webnode.se",
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
    logger.info(f"Request [{request_id}]: Startar. Plats='{location}', Bild: {'Ja' if imageFile else 'Nej'}")

    image_supabase_url: Optional[str] = None
    image_analysis_result: str = "Ingen bildanalys utförd (ingen bild skickad)."

    try:
        if imageFile:
            if imageFile.filename == "":
                logger.info(f"Request [{request_id}]: Tomt imageFile-objekt mottaget, ingen bild behandlas.")
            elif imageFile.size == 0:
                 logger.info(f"Request [{request_id}]: Mottagen bildfil har storlek 0, ingen bild behandlas.")
            else:
                logger.info(f"Request [{request_id}]: Bearbetar uppladdad bild: {imageFile.filename}, Storlek: {imageFile.size}")
                file_extension = imageFile.filename.split(".")[-1] if "." in imageFile.filename else "jpg"
                unique_filename_stem = f"garden_image_{request_id}"
                contents = await imageFile.read()
                if not contents:
                    logger.warning(f"Request [{request_id}]: Innehållet i den uppladdade filen är tomt.")
                else:
                    import base64
                    encoded_string = base64.b64encode(contents).decode('utf-8')
                    data_url = f"data:{imageFile.content_type};base64,{encoded_string}"
                    image_supabase_url = await supabase_db.upload_image_from_data_url(data_url, unique_filename_stem)
                    logger.info(f"Request [{request_id}]: Bild uppladdad till: {image_supabase_url}")
                    image_analysis_result = await llm.analyze_image_with_google_llm(image_supabase_url)
                    logger.info(f"Request [{request_id}]: Bildanalys klar.")
        user_data = UserInput(location=location, preferences=preferences, image_supabase_url=image_supabase_url)
        logger.info(f"Request [{request_id}]: Hämtar trädgårdsråd från LLM.")
        llm_output: LLMDesignOutput = await llm.get_garden_advice_from_google_llm(
            image_analysis_text=image_analysis_result,
            user_location=user_data.location,
            user_preferences=user_data.preferences
        )
        logger.info(f"Request [{request_id}]: LLM-råd mottaget.")
        logger.info(f"Request [{request_id}]: Genererar SVG-plan.")
        svg_plan_str = svg_gen.create_2d_garden_svg(llm_output.garden_plan_data)
        logger.info(f"Request [{request_id}]: SVG-plan genererad.")
        try:
            await supabase_db.save_garden_advice_to_db(
                user_input=user_data.dict(),
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
