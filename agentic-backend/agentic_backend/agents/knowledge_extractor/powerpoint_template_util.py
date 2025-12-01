import re

from pptx import Presentation


def fill_slide_from_json_schema(ppt_path, json_schema, slide_number, output_path):
    """
    Remplit les placeholders texte d'un slide PowerPoint avec les descriptions
    provenant d'un JSON Schema.

    Params:
        ppt_path (str): Chemin du fichier PPTX source.
        json_schema (dict): Le JSON Schema sous forme de dict Python.
        slide_number (int): Numéro du slide (1-based).
        output_path (str): Destination du PPTX modifié.
    """

    prs = Presentation(ppt_path)

    # Support 1-based slide numbering
    slide = prs.slides[slide_number - 1]

    # On extrait toutes les propriétés et leurs descriptions
    schema_properties = json_schema.get("properties", {})

    # Exemple: { "name": {"type": "string", "description": "..."} }
    schema_map = {
        prop: data.get("description", "") for prop, data in schema_properties.items()
    }

    # Pattern: {name}, {email}, {phone}, etc.
    pattern = re.compile(r"\{([^}]+)\}")

    # Parcourir toutes les shapes
    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                text = run.text
                matches = pattern.findall(text)

                for key in matches:
                    if key in schema_map:
                        # Remplacement sans toucher au style
                        text = text.replace(f"{{{key}}}", schema_map[key])

                run.text = text  # Mise à jour du run (style conservé)

    prs.save(output_path)
    return output_path


path_test = "/mnt/c/Users/mahmo/fred/agentic-backend/agentic_backend/academy/04_slide_maker/test_ppt.pptx"
path_test2 = "/mnt/c/Users/mahmo/fred/agentic-backend/agentic_backend/academy/04_slide_maker/test_ppt2.pptx"

enjeuxBesoinsSchema = {
    "type": "object",
    "properties": {
        "contexte": {
            "type": "string",
            "description": "Contexte du projet.",
            "maxLength": 300,
        },
        "missions": {
            "type": "string",
            "description": "Ensemble des missions et objectifs.",
            "maxLength": 300,
        },
        "refCahierCharges": {
            "type": "string",
            "description": "Nom du fichier duquel les données sont exraites.",
        },
    },
}

fill_slide_from_json_schema(path_test, enjeuxBesoinsSchema, 3, path_test2)
