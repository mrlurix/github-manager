"""Modern, flat design system: palette, typography and the global QSS."""

from __future__ import annotations

from PySide6.QtGui import QColor, QFont, QFontDatabase

DARK = {
    "bg": "#0b0e14",
    "bg_elev": "#11151f",
    "surface": "#151a26",
    "surface_2": "#1b2130",
    "surface_3": "#222939",
    "border": "#252c3b",
    "border_soft": "#1d2432",
    "text": "#e7ecf5",
    "text_dim": "#9aa5bb",
    "text_faint": "#6b7690",
    "accent": "#7c6cff",
    "accent_hi": "#9487ff",
    "accent_press": "#6857f5",
    "accent_soft": "rgba(124, 108, 255, 0.16)",
    "on_accent": "#ffffff",
    "success": "#31c48d",
    "warning": "#f5a524",
    "danger": "#f2555a",
    "info": "#3aa0ff",
    "shadow": "rgba(0, 0, 0, 0.55)",
    "code_bg": "#0e1320",
}

LIGHT = {
    "bg": "#f4f6fb",
    "bg_elev": "#ffffff",
    "surface": "#ffffff",
    "surface_2": "#f7f8fc",
    "surface_3": "#eef0f7",
    "border": "#dfe3ed",
    "border_soft": "#e9ecf4",
    "text": "#141824",
    "text_dim": "#5a6377",
    "text_faint": "#8b93a5",
    "accent": "#5b4bdb",
    "accent_hi": "#6c5ce7",
    "accent_press": "#4a3ac9",
    "accent_soft": "rgba(91, 75, 219, 0.12)",
    "on_accent": "#ffffff",
    "success": "#12a374",
    "warning": "#c77700",
    "danger": "#d63b40",
    "info": "#1372c4",
    "shadow": "rgba(23, 28, 45, 0.14)",
    "code_bg": "#0f1320",
}

ACCENTS = {
    "violet": "#7c6cff",
    "blue": "#3b82f6",
    "emerald": "#10b981",
    "amber": "#f59e0b",
    "rose": "#f43f5e",
    "cyan": "#06b6d4",
}

FONT_STACK = ("Segoe UI Variable Display", "Segoe UI", "Inter", "Noto Sans", "Arial")

# Horizontal padding used by QPushButton#Chip. Kept as a constant because the
# chip helper needs it to compute a correct minimum width (Qt's sizeHint ignores
# QSS padding).
CHIP_PADDING_X = 14


def font_family(override: str = "") -> str:
    available = set(QFontDatabase.families())
    if override and override in available:
        return override
    for name in FONT_STACK:
        if name in available:
            return name
    return "Arial"


def mono_family() -> str:
    available = set(QFontDatabase.families())
    for name in ("Cascadia Code", "Cascadia Mono", "Consolas", "JetBrains Mono", "Menlo"):
        if name in available:
            return name
    return "Courier New"


def build_palette(theme: str = "dark", accent: str = "violet") -> dict[str, str]:
    base = dict(DARK if theme == "dark" else LIGHT)
    key = ACCENTS.get(accent)
    if key:
        base["accent"] = key
        if theme == "dark":
            base["accent_hi"] = _lighten(key, 0.16)
            base["accent_press"] = _darken(key, 0.12)
        else:
            base["accent_hi"] = _darken(key, 0.08)
            base["accent_press"] = _darken(key, 0.18)
        base["accent_soft"] = _rgba(key, 0.16 if theme == "dark" else 0.12)
    return base


def _lighten(hex_color: str, amount: float) -> str:
    color = QColor(hex_color)
    return QColor(
        min(255, int(color.red() + 255 * amount)),
        min(255, int(color.green() + 255 * amount)),
        min(255, int(color.blue() + 255 * amount)),
    ).name()


def _darken(hex_color: str, amount: float) -> str:
    color = QColor(hex_color)
    return QColor(
        max(0, int(color.red() * (1 - amount))),
        max(0, int(color.green() * (1 - amount))),
        max(0, int(color.blue() * (1 - amount))),
    ).name()


