import re
from docx import Document

TITLE_SPLIT = re.compile(r"\s{2,}(?=[A-Z])")

# Original CV sections that the generated profile replaces
PROFILE_HEADINGS = ("profile", "summary", "about me", "professional summary", "objective")


def save_tailored_cv(tailored, profile_text, path):
    doc = Document()

    # Contact lines at the top
    contact = tailored.get("Contact Information", {}).get("kept", [])
    for line in contact:
        doc.add_paragraph(line)

    # Generated profile (replaces the original one)
    doc.add_heading("Profile", level=1)
    doc.add_paragraph(profile_text)

    for heading, part in tailored.items():
        # Skip contact, empty sections and the original profile
        if heading == "Contact Information" or not part["kept"]:
            continue
        if heading.strip().lower() in PROFILE_HEADINGS:
            continue

        doc.add_heading(heading, level=1)

        for item in part["kept"]:
            paragraphs = []  # list of [text, is_bullet]
            for raw in item.splitlines():
                line = raw.strip()
                if not line:
                    continue
                if line[0] in "•-–":
                    # New bullet point
                    paragraphs.append([line[1:].strip(), True])
                elif paragraphs and line[0].islower():
                    # Continuation of a line the PDF wrapped
                    paragraphs[-1][0] += " " + line
                else:
                    # New normal line (title, degree, job, ...)
                    paragraphs.append([line, False])

            for text, is_bullet in paragraphs:
                # Split titles that were glued with extra spaces
                for piece in TITLE_SPLIT.split(text):
                    piece = piece.strip().rstrip(",;").strip()
                    if not piece:
                        continue
                    if is_bullet:
                        doc.add_paragraph(piece, style="List Bullet")
                    else:
                        doc.add_paragraph(piece)

    doc.save(path)
    return path