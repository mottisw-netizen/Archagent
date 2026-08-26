"""Hebrew lexicon.

Written against how Israeli permit comments (הערות רישוי / דרישות הוועדה) are
actually phrased: verbs in the infinitive ("יש להגדיל"), bounds as
"לא יפחת מ-" / "לא יעלה על", the value introduced by ל-, and units written
מ' / מטר / ס"מ / מ"ר.  Prefixed letters (ב, ה, ו, כ, ל, מ, ש) are absorbed by
:attr:`Lexicon.prefix`, so "הרוחב", "ברוחב" and "לרוחב" all read as רוחב.
"""

from __future__ import annotations

from .base import Lexicon

#: The prefixed letters Hebrew glues onto the front of a word.
PREFIX = r"[בהוכלמש]{0,2}"

AT_LEAST = (r"(?:לפחות|לא\s*יפחת\s*מ-?|לא\s*תפחת\s*מ-?|לא\s*פחות\s*מ-?|"
            r"מינימום(?:\s*של)?|לכל\s*הפחות|לא\s*יקטן\s*מ-?|לא\s*תקטן\s*מ-?|"
            r"יעמוד\s*על\s*לפחות|לא\s*יהיה\s*קטן\s*מ-?)")
AT_MOST = (r"(?:לא\s*יעלה\s*על|לא\s*תעלה\s*על|לכל\s*היותר|מקסימום(?:\s*של)?|"
           r"לא\s*יותר\s*מ-?|לא\s*יעבור\s*את|לא\s*יחרוג\s*מ-?|עד\s*ל?-?)")

