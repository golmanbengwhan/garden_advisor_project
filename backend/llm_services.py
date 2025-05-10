# backend/llm_services.py

# Saker vi behöver (som verktyg från en verktygslåda)
import os  # För att läsa hemligheter som vi gav Render
from fastapi import HTTPException # För att berätta om något går fel
from google.cloud import aiplatform # Googles verktygslåda för Vertex AI
from vertexai.preview.generative_models import GenerativeModel, Part, GenerationConfig # Specifika verktyg för Gemini
import json # För att förstå svaren från Gemini
import logging # För att skriva en dagbok om vad appen gör

# Importera våra "ritningar" för hur datan ska se ut
from backend.models import LLMDesignOutput, GardenPlanData, PlantData, PathData

# Ställ in vår dagbok
logger = logging.getLogger(__name__)
# load_dotenv() # Behövs inte på Render, den använder miljövariabler direkt

# ---- Konfigurera Google Cloud / Gemini ----
# aiplatform.init(project=os.getenv("GOOGLE_PROJECT_ID"), location=os.getenv("GOOGLE_LOCATION"))
# vision_model_name = "gemini-2.0-flash-001"
# text_model_name = "gemini-2.0-flash-001"
# if os.getenv("GOOGLE_GEMINI_API_KEY"):
#    genai.configure(api_key=os.getenv("GOOGLE_GEMINI_API_KEY"))

async def analyze_image_with_google_llm(image_url: str) -> str:
    logger.info(f"Bild-roboten ska titta på: {image_url}")
    if not image_url:
        return "Ingen bild att titta på!"

    try:
        # Hämta vår bild-robot
        model = GenerativeModel(VISION_MODEL_NAME)
        
        # Ge bilden till roboten (den kan titta på bilder direkt från internet-adresser)
        image_part = Part.from_uri(uri=image_url, mime_type="image/jpeg") # Säg att det är en .jpg-bild

        # Vad vi vill att roboten ska leta efter och berätta
        fraga_till_roboten = (
            "Titta noga på den här bilden av en trädgård på svenska. Berätta kort om: "
            "1. Vad ser du för ytor (gräs, sten, rabatt)? "
            "2. Finns det stora saker (hus, staket, stora träd)? "
            "3. Ser det soligt, skuggigt eller mittemellan ut? "
            "4. Ser du några växter du känner igen (gissa inte om du är osäker)? "
            "Fokusera på vad som är viktigt om man ska planera en trädgård där."
        )

        # Skicka bilden och frågan till roboten
        svar_fran_roboten = await model.generate_content_async(
            [image_part, fraga_till_roboten],
            generation_config=GenerationConfig(temperature=0.2, max_output_tokens=500) # Säg åt den att vara försiktig och inte skriva för mycket
        )
        
        # Kolla om roboten svarade något vettigt
        if svar_fran_roboten.candidates and svar_fran_roboten.candidates[0].content.parts:
            text_svar = "".join(part.text for part in svar_fran_roboten.candidates[0].content.parts if hasattr(part, 'text'))
            if text_svar:
                logger.info("Bild-roboten gav ett svar.")
                return text_svar.strip()
        
        logger.warning("Bild-roboten gav ett konstigt eller tomt svar.")
        return "Tyvärr kunde jag inte förstå bilden just nu."

    except Exception as e:
        logger.error(f"Aj! Något gick fel när bild-roboten jobbade: {e}", exc_info=True)
        return f"Ett tekniskt fel med bildanalysen: {str(e)[:100]}"