def _rgba(hex_color: str, alpha: float) -> str:
    color = QColor(hex_color)
    return f"rgba({color.red()}, {color.green()}, {color.blue()}, {alpha:g})"


def app_font(size: int = 10, weight: int = 400, family: str = "") -> QFont:
    font = QFont(font_family(family))
    font.setPointSize(size)
    font.setWeight(QFont.Weight(weight))
    font.setHintingPreference(QFont.HintingPreference.PreferFullHinting)
    return font


def mono_font(size: int = 10) -> QFont:
    """Monospaced font at ``size`` points, using the detected mono family."""
    font = QFont(mono_family())
    font.setPointSize(size)
    return font


STYLESHEET = """
* {{
    outline: none;
}}

QWidget {{
    color: {text};
    font-family: "{font}";
    font-size: {fs}pt;
}}

QToolTip {{
    background: {surface_3};
    color: {text};
    border: 1px solid {border};
    border-radius: 6px;
    padding: 6px 8px;
}}

/* ---------------------------------------------------------- base surfaces */
#Root, #Sidebar, #Content {{
    background: {bg};
}}
#Content {{
    background: qlineargradient(x1:0, y1:0, x2:0, y2:1,
                stop:0 {bg}, stop:1 {bg_elev});
}}

#Card {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 14px;
}}
#CardFlat {{
    background: {surface_2};
    border: 1px solid {border_soft};
    border-radius: 12px;
}}
#CardHover:!hover {{
    border: 1px solid {border};
    background: {surface_2};
}}
#CardHover:hover {{
    border: 1px solid {accent};
    background: {surface_2};
}}
#Inset {{
    background: {surface_2};
    border: 1px solid {border_soft};
    border-radius: 10px;
}}
#GlassCard {{
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 {surface}, stop:1 {surface_2});
    border: 1px solid {border};
    border-radius: 16px;
}}

/* ------------------------------------------------------------- typography */
QLabel[role="h1"] {{
    font-size: {h1}pt;
    font-weight: 700;
    color: {text};
}}
QLabel[role="h2"] {{
    font-size: {h2}pt;
    font-weight: 600;
    color: {text};
}}
QLabel[role="h3"] {{
    font-size: {h3}pt;
    font-weight: 600;
    color: {text};
}}
QLabel[role="dim"] {{ color: {text_dim}; }}
QLabel[role="faint"] {{ color: {text_faint}; font-size: 9pt; }}
QLabel[role="mono"] {{
    font-family: "{mono}";
    color: {text_dim};
}}
QLabel[role="accent"] {{ color: {accent}; font-weight: 600; }}
QLabel[role="danger"] {{ color: {danger}; }}
QLabel[role="success"] {{ color: {success}; }}
QLabel[role="warning"] {{ color: {warning}; }}

/* ---------------------------------------------------------------- buttons */
QPushButton {{
    background: {surface_2};
    color: {text};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 8px 14px;
    font-weight: 500;
}}
QPushButton:hover {{ background: {surface_3}; border-color: {border}; }}
QPushButton:pressed {{ background: {surface}; }}
QPushButton:disabled {{ color: {text_faint}; background: {surface_2}; border-color: {border_soft}; }}

QPushButton[variant="primary"] {{
    background: {accent};
    color: {on_accent};
    border: 1px solid {accent};
    font-weight: 600;
}}
QPushButton[variant="primary"]:hover {{ background: {accent_hi}; border-color: {accent_hi}; }}
QPushButton[variant="primary"]:pressed {{ background: {accent_press}; }}
QPushButton[variant="primary"]:disabled {{
    background: {surface_3}; color: {text_faint}; border-color: {border_soft};
}}

QPushButton[variant="ghost"] {{
    background: transparent;
    border: 1px solid transparent;
    color: {text_dim};
    padding: 6px 10px;
}}
QPushButton[variant="ghost"]:hover {{ background: {surface_2}; color: {text}; }}
QPushButton[variant="ghost"]:pressed {{ background: {surface_3}; }}

QPushButton[variant="outline"] {{
    background: transparent;
    border: 1px solid {border};
    color: {text};
}}
QPushButton[variant="outline"]:hover {{ border-color: {accent}; color: {accent}; }}

QPushButton[variant="danger"] {{
    background: transparent;
    border: 1px solid {danger};
    color: {danger};
}}
QPushButton[variant="danger"]:hover {{ background: {danger}; color: {on_accent}; }}

QPushButton[variant="subtle"] {{
    background: {accent_soft};
    color: {accent};
    border: 1px solid transparent;
    font-weight: 600;
}}
QPushButton[variant="subtle"]:hover {{ background: {accent_soft}; border-color: {accent}; }}

QPushButton#NavButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 10px;
    color: {text_dim};
    text-align: left;
    padding: 10px 12px;
    font-size: {fs}pt;
    font-weight: 500;
}}
QPushButton#NavButton:hover {{ background: {surface_2}; color: {text}; }}
QPushButton#NavButton:checked {{
    background: {accent_soft};
    color: {accent};
    font-weight: 600;
}}

QPushButton#Chip {{
    background: {surface_2};
    border: 1px solid {border_soft};
    border-radius: 14px;
    color: {text_dim};
    padding: 6px 14px;
    font-size: 9pt;
}}
QPushButton#Chip:hover {{ border-color: {accent}; color: {text}; }}
QPushButton#Chip:checked {{
    background: {accent_soft};
    border-color: {accent};
    color: {accent};
    font-weight: 600;
}}

QPushButton#LinkButton {{
    background: transparent;
    border: none;
    color: {accent};
    padding: 2px;
    text-align: left;
    font-weight: 500;
}}
QPushButton#LinkButton:hover {{ color: {accent_hi}; text-decoration: underline; }}

QPushButton#IconButton {{
    background: transparent;
    border: 1px solid transparent;
    border-radius: 9px;
    padding: 6px;
}}
QPushButton#IconButton:hover {{ background: {surface_2}; border-color: {border}; }}

/* ----------------------------------------------------------------- inputs */
QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox {{
    background: {surface_2};
    color: {text};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 8px 10px;
    selection-background-color: {accent};
    selection-color: {on_accent};
}}
QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus,
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {accent};
    background: {surface};
}}
QLineEdit:disabled, QTextEdit:disabled, QPlainTextEdit:disabled {{
    color: {text_faint};
    background: {surface_2};
}}
QLineEdit[role="search"] {{
    padding-left: 10px;
}}
QLineEdit QIcon {{
    padding-left: 2px;
}}
QLineEdit#CodeEditor {{
    font-family: "{mono}";
    font-size: {mono_fs}pt;
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 12px;
}}

QComboBox {{
    background: {surface_2};
    color: {text};
    border: 1px solid {border};
    border-radius: 9px;
    padding: 7px 10px;
    min-height: 20px;
}}
QComboBox:hover {{ border-color: {accent}; }}
QComboBox::drop-down {{ border: none; width: 22px; }}
QComboBox QAbstractItemView {{
    background: {surface_2};
    color: {text};
    border: 1px solid {border};
    border-radius: 10px;
    selection-background-color: {accent_soft};
    selection-color: {text};
    padding: 4px;
    outline: none;
}}

QCheckBox, QRadioButton {{ spacing: 8px; color: {text}; }}
QCheckBox::indicator, QRadioButton::indicator {{
    width: 17px; height: 17px;
    border: 1px solid {border};
    background: {surface_2};
}}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 9px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {accent}; }}
QCheckBox::indicator:checked {{ background: {accent}; border-color: {accent}; }}
QRadioButton::indicator:checked {{ background: {accent}; border: 5px solid {surface_2}; }}
QCheckBox::indicator:disabled {{ background: {surface_3}; border-color: {border_soft}; }}

QSlider::groove:horizontal {{
    height: 4px; background: {surface_3}; border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {accent};
    width: 15px; height: 15px;
    margin: -6px 0;
    border-radius: 7px;
}}
QSlider::sub-page:horizontal {{ background: {accent}; border-radius: 2px; }}

/* ------------------------------------------------------------------ lists */
QListWidget, QTreeWidget, QTableWidget {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
    outline: none;
}}
QListWidget::item {{
    padding: 8px;
    border-radius: 8px;
}}
QListWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QListWidget::item:hover {{ background: {surface_2}; }}
QTreeWidget::item:selected {{ background: {accent_soft}; color: {text}; }}
QHeaderView::section {{
    background: {surface_2};
    color: {text_dim};
    border: none;
    border-bottom: 1px solid {border};
    padding: 8px;
    font-weight: 600;
}}

/* --------------------------------------------------------------- scrollbar */
QScrollBar:vertical {{
    background: transparent; width: 10px; margin: 2px;
}}
QScrollBar::handle:vertical {{
    background: {surface_3}; border-radius: 5px; min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{ background: {accent}; }}
QScrollBar:horizontal {{
    background: transparent; height: 10px; margin: 2px;
}}
QScrollBar::handle:horizontal {{
    background: {surface_3}; border-radius: 5px; min-width: 30px;
}}
QScrollBar::handle:horizontal:hover {{ background: {accent}; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; width: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}

/* ------------------------------------------------------------------- tabs */
QTabWidget::pane {{
    border: 1px solid {border};
    border-radius: 12px;
    background: {surface};
    top: -1px;
}}
QTabBar::tab {{
    background: transparent;
    color: {text_dim};
    padding: 9px 16px;
    margin-right: 4px;
    border: 1px solid transparent;
    border-top-left-radius: 9px;
    border-top-right-radius: 9px;
    font-weight: 500;
}}
QTabBar::tab:hover {{ color: {text}; background: {surface_2}; }}
QTabBar::tab:selected {{
    background: {surface};
    color: {accent};
    border-color: {border};
    border-bottom-color: {surface};
    font-weight: 600;
}}

/* --------------------------------------------------------------- progress */
QProgressBar {{
    background: {surface_3};
    border: none;
    border-radius: 4px;
    height: 8px;
    text-align: center;
    color: transparent;
}}
QProgressBar::chunk {{ background: {accent}; border-radius: 4px; }}

QStatusBar {{
    background: {bg_elev};
    color: {text_dim};
    border-top: 1px solid {border_soft};
}}
QStatusBar::item {{ border: none; }}

/* ----------------------------------------------------------------- menus */
QMenu {{
    background: {surface_2};
    color: {text};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 22px 7px 14px;
    border-radius: 7px;
}}
QMenu::item:selected {{ background: {accent_soft}; color: {accent}; }}
QMenu::separator {{
    height: 1px; background: {border_soft}; margin: 5px 8px;
}}

/* --------------------------------------------------------------- scrollarea */
QScrollArea {{ background: transparent; border: none; }}
QScrollArea > QWidget > QWidget {{ background: transparent; }}
QScrollArea QScrollBar {{ background: transparent; }}

/* ---------------------------------------------------------------- helpers */
#Divider {{ background: {border_soft}; max-height: 1px; min-height: 1px; border: none; }}
#VDivider {{ background: {border_soft}; max-width: 1px; min-width: 1px; border: none; }}

#Sidebar {{
    background: {bg_elev};
    border-right: 1px solid {border_soft};
}}
#TopBar {{
    background: transparent;
    border-bottom: 1px solid {border_soft};
}}

#StatValue {{ font-size: {stat}pt; font-weight: 700; color: {text}; }}
#StatLabel {{ font-size: 9pt; color: {text_faint}; }}

/* ----------------------------------------------------------- issue rows */
QListWidget#IssueList {{
    background: transparent;
    border: none;
}}
QListWidget#IssueList::item {{
    background: transparent;
    border: none;
    padding: 0;
}}
QListWidget#IssueList::item:selected,
QListWidget#IssueList::item:hover {{
    background: transparent;
}}
QWidget#IssueRow {{
    background: {surface};
    border-radius: 10px;
}}
QWidget#IssueRow:hover {{
    background: {surface_2};
}}
QWidget#IssueRow[active="true"] {{
    background: {accent_soft};
    border-radius: 10px;
}}

#Badge {{
    background: {surface_3};
    color: {text_dim};
    border-radius: 9px;
    padding: 3px 9px;
    font-size: 8pt;
    font-weight: 600;
}}
#BadgeAccent {{ background: {accent_soft}; color: {accent}; border-radius: 9px; padding: 3px 9px; font-size: 8pt; font-weight: 600; }}
#BadgeSuccess {{ background: rgba(49, 196, 141, 0.16); color: {success}; border-radius: 9px; padding: 3px 9px; font-size: 8pt; font-weight: 600; }}
#BadgeWarning {{ background: rgba(245, 165, 36, 0.16); color: {warning}; border-radius: 9px; padding: 3px 9px; font-size: 8pt; font-weight: 600; }}
#BadgeDanger {{ background: rgba(242, 85, 90, 0.16); color: {danger}; border-radius: 9px; padding: 3px 9px; font-size: 8pt; font-weight: 600; }}

#Kbd {{
    background: {surface_3};
    color: {text_dim};
    border: 1px solid {border};
    border-radius: 5px;
    padding: 1px 6px;
    font-family: "{mono}";
    font-size: 8pt;
}}

QTextBrowser#MarkdownView {{
    background: {surface};
    border: 1px solid {border};
    border-radius: 12px;
    padding: 18px 22px;
}}

/* --------------------------------------------------------- chat bubbles */
QWidget#BubbleRow {{
    background: transparent;
}}
QTextBrowser#BubbleView {{
    background: transparent;
    border: none;
    padding: 0;
}}
"""


