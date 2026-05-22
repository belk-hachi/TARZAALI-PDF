import os
import json
from io import BytesIO
from dataclasses import dataclass, field
from typing import Dict, Any, Tuple, Optional

from xml.sax.saxutils import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (
    BaseDocTemplate, PageTemplate, Frame,
    Table, TableStyle, Paragraph, Spacer, KeepTogether
)
from reportlab.lib.units import mm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfbase.pdfmetrics import registerFontFamily
from reportlab.pdfgen import canvas


# ==========================================================
# 1. Config / Theme
# ==========================================================

@dataclass(frozen=True)
class PDFConfig:
    PAGE_W: float = A4[0]
    PAGE_H: float = A4[1]

    TABLE_LEFT_MARGIN: float = 7.5
    TOTAL_WIDTH: float = 572.5

    BOTTOM_MARGIN: float = 35.0
    HEADER_MARGIN: float = 180.0

    COLUMN_WIDTHS: Tuple[float, ...] = (290.5, 98.0, 56.0, 73.0, 55.0)

    LAB_INFO: Dict[str, Any] = field(default_factory=lambda: {
        "fax": "027902479",
        "tel": "027902479",
        "mobiles": ["0671013704", "0662552205"],
        "dr_name": "IBN SINA. Dr N.KACI",
        "addr_l1": "Boulevard Amir Abdelkader, Cité nouvelle",
        "addr_l2": "mosquée 205 N°1 et 2. DJELFA",
        "email": "info.tarzaali@gmail.com",
        "lab_name": "LABORATOIRE D'ANALYSES DE BIOLOGIE MEDICALE",
        "prof_name": "Professeur Abdelaziz TARZAALI"
    })


@dataclass(frozen=True)
class Theme:
    GRAY_CATEGORY: colors.Color = colors.HexColor("#C0C0C0")
    BLUE_RESULT: colors.Color = colors.HexColor("#0000FF")
    RED_ABNORMAL: colors.Color = colors.HexColor("#FF0000")
    RED_BORDER: colors.Color = colors.HexColor("#FF0000")
    GREEN_RESULT: colors.Color = colors.HexColor("#008000")
    BLACK_SEP: colors.Color = colors.black
    TEXT_COLOR: colors.Color = colors.black


# ==========================================================
# 2. Fonts (lazy loaded)
# ==========================================================

_fonts_cache = None

def register_fonts() -> Dict[str, str]:
    font_paths = [
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf', 'Regular'),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf', 'Bold'),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-Italic.ttf', 'Italic'),
        ('/usr/share/fonts/truetype/liberation/LiberationSans-BoldItalic.ttf', 'BoldItalic'),
        (r'C:\Windows\Fonts\arial.ttf', 'Regular'),
        (r'C:\Windows\Fonts\arialbd.ttf', 'Bold'),
        (r'C:\Windows\Fonts\ariali.ttf', 'Italic'),
        (r'C:\Windows\Fonts\arialbi.ttf', 'BoldItalic'),
    ]

    found_fonts = {'Regular': None, 'Bold': None, 'Italic': None, 'BoldItalic': None}

    for path, style in font_paths:
        if found_fonts[style] is None and os.path.exists(path):
            try:
                name = f"Arial-{style}" if "arial" in path.lower() else f"LiberationSans-{style}"
                pdfmetrics.registerFont(TTFont(name, path))
                found_fonts[style] = name
            except Exception:
                continue

    if all(found_fonts.values()):
        registerFontFamily(
            'Arial',
            normal=found_fonts['Regular'],
            bold=found_fonts['Bold'],
            italic=found_fonts['Italic'],
            boldItalic=found_fonts['BoldItalic']
        )
        return {
            'NORMAL': found_fonts['Regular'],
            'BOLD': found_fonts['Bold'],
            'ITALIC': found_fonts['Italic'],
            'BOLD_ITALIC': found_fonts['BoldItalic']
        }

    return {
        'NORMAL': 'Helvetica',
        'BOLD': 'Helvetica-Bold',
        'ITALIC': 'Helvetica-Oblique',
        'BOLD_ITALIC': 'Helvetica-BoldOblique'
    }


def get_fonts() -> Dict[str, str]:
    global _fonts_cache
    if _fonts_cache is None:
        _fonts_cache = register_fonts()
    return _fonts_cache


