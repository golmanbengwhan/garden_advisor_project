# backend/llm_services.py

import os
from fastapi import HTTPException
from google.cloud import aiplatform
from vertexai.preview.generative_models import GenerativeModel, Part, GenerationConfig
import json
import logging
import httpx # Importera httpx för att hämta bilddata

# Importera Pydantic-modeller
from .models import LLMDesignOutput, GardenPlanData, PlantData, PathData

logger = logging.getLogger(__name__)

# Global variabel för vald Gemini-modell
CHOSEN_GEMINI_MODEL = None
GOOGLE_PROJECT_ID_USED = None # För loggning
GOOGLE_LOCATION_USED = None # För loggning

try:
    PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
    LOCATION = os.getenv("GOOGLE_LOCATION")
    GOOGLE_PROJECT_ID_USED = PROJECT_ID 
    GOOGLE_LOCATION_USED = LOCATION 

    if not PROJECT_ID or not LOCATION:
        logger.error("VIKTIGT: GOOGLE_PROJECT_ID eller GOOGLE_LOCATION är inte satta som miljövariabler på Render!")
    else:
        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Försöker prata med Google Vertex AI i projekt '{PROJECT_ID}' och plats '{LOCATION}'.")

        # HÄR VÄLJER DU DIN SENASTE MODELL!
        # VERIFIERA DETTA EXAKTA MODELL-ID I DIN GOOGLE CLOUD CONSOLE (Vertex AI > Model Garden)
        # FÖR DITT PROJEKT 'tradgardsleads' OCH REGION 'europe-north1'.
        CHOSEN_GEMINI_MODEL = "gemini-2.5-flash-preview-04-17"  # <-- UPPDATERAD TILL MODELL-ID FRÅN DOKUMENTATIONEN!
                                                              # VERIFIERA ATT DENNA ÄR TILLGÄNGLIG FÖR DIG!
        
        logger.info(f"Vald Gemini-modell för användning: {CHOSEN_GEMINI_MODEL} (Projekt: {PROJECT_ID}, Plats: {LOCATION})")

except Exception as e:
    logger.error(f"ALLVARLIGT FEL: Kunde inte starta kopplingen till Vertex AI: {e} (Projekt: {GOOGLE_PROJECT_ID_USED}, Plats: {GOOGLE_LOCATION_USED})", exc_info=True)
    # CHOSEN_GEMINI_MODEL förblir None

async def analyze_image_with_google_llm(image_url: str, actual_mime_type: str) -> str:
    logger.info(f"Bild-roboten ({CHOSEN_GEMINI_MODEL if CHOSEN_GEMINI_MODEL else 'Odefinierad modell'}) ska titta på bild från URL: {image_url} med typ: {actual_mime_type}")
    
    if not image_url:
        return "Ingen bild att titta på (URL saknas)!"
    if not actual_mime_type:
        logger.warning("MIME-typ saknas för bildanalys, kan inte fortsätta.")
        return "Fel: Bildinformation är ofullständig (MIME-typ saknas)."
    if not CHOSEN_GEMINI_MODEL:
        logger.error("analyze_image_with_google_llm: Vertex AI är inte korrekt initierad (CHOSEN_GEMINI_MODEL är None).")
        return "Fel: AI-tjänsten för bildanalys är inte korrekt konfigurerad."

    try:
        clean_image_url = image_url.rstrip('?')
        logger.info(f"Rensad bild-URL för hämtning: {clean_image_url}")

        async with httpx.AsyncClient() as client:
            logger.info(f"Försöker hämta bilddata från: {clean_image_url}")
            response = await client.get(clean_image_url)
            response.raise_for_status() 
            image_bytes = response.content
            logger.info(f"Bilddata hämtad, storlek: {len(image_bytes)} bytes.")

        model = GenerativeModel(CHOSEN_GEMINI_MODEL)
        image_part = Part.from_data(data=image_bytes, mime_type=actual_mime_type) 

        fraga_till_roboten = (
            "Titta noga på den här bilden av en trädgård på svenska. Berätta kort om: "
            "1. Vad ser du för ytor (gräs, sten, rabatt)? "
            "2. Finns det stora saker (hus, staket, stora träd)? "
            "3. Ser det soligt, skuggigt eller mittemellan ut? "
            "4. Ser du några växter du känner igen (gissa inte om du är osäker)? "
            "Fokusera på vad som är viktigt om man ska planera en trädgård där."
        )

        svar_fran_roboten = await model.generate_content_async(
            [image_part, fraga_till_roboten],
            generation_config=GenerationConfig(temperature=0.2, max_output_tokens=500)
        )
        
        if svar_fran_roboten.candidates and svar_fran_roboten.candidates[0].content.parts:
            text_svar = "".join(part.text for part in svar_fran_roboten.candidates[0].content.parts if hasattr(part, 'text'))
            if text_svar:
                logger.info("Bild-roboten gav ett svar.")
                return text_svar.strip()
        
        logger.warning(f"Bild-roboten gav ett konstigt eller tomt svar: {svar_fran_roboten}")
        return "Tyvärr kunde jag inte förstå bilden just nu."

    except httpx.HTTPStatusError as http_err:
        logger.error(f"HTTP-fel vid hämtning av bild från Supabase URL ({clean_image_url}): {http_err}", exc_info=True)
        return f"Kunde inte hämta bilden från molnet för analys (HTTP-fel: {http_err.response.status_code})."
    except Exception as e:
        logger.error(f"Aj! Något gick fel när bild-roboten jobbade: {e}", exc_info=True)
        if "Publisher Model" in str(e) or "is not supported" in str(e) or "was not found" in str(e):
             return f"Ett tekniskt fel med AI-bildanalysen: Modellen '{CHOSEN_GEMINI_MODEL}' kunde inte användas. Kontrollera modellnamn och tillgänglighet i Google Cloud. Fel: {str(e)[:100]}"
        return f"Ett tekniskt fel uppstod under bildanalysen: {str(e)[:150]}"