HEBREW = Lexicon(
    code="he",
    name="עברית",
    departments={
        "תכנון": "Planning", "אדריכלות": "Architecture", "רישוי": "Licensing",
        "רישוי בנייה": "Licensing", "תנועה": "Traffic", "תחבורה": "Traffic",
        "חניה": "Parking", "חנייה": "Parking", "נגישות": "Accessibility",
        "כבאות": "Fire Safety", "כיבוי אש": "Fire Safety", "בטיחות אש": "Fire Safety",
        "תברואה": "Sanitation", "מים": "Water", "ביוב": "Sanitation",
        "ניקוז": "Drainage", "גינון": "Landscaping", "נוף": "Landscaping",
        "איכות הסביבה": "Environment", "סביבה": "Environment",
        "תשתיות": "Infrastructure", "הנדסה": "Engineering", "מהנדס העיר": "Engineering",
    },
    metrics={
        r"רוחב\s*(?:ה)?מעבר": "clear_width",
        r"רוחב\s*(?:נטו|חופשי|פנוי)": "clear_width",
        r"מעבר\s*(?:ה)?חופשי": "clear_width",
        r"שטח\s*(?:ה)?בניי?ה": "floor_area",
        r"שטחי\s*(?:ה)?בניי?ה": "floor_area",
        r"שטח\s*בנוי": "floor_area",
        r"קו\s*(?:ה)?בניי?ן": "setback",
        r"נסיג[הת]": "setback",
        r"מרווח": "clear_distance",
        r"מרחק": "clear_distance",
        r"רוחב": "width",
        r"אורך": "length",
        r"עומק": "length",
        r"גובה": "height",
        r"שטח": "area",
    },
    elements={
        r"מקומות\s*חני[יי]?[הת]": "parking",
        r"מקום\s*(?:ה)?חני[יי]?[הת]": "parking",
        # חניה / חנייה / חניית (construct state) / חניות
        r"חני[יי]?[הת]": "parking",
        r"חניות": "parking",
        r"שביל\s*(?:ה)?גישה": "driveway",
        r"דרך\s*פנימית": "driveway",
        r"משטח\s*תמרון": "driveway",
        r"מעבר": "driveway",
        r"בניי?ן": "building",
        r"מבנה": "building",
        r"מרפסת": "balcony",
        r"חדר": "room",
        r"רמפה": "ramp",
        r"מדרכה": "sidewalk",
        r"חלון": "window",
        r"קיר": "wall",
        r"מחסן": "store",
    },
    directions={
        r"צפוני?ת?\b": "north", r"צפון": "north",
        r"דרומי?ת?\b": "south", r"דרום": "south",
        r"מזרחי?ת?\b": "east", r"מזרח": "east",
        r"מערבי?ת?\b": "west", r"מערב": "west",
    },
    at_least=AT_LEAST,
    at_most=AT_MOST,
    increase_verbs=(r"(?:להגדיל|להרחיב|להעלות|להאריך|להגביה|יוגדל|תוגדל|יורחב|"
                    r"תורחב|יוארך|להוסיף)"),
    decrease_verbs=r"(?:להקטין|לצמצם|להצר|להפחית|לקצר|יוקטן|תוקטן|יצומצם|להנמיך)",
    set_verbs=r"(?:לשנות|לתקן|להתאים|לעדכן|לקבוע|ליישר)",
    # The lookbehind stops the ל of a word like "על" from reading as "to".
    to_marker=r"(?:(?<![א-ת])ל-?|לכדי|יהיה|תהיה|יעמוד\s*על|תעמוד\s*על)",
    unit_pattern=r"\s*(?P<unit>מ\"ר|ס\"מ|מ\"מ|מטרים|מטר|מ'|מ\b)?",
    units={r"מ\"ר": "m2", r"ס\"מ": "cm", r"מ\"מ": "mm",
           r"מטרים": "m", r"מטר": "m", r"מ'": "m", r"מ": "m"},
    statements=(r"נרשם", r"לידיעה", r"אין\s*הערות", r"הובהר", r"לתשומת\s*לב",
                r"מקובל", r"ללא\s*הערות"),
    annotations={
        r"טבל[הת]": "update_schedule",
        r"רשימ[הת]": "update_schedule",
        r"מידות": "update_dimension",
        r"מיד[הת]": "update_dimension",
        r"כותרת": "update_text",
        r"תווית": "update_text",
        r"סימון": "update_text",
        r"טקסט": "update_text",
    },
    annotation_verbs=r"(?:יש\s*)?(?:לעדכן|להוסיף|לתקן|לשנות|להשלים|לציין|לרשום|לסמן)",
    count_nouns=(
        (r"מקומות\s*חני[יי]?[הת]\s*(?:נגישים|לנכים)", {"type": "parking", "category": "accessible"}),
        (r"חניות\s*(?:נגישות|לנכים)", {"type": "parking", "category": "accessible"}),
        (r"מקומות\s*חני[יי]?[הת]\s*לאופניים", {"type": "bicycle_parking"}),
        (r"מקומות\s*חני[יי]?[הת]", {"type": "parking"}),
        (r"חניות", {"type": "parking"}),
    ),
    department_line=r"^\s*(?:מחלק[הת]|אגף|מדור|תחום|גורם\s*מאשר)\s*[:\-]\s*(?P<name>.+?)\s*$",
    comment_id_patterns=(
        r"^\s*(?:(?P<full>[A-Z]{1,3}-\d{1,4})|(?P<num>\d{1,3}))\s*[.):\-]\s*(?P<body>.+)$",
        r"^\s*הער[הת]\s*(?:מס['`]?\s*)?(?P<num>\d{1,3})\s*[.):\-]\s*(?P<body>.+)$",
        r"^\s*דריש[הת]\s*(?P<num>\d{1,3})\s*[.):\-]\s*(?P<body>.+)$",
    ),
    label_patterns=(
        r"\b(?P<label>[A-Z]{1,3}[-_ ]?\d{1,3})\b",
        r"מס['`]?\s*(?P<label>\d{1,3})\b",
        r"מספר\s*(?P<label>\d{1,3})\b",
    ),
    implied_metrics=(
        (r"להרחיב|יורחב|תורחב", "width", ">="),
        (r"להצר|יוצר", "width", "<="),
        (r"להאריך|יוארך|תוארך", "length", ">="),
        (r"לקצר|יקוצר", "length", "<="),
        (r"להגביה|יוגבה", "height", ">="),
        (r"להנמיך|יונמך", "height", "<="),
    ),
    prefix=PREFIX,
    setback_order="both",
)