# ==========================================================
# 3. Styles (WITH PAGINATION FIXES)
# ==========================================================

class PDFStyles:
    def __init__(self, fonts: Dict[str, str], theme: Theme):
        self.normal = ParagraphStyle(
            "Normal", fontName=fonts["NORMAL"], fontSize=8, textColor=theme.TEXT_COLOR
        )

        self.patient = ParagraphStyle(
            "Patient", fontName=fonts["BOLD"], fontSize=10.5, leading=13,
            alignment=1, textColor=theme.TEXT_COLOR
        )

        self.category = ParagraphStyle(
            "Category", fontName=fonts["BOLD"], fontSize=8.0, leading=8.0,
            leftIndent=14, textColor=theme.TEXT_COLOR
        )

        self.subtest_name = ParagraphStyle(
            "SubtestName", fontName=fonts["BOLD"], fontSize=8.0, leading=8.0,
            leftIndent=18, textColor=theme.TEXT_COLOR,
            keepWithNext=True  # <-- FIX 2: Prevents result from being orphaned on previous page
        )

        self.subtest_result = ParagraphStyle(
            "SubtestResult", fontName=fonts["BOLD"], fontSize=10.5, leading=10,
            alignment=1, textColor=theme.BLUE_RESULT
        )

        self.subtest_result_blue = ParagraphStyle(
            "SubtestResultBlue", parent=self.subtest_result,
            textColor=theme.BLUE_RESULT
        )

        self.subtest_result_red = ParagraphStyle(
            "SubtestResultRed", parent=self.subtest_result,
            textColor=theme.RED_ABNORMAL
        )

        self.unit = ParagraphStyle(
            "Unit", fontName=fonts["NORMAL"], fontSize=7.2, leading=9.2,
            alignment=1, textColor=theme.TEXT_COLOR
        )

        self.range = ParagraphStyle(
            "Range", fontName=fonts["NORMAL"], fontSize=7.2, leading=9.2,
            alignment=1, textColor=theme.TEXT_COLOR
        )

        self.method = ParagraphStyle(
            "Method", fontName=fonts["ITALIC"], fontSize=6.3, leading=8.3,
            leftIndent=22, textColor=theme.TEXT_COLOR,
            keepWithNext=True  # <-- FIX 2: Keeps observation tied to method
        )

        self.observation_label = ParagraphStyle(
            "ObservationLabel", fontName=fonts["NORMAL"], fontSize=7.5, leading=10.0,
            textColor=theme.TEXT_COLOR
        )

        self.observation_value = ParagraphStyle(
            "ObservationValue", fontName=fonts["BOLD"], fontSize=8.0, leading=10.0,
            textColor=theme.TEXT_COLOR
        )

        self.legend_bullet = ParagraphStyle(
            "LegendBullet", fontName=fonts["NORMAL"], fontSize=8.0, leading=10.0,
            leftIndent=12, textColor=theme.TEXT_COLOR
        )

        self.legend_remarque_text = ParagraphStyle(
            "LegendRemarqueText", fontName=fonts["NORMAL"], fontSize=8.0, leading=10.0,
            leftIndent=12, textColor=theme.TEXT_COLOR
        )

        self.legend_sub_item = ParagraphStyle(
            "LegendSubItem", fontName=fonts["NORMAL"], fontSize=8.0, leading=10.0,
            leftIndent=24, textColor=theme.TEXT_COLOR
        )

        self.empty = ParagraphStyle(
            "Empty", fontName=fonts["NORMAL"], fontSize=8, textColor=theme.TEXT_COLOR
        )


# ==========================================================
# 4. Canvas Page Numbering
# ==========================================================

class NumberedCanvas(canvas.Canvas):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._saved_page_states = []

    def showPage(self):
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self):
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_number(num_pages)
            canvas.Canvas.showPage(self)
        canvas.Canvas.save(self)

    def draw_page_number(self, page_count):
        self.saveState()
        self.setFont(get_fonts()["NORMAL"], 9)
        self.drawRightString(A4[0] - 20, 20, f"Page {self._pageNumber} sur {page_count}")
        self.restoreState()


# ==========================================================
# 5. Header Drawer
# ==========================================================