async def get_garden_advice_from_google_llm(
    image_analysis_text: str,
    user_location: str,
    user_preferences: str
) -> LLMDesignOutput:
    logger.info(f"Text-roboten ({CHOSEN_GEMINI_MODEL if CHOSEN_GEMINI_MODEL else 'Odefinierad modell'}) ska designa en trädgård. Info: Plats='{user_location}', Bildanalys='{image_analysis_text[:50]}...'")

    if not CHOSEN_GEMINI_MODEL:
        logger.error("get_garden_advice_from_google_llm: Vertex AI är inte korrekt initierad (CHOSEN_GEMINI_MODEL är None).")
        raise HTTPException(status_code=503, detail="Fel: AI-tjänsten för textgenerering är inte korrekt konfigurerad.")

    instruktion_till_roboten = f"""
    Du är en superduktig trädgårdsdesigner som pratar svenska.
    Här är informationen du har:
    - Plats och växtzon: {user_location}
    - Vad bild-roboten såg: {image_analysis_text}
    - Vad användaren önskar sig: {user_preferences}

    Din uppgift är att svara med en JSON-kod. JSON-koden ska ha två huvuddelar: "text_advice" och "garden_plan_data".

    1.  "text_advice": (Detta ska vara en vanlig text) Skriv en trevlig text som förklarar:
        * Vilken stil på trädgården du föreslår (t.ex. "mysig stugträdgård", "modern och enkel").
        * Varför du valde den stilen.
        * Lite om hur växterna ska placeras.
        * Några enkla skötselråd.
        * Kanske förslag på en fin gång eller en bänk.

    2.  "garden_plan_data": (Detta ska vara mer JSON-kod inuti) Här beskriver du planen mer exakt:
        * "area_width_cm": (Ett tal) Hur bred är trädgården i centimeter (t.ex. 500 om den är 5 meter)? Gör en smart gissning.
        * "area_height_cm": (Ett tal) Hur djup är trädgården i centimeter (t.ex. 300 om den är 3 meter)? Gör en smart gissning.
        * "plants": (En lista med växter) Ge förslag på 5-7 växter. För varje växt, skriv:
            * "name": (Text) Svenskt namn på växten.
            * "latin_name": (Text, valfritt) Latinskt namn.
            * "x": (Ett tal) Var på en karta (vänster till höger, från 0) växten ska vara, i cm.
            * "y": (Ett tal) Var på en karta (uppe till nere, från 0) växten ska vara, i cm.
            * "diameter": (Ett tal) Hur bred växten blir när den är stor, i cm.
            * "color_2d": (Text) Vilken färg den ska ha på vår enkla karta (t.ex. "rosa", "mörkgrön", "lightblue").
            * "height_3d": (Ett tal i meter, eller texten "okänd") Hur hög växten blir.
        * "paths": (En lista med gångar, kan vara tom [{{"points": [[x1,y1],[x2,y2],...], "color": "gray"}}]) Om du föreslår en gång, beskriv den med en lista av punkter (x,y) i cm och en färg.

    Exempel på hur "garden_plan_data" ska se ut (OBS: ge mig bara JSON-objektet, inget extra prat före eller efter):
    ```json
    {{
        "area_width_cm": 700,
        "area_height_cm": 400,
        "plants": [
            {{"name": "Stjärnflocka", "latin_name": "Astrantia major", "x": 100, "y": 150, "diameter": 40, "color_2d": "pink", "height_3d": 0.6}},
            {{"name": "Jättedaggkåpa", "latin_name": "Alchemilla mollis", "x": 200, "y": 250, "diameter": 50, "color_2d": "limegreen", "height_3d": 0.4}}
        ],
        "paths": [
            {{"points": [[0, 350], [700, 350], [700, 380], [0, 380]], "color": "lightgray"}}
        ]
    }}
    ```
    Se till att hela ditt svar är en enda giltig JSON-sträng som börjar med {{ och slutar med }}.
    """

    try:
        model = GenerativeModel(CHOSEN_GEMINI_MODEL)

        svar_fran_roboten = await model.generate_content_async(
            instruktion_till_roboten,
            generation_config=GenerationConfig(
                temperature=0.7,
                max_output_tokens=2048,
            )
        )

        if svar_fran_roboten.candidates and svar_fran_roboten.candidates[0].content.parts:
            json_text_svar = "".join(part.text for part in svar_fran_roboten.candidates[0].content.parts if hasattr(part, 'text')).strip()
            
            if json_text_svar.startswith("```json"):
                json_text_svar = json_text_svar[len("```json"):]
            if json_text_svar.endswith("```"):
                json_text_svar = json_text_svar[:-len("```")]
            json_text_svar = json_text_svar.strip()
            
            logger.debug(f"Rå JSON från LLM: {json_text_svar}")

            try:
                llm_data = json.loads(json_text_svar)
            except json.JSONDecodeError as json_e:
                logger.error(f"Kunde inte förstå JSON från text-roboten: {json_e}. Svar var: {json_text_svar}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"AI:n gav ett svar i ett format som inte kunde tolkas (JSON-fel): {json_text_svar[:200]}")

            if "text_advice" not in llm_data or "garden_plan_data" not in llm_data:
                logger.error(f"Nödvändiga nycklar saknas i LLM JSON-svar: {llm_data.keys()}")
                raise HTTPException(status_code=500, detail="AI:n gav ett ofullständigt svar (saknar nödvändiga delar).")

            try:
                raw_plan_data = llm_data["garden_plan_data"]
                plants_list = [PlantData(**p) for p in raw_plan_data.get("plants", [])]
                paths_list = [PathData(**p) for p in raw_plan_data.get("paths", [])] if raw_plan_data.get("paths") is not None else []

                garden_plan = GardenPlanData(
                    area_width_cm=raw_plan_data.get("area_width_cm", 500),
                    area_height_cm=raw_plan_data.get("area_height_cm", 300),
                    plants=plants_list,
                    paths=paths_list
                )
                text_advice = str(llm_data["text_advice"])

                logger.info("Text-roboten gav ett bra svar och det kunde förstås.")
                return LLMDesignOutput(text_advice=text_advice, garden_plan_data=garden_plan)

            except Exception as pydantic_e:
                logger.error(f"Fel när Pydantic skulle validera LLM-data: {pydantic_e}. Rådata för garden_plan_data: {raw_plan_data}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"AI:n gav data i ett oväntat format (valideringsfel): {str(pydantic_e)[:150]}")
        
        logger.warning(f"Text-roboten gav ett konstigt eller tomt svar: {svar_fran_roboten}")
        raise HTTPException(status_code=503, detail="AI:n kunde inte generera trädgårdsråd just nu.")

    except HTTPException: 
        raise
    except Exception as e:
        logger.error(f"Aj! Något gick fel när text-roboten jobbade: {e}", exc_info=True)
        if "Publisher Model" in str(e) or "is not supported" in str(e) or "was not found" in str(e):
             raise HTTPException(status_code=503, detail=f"Ett tekniskt fel med AI-designen: Modellen '{CHOSEN_GEMINI_MODEL}' kunde inte användas. Kontrollera modellnamn och tillgänglighet i Google Cloud. Fel: {str(e)[:100]}")
        raise HTTPException(status_code=503, detail=f"Ett tekniskt fel uppstod med AI-designen: {str(e)[:150]}")