def stylesheet(theme: str = "dark", accent: str = "violet", family: str = "", scale: float = 1.0) -> str:
    pal = build_palette(theme, accent)
    fs = int(round(10 * scale))
    mono_fs = max(9, int(round(10 * scale)))
    return (
        STYLESHEET.format(
            font=font_family(family),
            mono=mono_family(),
            fs=fs,
            mono_fs=mono_fs,
            h1=int(round(21 * scale)),
            h2=int(round(16 * scale)),
            h3=int(round(12 * scale)),
            stat=int(round(19 * scale)),
            **pal,
        )
    )


MARKDOWN_CSS = """
body {{
    color: {text};
    background: transparent;
    line-height: 150%;
}}
h1, h2, h3, h4 {{ color: {text}; margin: 18px 0 8px 0; }}
h1 {{ font-size: 22px; border-bottom: 1px solid {border}; padding-bottom: 6px; }}
h2 {{ font-size: 17px; border-bottom: 1px solid {border_soft}; padding-bottom: 5px; }}
a {{ color: {accent}; text-decoration: none; }}
code {{ background: {surface_3}; color: {accent_hi}; padding: 2px 5px; border-radius: 4px;
        font-family: "{mono}"; font-size: 90%; }}
pre, pre.highlight-pre {{
    background: {code_bg};
    border: 1px solid {border};
    border-radius: 10px;
    padding: 12px 14px;
    margin: 10px 0;
    overflow-x: auto;
}}
pre code {{ background: transparent; color: {text}; padding: 0; border: none; }}
.highlight {{ background: transparent; }}
blockquote {{
    border-left: 3px solid {accent};
    color: {text_dim};
    margin: 12px 0;
    padding: 2px 0 2px 12px;
}}
table {{ border-collapse: collapse; margin: 12px 0; }}
th, td {{ border: 1px solid {border}; padding: 7px 11px; text-align: left; }}
th {{ background: {surface_2}; font-weight: 600; }}
ul, ol {{ padding-left: 24px; }}
li {{ padding-left: 14px; }}
img {{ max-width: 100%; }}
hr {{ border: none; border-top: 1px solid {border}; margin: 18px 0; }}
p {{ margin: 8px 0; }}
"""


def markdown_css(theme: str = "dark", accent: str = "violet") -> str:
    pal = build_palette(theme, accent)
    return MARKDOWN_CSS.format(mono=mono_family(), **pal)


def markdown_palette(theme: str = "dark", accent: str = "violet") -> dict[str, str]:
    """Palette keys needed when inlining styles into rendered markdown."""
    pal = build_palette(theme, accent)
    pal["mono"] = mono_family()
    return pal
