import logging
import re

from docx import Document
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


def fill_word_from_structured_response(docx_path, structured_responses, output_path):
    doc = Document(docx_path)
    pattern = re.compile(r"\{([^}]+)\}")

    logger.info("=== STARTING WORD TEMPLATE FILL ===")
    logger.info(f"Template path: {docx_path}")
    logger.info(f"Output path: {output_path}")

    # Log template content before processing
    logger.info("=== TEMPLATE CONTENT BEFORE PROCESSING ===")
    total_placeholders_in_template = 0
    for i, para in enumerate(doc.paragraphs):
        if para.text.strip():
            logger.info(f"Template Para {i}: {para.text}")
            placeholders = pattern.findall(para.text)
            if placeholders:
                total_placeholders_in_template += len(placeholders)
                logger.info(f"  Placeholders found: {placeholders}")

    for i, table in enumerate(doc.tables):
        for row_idx, row in enumerate(table.rows):
            for col_idx, cell in enumerate(row.cells):
                for para in cell.paragraphs:
                    if para.text.strip():
                        logger.info(f"Template Table {i}[{row_idx},{col_idx}]: {para.text}")
                        placeholders = pattern.findall(para.text)
                        if placeholders:
                            total_placeholders_in_template += len(placeholders)
                            logger.info(f"  Placeholders found: {placeholders}")

    logger.info(f"Total placeholders in template: {total_placeholders_in_template}")

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

    logger.info("=== DATA FOR REPLACEMENT ===")
    logger.info(f"Flattened data keys: {list(flattened_data.keys())}")
    logger.info(f"Flattened data: {flattened_data}")

    # Helper function to process paragraphs with formatting preservation
    def process_paragraph(paragraph):
        # Merge all runs to find complete placeholders (handles split placeholders)
        full_text = "".join(run.text for run in paragraph.runs)

        if not full_text:
            return

        logger.debug(f"Processing paragraph text: '{full_text}'")

        # Find all placeholders and their positions in the merged text
        matches = list(pattern.finditer(full_text))
        if not matches:
            return

        logger.info(f"Found {len(matches)} placeholders in paragraph")

        # Build a list of placeholder replacements
        placeholder_replacements = {}
        for match in matches:
            key = match.group(1)
            logger.info(f"Processing placeholder: {{{key}}}")
            if key in flattened_data:
                value = str(flattened_data[key])
                logger.info(f"Replacing {{{key}}} with: {value}")
                placeholder_replacements[match.start()] = {
                    "end": match.end(),
                    "placeholder": match.group(0),
                    "value": value,
                }
            else:
                logger.warning(f"Placeholder '{key}' not found in flattened data")

        if not placeholder_replacements:
            return

        # Sort placeholders by position
        sorted_placeholders = sorted(placeholder_replacements.items(), key=lambda x: x[0])

        # Process each run and replace placeholder text while preserving formatting
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
                        offset = len(new_run_text) - local_start

                # Case 2: This run is in the middle/end of a placeholder
                elif placeholder_start < run_start < placeholder_end:
                    if placeholder_end >= run_end:
                        # Entire run is part of the placeholder - empty it
                        new_run_text = ""
                        offset = -len(run.text)
                    else:
                        # Placeholder ends in this run - keep text after placeholder
                        local_end = placeholder_end - run_start
                        new_run_text = new_run_text[local_end:]
                        offset = -local_end

            run.text = new_run_text
            char_position = run_end

        logger.info(f"Final paragraph text after replacement: '{paragraph.text}'")

    # Process all paragraphs in the document body
    for paragraph in doc.paragraphs:
        process_paragraph(paragraph)

    # Process tables in the document
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                for paragraph in cell.paragraphs:
                    process_paragraph(paragraph)

    # Process headers
    for section in doc.sections:
        # Process header (first, even, default)
        header = section.header
        for paragraph in header.paragraphs:
            process_paragraph(paragraph)
        # Process header tables
        for table in header.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        process_paragraph(paragraph)

    # Process footers
    for section in doc.sections:
        # Process footer (first, even, default)
        footer = section.footer
        for paragraph in footer.paragraphs:
            process_paragraph(paragraph)
        # Process footer tables
        for table in footer.tables:
            for row in table.rows:
                for cell in row.cells:
                    for paragraph in cell.paragraphs:
                        process_paragraph(paragraph)

    # Process textboxes (VML and DrawingML) - CRITICAL for templates with text boxes
    # Many Word templates use textboxes for layout, and python-docx doesn't handle them well
    logger.info("=== PROCESSING TEXTBOXES ===")

    textbox_count = 0
    replacements_made = 0

    # Process all textbox content elements (both VML and DrawingML formats)
    for txbxContent in doc.element.body.iter():
        # Check if this is a textbox content element
        tag_name = txbxContent.tag.split('}')[-1] if '}' in txbxContent.tag else txbxContent.tag
        if tag_name != 'txbxContent':
            continue

        textbox_count += 1
        logger.info(f"Processing textbox {textbox_count}")

        # Find all text elements in this textbox
        for t_elem in txbxContent.iter():
            t_tag = t_elem.tag.split('}')[-1] if '}' in t_elem.tag else t_elem.tag
            if t_tag != 't':
                continue

            if t_elem.text and ('{' in t_elem.text or '}' in t_elem.text):
                original_text = t_elem.text
                logger.info(f"  Found text with potential placeholders: '{original_text}'")

                # Find and replace all placeholders in this text element
                new_text = original_text
                for match in pattern.finditer(original_text):
                    key = match.group(1)
                    placeholder = match.group(0)

                    if key in flattened_data:
                        value = str(flattened_data[key])
                        logger.info(f"    Replacing {placeholder} with: {value}")
                        new_text = new_text.replace(placeholder, value)
                        replacements_made += 1
                    else:
                        logger.warning(f"    Placeholder '{key}' not found in flattened data")

                if new_text != original_text:
                    t_elem.text = new_text
                    logger.info(f"    Updated text: '{new_text}'")

    logger.info(f"Processed {textbox_count} textboxes, made {replacements_made} replacements")

    doc.save(output_path)
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
                    "description": "Le nombre de personnes dans la direction (uniquement dans la direction)",
                },
                "enjeuFinancier": {
                    "type": "string",
                    "description": "Les coûts financiers ou la rentabilité du projet exprimé en euros, juste un seul chiffre clé comme le CA (jamais en nombre de personnes sinon ne rien mettre)",
                    "maxLength": 100,
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
