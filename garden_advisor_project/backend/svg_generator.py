import svgwrite
from backend.models import GardenPlanData
import logging

logger = logging.getLogger(__name__)

def create_2d_garden_svg(plan_data: GardenPlanData) -> str:
    logger.info(f"Genererar SVG för yta: {plan_data.area_width_cm}x{plan_data.area_height_cm} cm")
    try:
        scale_factor = 1.0 # 1 cm i data = 1 px i SVG
        svg_width = plan_data.area_width_cm * scale_factor
        svg_height = plan_data.area_height_cm * scale_factor

        if svg_width <= 0 or svg_height <= 0:
            logger.warning("Ogiltiga dimensioner för SVG-generering.")
            # Returnera en tom SVG eller en fel-SVG
            return '<svg width="100" height="50" xmlns="http://www.w3.org/2000/svg"><text x="10" y="30" fill="red">Fel: Ogiltiga mått</text></svg>'

        dwg = svgwrite.Drawing(profile='tiny', size=(f"{svg_width}px", f"{svg_height}px"))
        dwg.add(dwg.rect(insert=(0, 0), size=(svg_width, svg_height), fill='lightgreen'))

        if plan_data.paths:
            for path_obj in plan_data.paths:
                # ... (samma som tidigare) ...
                scaled_points = [(p[0] * scale_factor, p[1] * scale_factor) for p in path_obj.points]
                dwg.add(dwg.polygon(points=scaled_points,fill=path_obj.color or "lightgray",stroke='black',stroke_width=1 ))

        if plan_data.plants:
            for plant in plan_data.plants:
                # ... (samma som tidigare, med dynamisk fontstorlek) ...
                center_x = plant.x * scale_factor
                center_y = plant.y * scale_factor
                radius = (plant.diameter / 2) * scale_factor
                color = plant.color_2d or 'green'
                dwg.add(dwg.circle(center=(center_x, center_y), r=radius, fill=color, stroke='darkgreen', stroke_width=1))
                text_x = center_x + radius + 5 
                text_y = center_y + 4          
                dwg.add(dwg.text( plant.name, insert=(text_x, text_y), fill='black', font_size=f"{max(8, int(radius * 0.3))}px" )) # Säkerställ int för font-size

        logger.info("SVG-plan genererad framgångsrikt.")
        return dwg.tostring()
    except Exception as e:
        logger.error(f"Fel vid SVG-generering: {e}", exc_info=True)
        # Returnera en fel-SVG istället för att krascha hela requesten
        return '<svg width="200" height="50" xmlns="http://www.w3.org/2000/svg"><text x="10" y="30" fill="red">Internt fel vid ritning av plan.</text></svg>'
