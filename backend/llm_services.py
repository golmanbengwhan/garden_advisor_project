# backend/llm_services.py

# Saker vi behöver (som verktyg från en verktygslåda)
import os  # För att läsa hemligheter som vi gav Render
from fastapi import HTTPException # För att berätta om något går fel
from google.cloud import aiplatform # Googles verktygslåda för Vertex AI
from vertexai.preview.generative_models import GenerativeModel, Part, GenerationConfig # Specifika verktyg för Gemini
import json # För att förstå svaren från Gemini
import logging # För att skriva en dagbok om vad appen gör

# Importera våra "ritningar" för hur datan ska se ut
# Använder relativ import om models.py är i samma backend-mapp
from .models import LLMDesignOutput, GardenPlanData, PlantData, PathData 

# Ställ in vår dagbok
logger = logging.getLogger(__name__)
# load_dotenv() # Behövs inte på Render, den använder miljövariabler direkt

# ---- Global variabel för vår valda Gemini-modell ----
CHOSEN_GEMINI_MODEL = None # Kommer att sättas i try-blocket nedan

# ---- Säg åt Google-verktygen vilket projekt vi jobbar med ----
try:
    PROJECT_ID = os.getenv("GOOGLE_PROJECT_ID")
    LOCATION = os.getenv("GOOGLE_LOCATION")

    if not PROJECT_ID or not LOCATION:
        logger.error("VIKTIGT: GOOGLE_PROJECT_ID eller GOOGLE_LOCATION är inte satta som miljövariabler på Render!")
    else:
        aiplatform.init(project=PROJECT_ID, location=LOCATION)
        logger.info(f"Pratar med Google Vertex AI i projekt '{PROJECT_ID}' och plats '{LOCATION}'.")

        # HÄR VÄLJER DU DIN SENASTE MODELL!
        # Kontrollera tillgängligheten i din Google Cloud Console för projektet och regionen.
        # Exempel: "gemini-1.5-flash-001" eller "gemini-2.0-flash-001"
        CHOSEN_GEMINI_MODEL = "gemini-2.0-flash-001" # <-- ERSÄTT MED DEN SENASTE MODELLEN DU VERIFIERAT!
        logger.info(f"Vald Gemini-modell för användning: {CHOSEN_GEMINI_MODEL}")

except Exception as e:
    logger.error(f"ALLVARLIGT FEL: Kunde inte starta kopplingen till Vertex AI: {e}", exc_info=True)
    # CHOSEN_GEMINI_MODEL förblir None, vilket kommer att hanteras i funktionerna nedan

# Funktion för att be bild-roboten titta på en bild
async def analyze_image_with_google_llm(image_url: str) -> str:
    logger.info(f"Bild-roboten ska titta på: {image_url}")
    if not image_url:
        return "Ingen bild att titta på!"

    if not CHOSEN_GEMINI_MODEL:
        logger.error("analyze_image_with_google_llm: Vertex AI är inte korrekt initierad (CHOSEN_GEMINI_MODEL är None).")
        return "Fel: AI-tjänsten för bildanalys är inte korrekt konfigurerad."

    try:
        model = GenerativeModel(CHOSEN_GEMINI_MODEL) # Använd den valda modellen
        
        image_part = Part.from_uri(uri=image_url)  # Förutsätter JPEG, kan behöva anpassas

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

    except Exception as e:
        logger.error(f"Aj! Något gick fel när bild-roboten jobbade: {e}", exc_info=True)
        # Returnera ett mer informativt fel till din main.py som kan bli en HTTPException
        return f"Ett tekniskt fel uppstod under bildanalysen: {str(e)[:150]}"


# Funktion för att be text-roboten designa trädgården
async def get_garden_advice_from_google_llm(
    image_analysis_text: str,
    user_location: str,
    user_preferences: str
) -> LLMDesignOutput:
    logger.info(f"Text-roboten ska designa en trädgård. Info: Plats='{user_location}', Bildanalys='{image_analysis_text[:50]}...'")

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
        model = GenerativeModel(CHOSEN_GEMINI_MODEL) # Använd den valda modellen

        svar_fran_roboten = await model.generate_content_async(
            instruktion_till_roboten,
            generation_config=GenerationConfig(
                temperature=0.7, # Lite mer kreativitet
                max_output_tokens=2048,
                # Försök få Gemini att generera JSON direkt. För nyare SDK-versioner kan detta vara:
                # response_mime_type="application/json" 
                # eller via candidate.finish_reason == "SAFETY" etc. och candidate.safety_ratings
            )
        )

        if svar_fran_roboten.candidates and svar_fran_roboten.candidates[0].content.parts:
            json_text_svar = "".join(part.text for part in svar_fran_roboten.candidates[0].content.parts if hasattr(part, 'text')).strip()
            
            if json_text_svar.startswith("```json"):
                json_text_svar = json_text_svar[len("```json"):]
            if json_text_svar.endswith("```"):
                json_text_svar = json_text_svar[:-len("```")]
            json_text_svar = json_text_svar.strip() # Ta bort eventuella extra blanksteg
            
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
        raise HTTPException(status_code=503, detail=f"Ett tekniskt fel uppstod med AI-designen: {str(e)[:150]}")