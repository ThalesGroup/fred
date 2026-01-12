import logging
import re

from pptx import Presentation

logger = logging.getLogger(__name__)


def fill_slide_from_structured_response(ppt_path, structured_responses, output_path):
    prs = Presentation(ppt_path)
    pattern = re.compile(r"\{([^}]+)\}")

    # Flatten the nested structure into a single dictionary
    flattened_data = {}
    for section_name, section_data in structured_responses.items():
        if isinstance(section_data, dict):
            # Add all nested key-value pairs to the flattened dictionary
            for key, value in section_data.items():
                flattened_data[key] = value
        else:
            # If it's not a dict, keep it as is
            flattened_data[section_name] = section_data

    logger.info(f"Flattened data keys: {list(flattened_data.keys())}")

    # Process only the first slide (slide 0) for single-slide templates
    slide = prs.slides[0]

    for shape in slide.shapes:
        if not shape.has_text_frame:
            continue

        for paragraph in shape.text_frame.paragraphs:  # type: ignore
            # Merge all runs to find complete placeholders (handles split placeholders)
            full_text = "".join(run.text for run in paragraph.runs)

            # Find all placeholders and their positions in the merged text
            placeholder_replacements = {}
            for match in pattern.finditer(full_text):
                key = match.group(1)
                if key in flattened_data:
                    placeholder_replacements[match.start()] = {
                        "end": match.end(),
                        "placeholder": match.group(0),
                        "value": str(flattened_data[key]),
                    }
                else:
                    logger.warning(f"Placeholder '{key}' not found in flattened data")

            if not placeholder_replacements:
                continue

            # Sort placeholders by position to handle multiple placeholders correctly
            sorted_placeholders = sorted(
                placeholder_replacements.items(), key=lambda x: x[0]
            )

            # Process each run and replace placeholder text
            char_position = 0
            for run in paragraph.runs:
                run_start = char_position
                run_end = char_position + len(run.text)
                new_run_text = run.text
                offset = 0  # Track text length changes within this run

                for placeholder_start, replacement in sorted_placeholders:
                    placeholder_end = replacement["end"]

                    # Case 1: Placeholder starts in this run
                    if run_start <= placeholder_start < run_end:
                        local_start = placeholder_start - run_start + offset

                        if placeholder_end <= run_end:
                            # Placeholder is completely within this run
                            placeholder_len = len(replacement["placeholder"])
                            new_run_text = (
                                new_run_text[:local_start]
                                + replacement["value"]
                                + new_run_text[local_start + placeholder_len :]
                            )
                            offset += len(replacement["value"]) - placeholder_len
                        else:
                            # Placeholder spans multiple runs - replace the start
                            new_run_text = (
                                new_run_text[:local_start] + replacement["value"]
                            )

                    # Case 2: This run is in the middle/end of a placeholder
                    elif placeholder_start < run_start < placeholder_end:
                        if placeholder_end >= run_end:
                            # Entire run is part of the placeholder - empty it
                            new_run_text = ""
                        else:
                            # Placeholder ends in this run - keep text after placeholder
                            local_end = placeholder_end - run_start
                            new_run_text = new_run_text[local_end:]

                run.text = new_run_text
                char_position = run_end

    prs.save(output_path)
    return output_path


referenceSchema = {
    "type": "object",
    "properties": {
        "informationsProjet": {
            "type": "object",
            "description": "Informations sur le projet",
            "properties": {
                "nomSociete": {
                    "type": "string",
                    "description": "Le nom de la société",
                    "maxLength": 50,
                },
                "nomProjet": {
                    "type": "string",
                    "description": "Le nom du projet",
                    "maxLength": 50,
                },
                "dateProjet": {
                    "type": "string",
                    "description": "La date de début et de fin du projet",
                },
                "nombrePersonnes": {
                    "type": "string",
                    "description": "Le nombre de personnes",
                },
                "enjeuFinancier": {
                    "type": "string",
                    "description": "Les enjeux financier du projet exprimé en k euros",
                },
            },
        },
        "contexte": {
            "type": "object",
            "description": "Informations sur le contexte et le client",
            "properties": {
                "presentationClient": {
                    "type": "string",
                    "description": "Courte présentation du client. Longueur maximale: 300 caractères (une à deux phrases).",
                    "maxLength": 300,
                },
                "presentationContexte": {
                    "type": "string",
                    "description": "Courte présentation du contexte du projet. Longueur maximale: 300 caractères (une à deux phrases).",
                    "maxLength": 300,
                },
                "listeTechnologies": {
                    "type": "string",
                    "description": "Listes des technologies utilisés lors de ce projet",
                },
            },
        },
        "syntheseProjet": {
            "type": "object",
            "description": "Synthèse struturée du projet",
            "properties": {
                "enjeux": {
                    "type": "string",
                    "description": "Court résumé des enjeux du projet. Longueur maximale: 300 caractères (une à deux phrases).",
                    "maxLength": 300,
                },
                "activiteSolutions": {
                    "type": "string",
                    "description": "Court résumé des activités et solutions du projet. Longueur maximale: 300 caractères (une à deux phrases).",
                    "maxLength": 300,
                },
                "beneficeClients": {
                    "type": "string",
                    "description": "Court résumé des bénéfices pour le client. Longueur maximale: 300 caractères (une à deux phrases).",
                },
                "pointsForts": {
                    "type": "string",
                    "description": "Court résumé des points forts du projet. Longueur maximale: 300 caractères (une à deux phrases).",
                },
            },
        },
    },
}
