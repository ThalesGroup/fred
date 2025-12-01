import re

from pptx import Presentation


def fill_slide_from_json_schema(ppt_path, json_schema, slide_number, output_path):

    prs = Presentation(ppt_path)

    # Support 1-based slide numbering
    slide = prs.slides[slide_number - 1]

    schema_properties = json_schema.get("properties", {})

    # Exemple: { "name": {"type": "string", "description": "..."} }
    schema_map = {
        prop: data.get("description", "") for prop, data in schema_properties.items()
    }

    # Pattern: {name}, {email}, {phone}, etc.
    pattern = re.compile(r"\{([^}]+)\}")

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        for paragraph in shape.text_frame.paragraphs:
            for run in paragraph.runs:
                text = run.text
                matches = pattern.findall(text)

                for key in matches:
                    if key in schema_map:
                       
                        text = text.replace(f"{{{key}}}", schema_map[key])

                run.text = text  

    prs.save(output_path)
    return output_path