class HeaderDrawer:
    def __init__(self, cfg: PDFConfig, theme: Theme, fonts: Dict[str, str]):
        self.cfg = cfg
        self.theme = theme
        self.fonts = fonts

    def draw(self, canvas_obj, list_info, logo_path=None, lab_config=None):
        if not lab_config: lab_config = self.cfg.LAB_INFO
        canvas_obj.saveState()

        x_left = self.cfg.TABLE_LEFT_MARGIN + 2
        x_right = x_left + self.cfg.TOTAL_WIDTH
        x_center = x_left + self.cfg.TOTAL_WIDTH / 2
        y_top = self.cfg.PAGE_H - 6

        self._draw_logo_and_title(canvas_obj, x_left, x_center, y_top, logo_path, lab_config)
        self._draw_contact_info(canvas_obj, x_left, x_right, y_top, lab_config)
        y_grid = self._draw_document_header(canvas_obj, x_center, y_top)
        self._draw_info_grid(canvas_obj, x_left, x_right, y_grid, list_info, lab_config)
        self._draw_column_headers(canvas_obj, x_left, self.cfg.PAGE_H - self.cfg.HEADER_MARGIN)

        canvas_obj.restoreState()

    def _draw_column_headers(self, canvas_obj, x_left, y_frame_top):
        headers = ["", "Résultat", "Unité", "Valeur Usuelle", "Validation"]
        widths = self.cfg.COLUMN_WIDTHS
        fs = 8.8

        curr_x = x_left
        text_y = y_frame_top - 12

        canvas_obj.setFont(self.fonts["BOLD"], fs)
        canvas_obj.setFillColor(colors.black)

        for i, h in enumerate(headers):
            tw = canvas_obj.stringWidth(h, self.fonts["BOLD"], fs)
            canvas_obj.drawString(curr_x + (widths[i] - tw) / 2, text_y, h)
            curr_x += widths[i]

        line_y = y_frame_top - 22
        canvas_obj.setLineWidth(1)
        canvas_obj.setStrokeColor(colors.black)
        canvas_obj.line(x_left, line_y, x_left + self.cfg.TOTAL_WIDTH, line_y)

    def _draw_logo_and_title(self, canvas_obj, x_left, x_center, y_top, logo_path, lab_config):
        logo_w, logo_h = 75, 61.5
        if logo_path and os.path.exists(logo_path):
            canvas_obj.drawImage(
                logo_path,
                x_left + 10, y_top - logo_h - 5,
                width=logo_w, height=logo_h,
                preserveAspectRatio=True, mask="auto"
            )

        canvas_obj.setFont(self.fonts["BOLD"], 12)
        canvas_obj.drawCentredString(x_center, y_top - 18, lab_config.get("lab_name", self.cfg.LAB_INFO["lab_name"]))

        canvas_obj.setFont(self.fonts["NORMAL"], 11)
        canvas_obj.drawCentredString(x_center, y_top - 34, lab_config.get("prof_name", self.cfg.LAB_INFO["prof_name"]))

    def _draw_contact_info(self, canvas_obj, x_left, x_right, y_top, lab_config):
        canvas_obj.setFont(self.fonts["NORMAL"], 9)
        phone_x = x_left + 120

        canvas_obj.drawString(phone_x, y_top - 62, f"Tel: {lab_config['lab_tel']}  / Fax: {lab_config['lab_fax']}")
        canvas_obj.drawString(phone_x, y_top - 72, f"Mobile: {lab_config['lab_mobile']}")

        canvas_obj.drawRightString(x_right, y_top - 62, lab_config.get("email", self.cfg.LAB_INFO["email"]))

    def _draw_document_header(self, canvas_obj, x_center, y_top):
        y_title = y_top - 100
        title_text = "Compte Rendu d'Analyses Medicales"

        canvas_obj.setFont(self.fonts["BOLD"], 13)
        canvas_obj.drawCentredString(x_center, y_title, title_text)

        tw = canvas_obj.stringWidth(title_text, self.fonts["BOLD"], 13)
        canvas_obj.setLineWidth(2.0)
        canvas_obj.line(x_center - tw / 2 - 4, y_title - 4, x_center + tw / 2 + 4, y_title - 4)

        return y_title - 20

    def _draw_info_grid(self, canvas_obj, x_left, x_right, y_grid, list_info, lab_config):
        fs, ls = 8.5, 13
        key_x = x_left + 22
        val_x = key_x + canvas_obj.stringWidth("Liste du :", self.fonts["ITALIC"], fs) + 5
        col2_x = x_left + 130
        col3_x = x_left + 275 + canvas_obj.stringWidth(" " * 30, self.fonts["NORMAL"], fs)

        rows = [
            ("N°Fax", lab_config["lab_fax"], lab_config["lab_mobile"],
             ("Adresse au laboratoire   ", lab_config["lab_dr_name"])),

            ("N°Tel", lab_config["lab_tel"], None, lab_config["lab_addr_l1"]),
            ("Liste", f"{list_info.get('listNumber', 'UNKNOWN')}", None, lab_config["lab_addr_l2"]),
            ("Liste du :", list_info.get("listeDate", ""), None, None),
        ]

        curr_y = y_grid

        for key, val, mob, addr in rows:
            canvas_obj.setFont(self.fonts["ITALIC"], fs)
            canvas_obj.drawString(key_x, curr_y, key)

            canvas_obj.setFont(self.fonts["BOLD"] if key in ["Liste", "Liste du :"] else self.fonts["NORMAL"], fs)
            canvas_obj.drawString(val_x, curr_y, str(val))

            if mob:
                canvas_obj.setFont(self.fonts["NORMAL"], fs)
                canvas_obj.drawString(col2_x, curr_y, str(mob))

            if addr:
                if isinstance(addr, tuple):
                    canvas_obj.setFont(self.fonts["NORMAL"], fs)
                    canvas_obj.drawString(col3_x, curr_y, addr[0])

                    canvas_obj.setFont(self.fonts["BOLD"], fs)
                    canvas_obj.drawString(
                        col3_x + canvas_obj.stringWidth(addr[0], self.fonts["NORMAL"], fs),
                        curr_y,
                        addr[1]
                    )
                else:
                    canvas_obj.setFont(self.fonts["NORMAL"], fs)
                    canvas_obj.drawString(col3_x, curr_y, addr)

            curr_y -= ls

        print_date = f"Imprimé Le {list_info.get('printDate', '')}"
        canvas_obj.setFont(self.fonts["NORMAL"], fs)
        canvas_obj.drawRightString(x_right - 10, curr_y + ls, print_date)



