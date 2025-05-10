from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any, Union

class UserInput(BaseModel):
    location: str
    preferences: str
    image_supabase_url: Optional[str] = None

class PlantData(BaseModel):
    name: str = Field(description="Växtens svenska namn")
    latin_name: Optional[str] = Field(None, description="Växtens latinska namn")
    x: int = Field(description="X-koordinat på 2D-planen i cm")
    y: int = Field(description="Y-koordinat på 2D-planen i cm")
    diameter: int = Field(description="Diameter vid mognad i cm (för 2D-planen)")
    color_2d: Optional[str] = Field("green", description="Färg för växten på 2D-planen")
    height_3d: Optional[Union[float, str]] = Field(None, description="Typisk höjd vid mognad i meter (för framtida 3D), kan vara sträng 'okänd'")

class PathData(BaseModel):
    points: List[tuple[int, int]]
    color: Optional[str] = "lightgray"

class GardenPlanData(BaseModel):
    area_width_cm: int = Field(description="Trädgårdsytans bredd i cm")
    area_height_cm: int = Field(description="Trädgårdsytans höjd i cm")
    plants: List[PlantData]
    paths: Optional[List[PathData]] = None

class LLMDesignOutput(BaseModel):
    text_advice: str
    garden_plan_data: GardenPlanData

class AdviceResponse(BaseModel):
    text_advice: str
    svg_plan: str
    image_analysis_text: Optional[str] = None