# Funktion för att be text-roboten designa trädgården
async def get_garden_advice_from_google_llm(
    image_analysis_text: str,
    user_location: str,
    user_preferences: str
) -> LLMDesignOutput:
    logger.info(f"Text-roboten ska designa en trädgård. Info: Plats='{user_location}', Bildanalys='{image_analysis_text[:50]}...'")

    # En lång instruktion till text-roboten
    # Vi ber den specifikt att svara med JSON så vår app förstår det lättare
    instruktion_till_roboten = f"""
    Du är en superduktig trädgårdsdesigner som pratar svenska.
    Här är informationen du har:
    - Plats och växtzon: {user_location}
    - Vad bild-roboten såg: {image_analysis_text}
    - Vad användaren önskar sig: {user_preferences}

    Din uppgift är att svara med en JSON-kod. JSON-koden ska ha två huvuddelar: "text_advice" och "garden_plan_data".

    1.  "text_advice": (Detta ska vara en vanlig text) Skriv en trevlig text som förklarar:
        *   Vilken stil på trädgården du föreslår (t.ex. "mysig stugträdgård", "modern och enkel").
        *   Varför du valde den stilen.
        *   Lite om hur växterna ska placeras.
        *   Några enkla skötselråd.
        *   Kanske förslag på en fin gång eller en bänk.

    2.  "garden_plan_data": (Detta ska vara mer JSON-kod inuti) Här beskriver du planen mer exakt:
        *   "area_width_cm": (Ett tal) Hur bred är trädgården i centimeter (t.ex. 500 om den är 5 meter)? Gör en smart gissning.
        *   "area_height_cm": (Ett tal) Hur djup är trädgården i centimeter (t.ex. 300 om den är 3 meter)? Gör en smart gissning.
        *   "plants": (En lista med växter) Ge förslag på 5-7 växter. För varje växt, skriv:
            *   "name": (Text) Svenskt namn på växten.
            *   "latin_name": (Text, om du kan) Latinskt namn.
            *   "x": (Ett tal) Var på en karta (vänster till höger) växten ska vara, i cm.
            *   "y": (Ett tal) Var på en karta (uppe till nere) växten ska vara, i cm.
            *   "diameter": (Ett tal) Hur bred växten blir när den är stor, i cm.
            *   "color_2d": (Text) Vilken färg den ska ha på vår enkla karta (t.ex. "rosa", "mörkgrön").
            *   "height_3d": (Ett tal eller texten "okänd") Hur hög växten blir i meter.
        *   "paths": (En lista med gångar, kan vara tom) Om du föreslår en gång, beskriv den med:
            *   "points": En lista med hörnens positioner (x,y) i cm.
            *   "color": (Text) Vilken färg gången ska ha på kartan.

    Exempel på hur "garden_plan_data" kan se ut:
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
    Var noga med att din JSON-kod är korrekt skriven med alla kommatecken och måsvingar på rätt ställen!
    """

    try:
        # Hämta vår text-robot
        model = GenerativeModel(TEXT_MODEL_NAME)

        # Skicka instruktionen till text-roboten
        # Vi ber den specifikt att försöka generera JSON.
        svar_fran_roboten = await model.generate_content_async(
            instruktion_till_roboten,
            generation_config=GenerationConfig(
                temperature=0.6, # Lite mer kreativitet än bild-roboten
                max_output_tokens=2048, # Kan behöva skriva mycket
                # Försök få Gemini att generera JSON direkt (kan behöva `response_mime_type` i nyare versioner)
                # response_mime_type="application/json" # Om din SDK-version stöder detta direkt i GenerationConfig
            )
        )

        # Försök tolka robotens svar som JSON
        if svar_fran_roboten.candidates and svar_fran_roboten.candidates[0].content.parts:
            json_text_svar = "".join(part.text for part in svar_fran_roboten.candidates[0].content.parts if hasattr(part, 'text')).strip()
            
            # Ibland kan LLM:er lägga till "```json" och "```" runt JSON-koden. Ta bort det.
            if json_text_svar.startswith("```json"):
                json_text_svar = json_text_svar[7:]
            if json_text_svar.endswith("```"):
                json_text_svar = json_text_svar[:-3]
            
            logger.debug(f"Rå JSON från LLM: {json_text_svar}")

            try:
                # Försök omvandla texten till en Python-dictionary
                llm_data = json.loads(json_text_svar)
            except json.JSONDecodeError as json_e:
                logger.error(f"Kunde inte förstå JSON från text-roboten: {json_e}. Svar var: {json_text_svar}", exc_info=True)
                raise HTTPException(status_code=500, detail="AI:n gav ett svar i ett format som inte kunde tolkas (JSON-fel).")

            # Kontrollera att vi fick de delar vi förväntade oss
            if "text_advice" not in llm_data or "garden_plan_data" not in llm_data:
                logger.error(f"Nödvändiga nycklar saknas i LLM JSON-svar: {llm_data.keys()}")
                raise HTTPException(status_code=500, detail="AI:n gav ett ofullständigt svar (saknar nycklar).")

            # Använd våra "ritningar" (Pydantic-modeller) för att se till att datan ser rätt ut
            try:
                # Konvertera rådata för växter och stigar till våra Pydantic-modeller
                raw_plan_data = llm_data["garden_plan_data"]
                plants_list = [PlantData(**p) for p in raw_plan_data.get("plants", [])]
                paths_list = [PathData(**p) for p in raw_plan_data.get("paths", [])] if raw_plan_data.get("paths") else None

                garden_plan = GardenPlanData(
                    area_width_cm=raw_plan_data.get("area_width_cm", 500), # Defaultvärden om de saknas
                    area_height_cm=raw_plan_data.get("area_height_cm", 300),
                    plants=plants_list,
                    paths=paths_list
                )
                text_advice = str(llm_data["text_advice"])

                logger.info("Text-roboten gav ett bra svar och det kunde förstås.")
                return LLMDesignOutput(text_advice=text_advice, garden_plan_data=garden_plan)

            except Exception as pydantic_e: # Om datan inte matchar våra Pydantic-modeller
                logger.error(f"Fel när Pydantic skulle validera LLM-data: {pydantic_e}. Rådata: {llm_data['garden_plan_data']}", exc_info=True)
                raise HTTPException(status_code=500, detail=f"AI:n gav data i ett oväntat format (valideringsfel): {pydantic_e}")
        
        logger.warning("Text-roboten gav ett konstigt eller tomt svar.")
        raise HTTPException(status_code=503, detail="AI:n kunde inte generera trädgårdsråd just nu.")

    except HTTPException: # Om vi redan har ett bra felmeddelande, skicka det vidare
        raise
    except Exception as e:
        logger.error(f"Aj! Något gick fel när text-roboten jobbade: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail=f"Ett tekniskt fel med AI-designen: {str(e)[:100]}")