# ==========================================================
# 6. Test Table Builder (WITH PAGINATION FIXES)
# ==========================================================

class TestTableBuilder:
    def __init__(self, cfg: PDFConfig, theme: Theme, styles: PDFStyles):
        self.cfg = cfg
        self.theme = theme
        self.styles = styles
        self.empty_p = Paragraph("", styles.empty)

    def build_patient_header(self, p: Dict[str, Any]) -> Table:
        text = (
            f"&gt;&gt;  {escape(p.get('lastName',''))} {escape(p.get('firstName',''))} "
            f"Né(e) le {escape(p.get('dateOfBirth',''))}, "
            f"Prélèvement du : {escape(p.get('sampleDate',''))}  &lt;&lt;"
        )

        row = [Paragraph(text, self.styles.patient)] + [self.empty_p] * 4

        t = Table([row], colWidths=self.cfg.COLUMN_WIDTHS)
        t.setStyle(TableStyle([
            ("SPAN", (0, 0), (4, 0)),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        return t

    def build_test_table(self, test: Dict[str, Any]) -> Table:
        rows = []
        styles_cmds = []

        subtests = test.get("subTests") or []
        test_name = test.get("testName", "")

        # ---- Category row
        cat_row = [Paragraph(escape(test_name), self.styles.category)] + [self.empty_p] * 4
        rows.append(cat_row)

        row_index = 0
        styles_cmds += [
            ("SPAN", (0, row_index), (4, row_index)),
            ("BACKGROUND", (0, row_index), (4, row_index), self.theme.GRAY_CATEGORY),
            ("VALIGN", (0, row_index), (4, row_index), "MIDDLE"),
            ("LEFTPADDING", (0, row_index), (4, row_index), 2),
            ("TOPPADDING", (0, row_index), (4, row_index), 3),
            ("BOTTOMPADDING", (0, row_index), (4, row_index), 3),
        ]

        # ---- Subtest rows
        for s in subtests:
            row_index += 1

            res = s.get("result", "")
            is_abnormal = bool(s.get("isAbnormal"))

            # abnormal overrides all colors
            if is_abnormal:
                res_style = self.styles.subtest_result_red
            elif isinstance(res, str) and res in ["En Cours", "Ci-Joint", "Non Trié"]:
                res_style = self.styles.subtest_result_blue
            else:
                res_style = self.styles.subtest_result

            if isinstance(res, (int, float)):
                res_text = f"{res:g}"
            else:
                res_text = escape(str(res))

            if is_abnormal:
                res_text += " *"

            subtest_row = [
                Paragraph(escape(s.get("subtestName", "")), self.styles.subtest_name),
                Paragraph(res_text, res_style),
                Paragraph(escape(s.get("unit") or ""), self.styles.unit),
                Paragraph(escape(s.get("normalRange") or ""), self.styles.range),
                self.empty_p
            ]

            rows.append(subtest_row)

            styles_cmds += [
                ("VALIGN", (0, row_index), (4, row_index), "MIDDLE"),
                ("TOPPADDING", (0, row_index), (4, row_index), 3),
                ("BOTTOMPADDING", (0, row_index), (4, row_index), 3),
                ("LEFTPADDING", (0, row_index), (4, row_index), 2),
                ("RIGHTPADDING", (0, row_index), (4, row_index), 2),
            ]

            # ---- Method row (span)
            method = s.get("method", "")
            if method:
                row_index += 1
                rows.append([Paragraph(escape(method), self.styles.method)] + [self.empty_p] * 4)

                styles_cmds += [
                    ("SPAN", (0, row_index), (4, row_index)),
                    ("TOPPADDING", (0, row_index), (4, row_index), 0),
                    ("BOTTOMPADDING", (0, row_index), (4, row_index), 1),
                ]

            # ---- Observation row (two-column layout)
            obs = s.get("observation", "")
            if obs:
                row_index += 1
                obs_indent = 30.0
                obs_label_width = 85.0
                obs_value_width = self.cfg.TOTAL_WIDTH - obs_indent - obs_label_width
                obs_row = Table(
                    [[
                        Paragraph("Observation :", self.styles.observation_label),
                        Paragraph(escape(obs), self.styles.observation_value)
                    ]],
                    colWidths=[obs_label_width, obs_value_width]
                )
                obs_row.setStyle(TableStyle([
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("LEFTPADDING", (0, 0), (0, 0), obs_indent),
                    ("LEFTPADDING", (1, 0), (1, 0), 0),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                    ("TOPPADDING", (0, 0), (-1, -1), 0),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
                ]))
                rows.append([obs_row] + [self.empty_p] * 4)

                styles_cmds += [
                    ("SPAN", (0, row_index), (4, row_index)),
                    ("TOPPADDING", (0, row_index), (4, row_index), 1),
                    ("BOTTOMPADDING", (0, row_index), (4, row_index), 1),
                ]

            # ---- small spacer row (black separator between subtests)
            row_index += 1
            rows.append([self.empty_p] * 5)

            styles_cmds += [
                ("BACKGROUND", (0, row_index), (4, row_index), colors.white),
                ("TOPPADDING", (0, row_index), (4, row_index), 10),
                ("BOTTOMPADDING", (0, row_index), (4, row_index), 10),
            ]

        # FIX 1: repeatRows=1 forces the Category row to repeat at the top of a new page if the table splits
        table = Table(rows, colWidths=self.cfg.COLUMN_WIDTHS, repeatRows=1)

        table.setStyle(TableStyle(styles_cmds))
        return table

    def build_legend_block(self) -> Table:
        total_w = self.cfg.TOTAL_WIDTH
        green_hex = "#008000"
        red_hex = "#FF0000"

        rows = []

        legend_items = [
            (green_hex, "V : Validé", "Cette analyse est validée sous réserve de sa confrontation au contexte clinique."),
            (red_hex, "B&lt;, B&gt; : Borne extrême", "Ce paramètre est au-delà des bornes extrêmes qui ont été définies pour l'analyse."),
            (red_hex, "D : Domaine de compétence", "Le dossier est hors du domaine d'expertise de nos règles de validation."),
            (red_hex, "A&lt;, A&gt;, a&lt;, a&gt; : Antériorité", "Il n'y a pas suffisamment d'éléments dans le dossier qui justifient la cinétique de ce paramètre avec son antériorité ou bien il existe des informations en contradiction."),
            (red_hex, "C&lt;, C&gt;, c&lt;, c&gt; : Corrélation", "ce paramètre ne paraît pas corrélé aux autres analyses du dossier."),
        ]

        for color_hex, title, desc in legend_items:
            text = f'<font color="{color_hex}"><b>\u2022 {title} /</b></font> {escape(desc)}'
            rows.append([Paragraph(text, self.styles.legend_bullet)])

        remarque_text = "Remarque : Nous dissocions A, par \u00ab a \u00bb ou \u00ab A \u00bb, et C, par \u00ab c \u00bb ou \u00ab C \u00bb :"
        rows.append([Paragraph(remarque_text, self.styles.legend_remarque_text)])

        rows.append([Paragraph("<b>Minuscule :</b> indique l'absence ou l'insuffisance de justification.", self.styles.legend_sub_item)])
        rows.append([Paragraph("<b>Majuscule :</b> indique la présence d'au moins une règle négative de validation.", self.styles.legend_sub_item)])

        table = Table(rows, colWidths=[total_w])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 4),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 2),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 2),
            ("LINEABOVE", (0, 0), (-1, 0), 2, colors.black),
        ]))
        return table

    def build_separator(self) -> Table:
        t = Table([[self.empty_p] * 5], colWidths=self.cfg.COLUMN_WIDTHS, rowHeights=[4])
        t.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), self.theme.BLACK_SEP),
            ("TOPPADDING", (0, 0), (-1, -1), 0),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
        ]))
        return t


