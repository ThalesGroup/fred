import re

from pptx import Presentation


def fill_slide_from_structured_response(
    ppt_path, structured_response, slide_number, output_path
):
    prs = Presentation(ppt_path)

    # Support 1-based slide numbering
    slide = prs.slides[slide_number - 1]

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
                    if key in structured_response.keys():
                        text = text.replace(f"{{{key}}}", structured_response[key])

                run.text = text

    prs.save(output_path)
    return output_path
