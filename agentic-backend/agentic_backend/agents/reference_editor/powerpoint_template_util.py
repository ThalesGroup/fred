import logging
import re

from pptx import Presentation

logger = logging.getLogger(__name__)


def fill_slide_from_structured_response(ppt_path, structured_responses, output_path):
    prs = Presentation(ppt_path)
    pattern = re.compile(r"\{([^}]+)\}")
    slides_numbers = [0, 0, 0]

    for slide_nb, response in zip(slides_numbers, structured_responses.values()):
        slide = prs.slides[slide_nb]
        for shape in slide.shapes:
            if not shape.has_text_frame:
                continue

            for paragraph in shape.text_frame.paragraphs:
                i = 0
                while i < len(paragraph.runs):
                    run = paragraph.runs[i]
                    text = run.text
                    runs_to_merge = 0

                    if "{" in text and "}" not in text:
                        for j, run2 in enumerate(paragraph.runs[i + 1 :], start=1):
                            text += run2.text
                            runs_to_merge = j
                            if "}" in text:
                                break

                    for key in pattern.findall(text):
                        if key in response:
                            text = text.replace(f"{{{key}}}", str(response[key]))

                    run.text = text

                    # Remove the merged runs
                    for _ in range(runs_to_merge):
                        if i + 1 < len(paragraph.runs):
                            paragraph._element.remove(paragraph.runs[i + 1]._element)

                    i += 1
            # for paragraph in shape.text_frame.paragraphs:  # type: ignore
            #     for run in paragraph.runs:
            #         text = run.text
            #         matches = pattern.findall(text)
            #         for key in matches:
            #             if key in response.keys():
            #                 text = text.replace(f"{{{key}}}", str(response[key]))

            #         run.text = text

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