# ==========================================================
# 7. Main Generator
# ==========================================================

def generate_pdf(patient, list_info, logo_path=None, lab_config=None):
    cfg = PDFConfig()
    theme = Theme()
    fonts = get_fonts()
    styles = PDFStyles(fonts, theme)

    header_drawer = HeaderDrawer(cfg, theme, fonts)
    builder = TestTableBuilder(cfg, theme, styles)

    output = BytesIO()

    frame = Frame(
        cfg.TABLE_LEFT_MARGIN + 2,
        cfg.BOTTOM_MARGIN,
        cfg.TOTAL_WIDTH,
        cfg.PAGE_H - cfg.HEADER_MARGIN - cfg.BOTTOM_MARGIN,
        leftPadding=0,
        rightPadding=0,
        topPadding=25,
        bottomPadding=0
    )

    def draw_border(canvas_obj, doc_obj):
        canvas_obj.saveState()
        canvas_obj.setStrokeColor(theme.RED_BORDER)
        canvas_obj.setLineWidth(2)
        canvas_obj.roundRect(
            cfg.TABLE_LEFT_MARGIN + 2,
            cfg.BOTTOM_MARGIN,
            cfg.TOTAL_WIDTH,
            cfg.PAGE_H - cfg.HEADER_MARGIN - cfg.BOTTOM_MARGIN,
            6
        )
        canvas_obj.restoreState()

    template = PageTemplate(
        id="main",
        frames=[frame],
        onPage=lambda c, d: header_drawer.draw(c, list_info, logo_path, lab_config),
        onPageEnd=draw_border
    )

    doc = BaseDocTemplate(
        output,
        pagesize=A4,
        leftMargin=0,
        rightMargin=0,
        topMargin=0,
        bottomMargin=0
    )
    doc.addPageTemplates([template])

    elements = []

    elements.append(builder.build_patient_header(patient))
    #elements.append(Spacer(1, 4))

    for test in (patient.get("tests") or []):
        elements.append(builder.build_test_table(test))
        elements.append(Spacer(1, 14))

    elements.append(builder.build_separator())
    # elements.append(Spacer(1, 16))

    # elements.append(KeepTogether([builder.build_legend_block()]))

    doc.build(elements, canvasmaker=NumberedCanvas)

    output.seek(0)
    return output


# ==========================================================
# 8. Test Run
# ==========================================================

if __name__ == "__main__":
    with open("data.json", "r", encoding="utf-8") as f:
        data = json.load(f)

    l_info = {k: data[k] for k in ["listNumber", "listeDate", "printDate"]}

    for patient in data["patients"]:
        pdf_bytes = generate_pdf(patient, l_info, logo_path="./logo.jpg")

        last_name = patient.get('lastName', 'unknown')
        first_name = patient.get('firstName', 'unknown')
        sample_date = patient.get('sampleDate', '')
        date_suffix = "".join(filter(str.isdigit, sample_date))
        
        filename = f"{last_name}_{first_name}_{date_suffix}.pdf" if date_suffix else f"{last_name}_{first_name}.pdf"
        with open(filename, "wb") as out:
            out.write(pdf_bytes.read())

        print(f"✓ Generated {filename}")
