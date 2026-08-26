"""User-facing text, in the language of the comments.

Every string the agent shows a human - report headings, statuses, consultation
questions, and the diagnostic reasons behind an open item - is looked up here.
A missing key falls back to English rather than showing a key name.
"""

from __future__ import annotations

ENGLISH: dict[str, str] = {
    # report skeleton
    "report_title": "Municipal Correction Report",
    "project": "Project",
    "run": "Run",
    "source_version": "Source version",
    "mode": "Mode",
    "execution": "Execution",
    "generated": "Generated",
    "summary": "Summary",
    "total_comments": "Total municipal comments",
    "resolved_auto": "Resolved automatically",
    "resolved_consulted": "Resolved after user consultation",
    "requires_review": "Requires human review",
    "partial_warning": "**This run is partial.** The following are not satisfied:",
    "markup_warning": ("**Markup only.** No editable source model was supplied, so no drawing "
                       "was modified. The corrections below are instructions for a drafter."),
    "open_items": "Open items",
    "constraint_summary": "Constraint validation summary",
    "drawing_validation": "Drawing validation",
    "non_visual": "Non-visual changes",
    "versions": "Versions",
    "definition_of_done": "Definition of done",
    "sign_off": "Sign-off",
    "artefacts": "Artefacts",
    "none": "none",
    "rollback_line": "{parent} → {version}. Rollback: restore {parent}.",
    "validation_result_line": "Validation result: {result}.",
    "sign_off_text": ("This report and the accompanying drawings are an AI-generated proposal.\n"
                      "They require review and approval by the responsible licensed professional\n"
                      "before submission to the authority."),
    "reviewed_by": "Reviewed by: ______________________  Date: ____________",
    # table headers
    "th_comment": "Comment", "th_department": "Department", "th_status": "Status",
    "th_confidence": "Confidence", "th_ref": "Ref", "th_why_open": "Why it is open",
    "th_needed": "What is needed", "th_constraint": "Constraint", "th_priority": "Priority",
    "th_rule": "Rule", "th_required": "Required", "th_measured": "Measured",
    "th_check": "Check", "th_details": "Details", "th_element": "Element",
    "th_change": "Change",
    # per-comment section
    "department": "Department",
    "municipal_comment": "Municipal comment",
    "interpretation": "Interpretation",
    "user_decision": "User decision",
    "correction": "Correction",
    "affected_drawings": "Affected drawings",
    "planning_impact": "Planning impact",
    "validation": "Validation",
    "confidence": "Confidence",
    "consultation_triggers": "Consultation triggers",
    "none_extracted": "(none extracted)",
    "none_applied": "None applied.",
    "none_required": "None required - the model already satisfies the comment.",
    "no_impact": "None detected.",
    "not_sheeted": "(not sheeted)",
    "not_evaluated": "Not evaluated.",
    "at_limit": "at the limit",
    "still_compliant": "still compliant",
    "not_compliant": "NOT compliant",
    "confidence_limited": "{value} (limited by {component})",
    "evidence_line": ("{status}. Measured {measured} {op} {required} required "
                      "({tool}, {basis} basis)."),
    "rows": "{count} row(s)",
    "updated": "{element} {property} updated ({before} → {after})",
    # statuses
    "status.Resolved": "Resolved",
    "status.Partially resolved": "Partially resolved",
    "status.Addressed - requires confirmation": "Addressed - requires confirmation",
    "status.Not resolved": "Not resolved",
    "status.Requires human review": "Requires human review",
    "status.Not applicable": "Not applicable",
    "priority.critical": "CRITICAL", "priority.high": "HIGH",
    "priority.medium": "MEDIUM", "priority.low": "LOW",
    # consultation
    "consultation": "Consultation",
    "the_municipal_comment": "The municipal comment",
    "what_was_found": "What was found",
    "affected_elements": "Affected elements:",
    "proposed_correction": "Proposed correction",
    "consequences": "Consequences",
    "alternatives": "Alternatives",
    "recommendation": "Recommendation",
    "option_line": "Option {letter}: {strategy}",
    "asking_because": "Asking because:",
    "answer_with": "Answer with: approve | reject | alternative:<letter> | modify:<instruction>",
    "no_secondary_effect": "- no secondary effect detected",
    "none_identified": "(none identified)",
    "unmet": "- unmet: {constraint} {rule}",
    "regression_line": "- regression: {constraint} {rule}",
    "answer": "Answer",
    # planner and orchestrator reasons
    "r_no_action": "comment demands no action",
    "r_no_requirement": "no testable requirement could be extracted",
    "r_no_element": "no element in the model matches {requirement}",
    "r_ambiguous": "{count} elements match and the comment names no discriminator",
    "r_program": ("{metric} is a program-level change; it is a design decision, "
                  "not a minimal correction"),
    "r_no_strategy": "no planning strategy for metric {metric}",
    "r_unmeasurable": "current value could not be measured: {error}",
    "r_no_minimal_change": "no minimal change was found that satisfies {requirement}",
    "r_all_unsafe": "every candidate change breaks a constraint or creates a conflict",
    "r_spatial": "spatial conflict: {detail}",
    "r_already_compliant": "already compliant; no change required",
    "r_annotation_missing_text": ("the comment asks for a text change but does not state "
                                  "the replacement text"),
    "r_annotation_no_target": "nothing in the model matches the requested {kind} change",
    "r_annotation_unsafe": "annotation change breaks a constraint in simulation",
    "r_simulation_failed": "simulation failed: {error}",
    "r_below_floor": "confidence {value} is below the 0.60 floor (limited by {component})",
    "r_rejected": "the user rejected the proposed change",
    "r_unanswered": "the consultation question is unanswered",
    "r_modify": "the user asked to modify the correction: {note}",
    "r_execution_failed": "execution failed: {error}",
    "r_file_unreadable": "file could not be read ({notes})",
    "r_no_model": "no editable source model was supplied (or no driver can read it)",
    "r_equal_conflict": "two constraints of equal priority and source conflict: {rules}",
    "r_cycle": "circular dependency between changes",
    "r_regression": "regression: {rule} now fails",
    "r_markup_only": ("markup-only run: the comment was interpreted but nothing could "
                      "be measured"),
    "r_not_measured": "constraint could not be measured",
    # what is needed
    "n_human_decision": "a decision or clarification from a human",
    "n_architect_decision": "an explicit decision by the project architect",
    "n_which_governs": "a decision from the project architect on which one governs",
    "n_human_review": "human review",
    "n_review_interpretation": "human review of the interpretation and the proposed change",
    "n_answer": "an answer to the consultation question",
    "n_other_correction": "a different correction, or a response to the authority",
    "n_investigate_api": "investigation of the drawing API failure",
    "n_readable_copy": "a readable copy, or a text/JSON export",
    "n_driver": "a DWG/RVT/IFC adapter, or a JSON model export",
    "n_precedence": "a human decision on which change takes precedence",
    "n_rollback": "rollback or a corrected plan",
    "n_missing_reference": "the missing reference, or a manual check",
    "n_drafter": "a drafter to execute the instruction",
    # consultation triggers
    "t_ambiguous": "the comment does not identify a single element",
    "t_confidence": ("confidence {value} is below the {threshold} threshold "
                     "(limited by {component})"),
    "t_spatial": "the correction creates a spatial conflict: {detail}",
    "t_unmet": "the correction leaves another constraint unmet: {constraints}",
    "t_changes_metric": "the correction changes {metric} ({before} → {after})",
    "t_structural": "{element} is a structural element",
    "t_footprint": "the correction changes the building footprint",
    "t_consultant": "{element} belongs to another consultant ({consultant})",
    "t_multiple": "more than one valid solution exists",
    "t_hard_metric": "the change alters {metric}, which always needs human approval",
    "t_low_confidence_risk": ("confidence {value} with {risk} risk; autonomous mode only "
                              "applies minimal, reversible changes below the threshold"),
    # validation notes
    "v_statement_only": "statement only; no action demanded",
    "v_not_measurable": "the change was made, but the demand is not machine-measurable",
    "v_no_requirement": "no testable requirement could be extracted from the comment",
    "v_cannot_measure": "could not be measured: {error}",
    "v_still_not_met": "a change was applied but the requirement is still not met",
    "v_no_change": "no valid change was applied",
    "v_no_test": "constraint has no machine-testable form",
    # planner strategies
    "s_set_dimension": "Set {element} {parameter} to {value} (holding the {anchor} edge)",
    "s_move": "Move {element} {distance} {direction} to reach a {value} {edge} setback",
    "s_pull_back": "Pull the {edge} face of {element} back by {distance} ({parameter} {before} → {after})",
    "s_annotation": "{action} ({count} item(s))",
    "s_no_change": "No change required: {requirement} already holds ({measured})",
    "s_program_proposal": ("{requirement}; the model currently measures {measured}. Closing the "
                           "gap changes the project program, which is a design decision for the "
                           "architect."),
    "s_blocked": ("The minimal change ({strategy}) would break {blockers}. Either the blocking "
                  "constraint is relaxed by the authority, or the design changes more widely "
                  "than this comment allows."),
    "s_rollback": "restore the parent version",
    # definition of done
    "dod_manifest": "Every supplied file appears in the input manifest with a read status.",
    "dod_comments": "Every municipal comment has a comment object, a status and a confidence.",
    "dod_evidence": "Every comment marked Resolved has measured evidence.",
    "dod_traceability": "Every change traces to a comment id and a plan id.",
    "dod_simulated": "Every applied plan was simulated and pre-validated.",
    "dod_ledger": "The full constraint ledger was validated; no regression and no CRITICAL failure.",
    "dod_questions": "Every consultation question was answered or is listed as open.",
    "dod_original": "The original source file is byte-identical to its ingest checksum.",
    "dod_version": "A new immutable version exists with its manifest and audit log.",
    "dod_previews": "Previews, comparison and highlighted change map are generated.",
    "dod_open_items": "Open items name what is needed and from whom.",
    # previews
    "before": "Before",
    "after": "After ({version})",
    "changes": "Changes ({version})",
    "plot_boundary": "plot boundary",
    "affected": "affected",
    "no_changes": "no changes",
    "affected_indirectly": "affected indirectly",
    "compare_title": "Before / after - {version}",
    "legend_modified": "New or modified elements",
    "legend_removed": "Removed or replaced elements",
    "legend_indirect": "Elements affected indirectly",
    "legend_resolved": "Municipal comments resolved by the modification",
    "legend_unresolved": "Unresolved issues requiring review",
    # vocabulary used inside generated sentences
    "metric.width": "width", "metric.length": "length", "metric.height": "height",
    "metric.area": "area", "metric.floor_area": "floor area", "metric.count": "count",
    "metric.setback": "setback", "metric.clear_width": "clear width",
    "metric.clear_distance": "clear distance",
    "dir.north": "north", "dir.south": "south", "dir.east": "east", "dir.west": "west",
    "edge.north": "northern", "edge.south": "southern",
    "edge.east": "eastern", "edge.west": "western",
    "anchor.south_west": "south west", "anchor.north_east": "north east",
    "anchor.centre": "centre", "anchor.north_west": "north west",
    "anchor.south_east": "south east",
    "requirement_line": "{subject} {metric} {op} {value}",
    "etype.parking": "parking space", "etype.driveway": "driveway",
    "etype.building": "building", "etype.balcony": "balcony", "etype.room": "room",
    "etype.ramp": "ramp", "etype.wall": "wall", "etype.window": "window",
    "etype.sidewalk": "sidewalk", "etype.store": "store",
    "etype.project": "the project",
    "department.Planning": "Planning", "department.Architecture": "Architecture",
    "department.Licensing": "Licensing", "department.Traffic": "Traffic",
    "department.Parking": "Parking", "department.Accessibility": "Accessibility",
    "department.Fire Safety": "Fire Safety", "department.Sanitation": "Sanitation",
    "department.Water": "Water", "department.Drainage": "Drainage",
    "department.Landscaping": "Landscaping", "department.Environment": "Environment",
    "department.Infrastructure": "Infrastructure", "department.Engineering": "Engineering",
    "department.Unknown": "Unknown",
    "mode.consultation": "consultation", "mode.autonomous": "autonomous",
    "exec.applied": "applied", "exec.markup_only": "markup only",
    "result.passed": "passed", "result.passed_with_open_items": "passed with open items",
    "result.failed": "failed",
    "check.duplicate_elements": "duplicate elements",
    "check.broken_references": "broken references",
    "check.spatial_conflicts": "spatial conflicts",
    "check.schedules": "schedules",
    "check.sheet_assignment": "sheet assignment",
    "check.drawing_checks": "drawing checks",
    "check_status.pass": "pass", "check_status.fail": "fail",
    "check_status.warn": "warn", "check_status.not_evaluated": "not evaluated",
    "unit.m": "m", "unit.cm": "cm", "unit.mm": "mm", "unit.m2": "m²",
    "unit.sqm": "m²", "unit.count": "", "unit.unit": "",
    "conf.extraction": "extraction", "conf.interpretation": "interpretation",
    "conf.identification": "identification", "conf.solution": "solution",
    "conf.verification": "verification",
    "implicit_count": "parking count must not fall below the approved {value}",
    "implicit_dimension": "{element} {parameter} must not fall below the approved {value}",
    "r_model_choice": "the model identified the element: {reasoning}",
    "r_model_declined": "the model could not tell the candidates apart either",
    "attention": "Needs your decision",
    "err_ambiguous_subject": "the subject matches {count} elements",
    "err_not_found": "the element {element} is not in the model",
    "err_no_plot": "the model has no plot boundary, so a setback cannot be measured",
}

HEBREW: dict[str, str] = {
    "report_title": "דוח תיקון הערות רישוי",
    "project": "פרויקט",
    "run": "הרצה",
    "source_version": "גרסת מקור",
    "mode": "מצב עבודה",
    "execution": "ביצוע",
    "generated": "הופק בתאריך",
    "summary": "תקציר",
    "total_comments": 'סה"כ הערות רישוי',
    "resolved_auto": "טופלו אוטומטית",
    "resolved_consulted": "טופלו לאחר התייעצות עם המשתמש",
    "requires_review": "דורשות בדיקה אנושית",
    "partial_warning": "**ההרצה חלקית.** הפריטים הבאים אינם מתקיימים:",
    "markup_warning": ("**סימון בלבד.** לא סופק מודל מקור הניתן לעריכה, ולכן לא בוצע שינוי "
                       "בתוכנית. התיקונים שלהלן הם הוראות לשרטט."),
    "open_items": "פריטים פתוחים",
    "constraint_summary": "סיכום בדיקת אילוצים",
    "drawing_validation": "בדיקת התוכנית",
    "non_visual": "שינויים שאינם ויזואליים",
    "versions": "גרסאות",
    "definition_of_done": "הגדרת סיום",
    "sign_off": "אישור",
    "artefacts": "קבצי פלט",
    "none": "אין",
    "rollback_line": "{parent} ← {version}. חזרה לאחור: שחזור {parent}.",
    "validation_result_line": "תוצאת הבדיקה: {result}.",
    "sign_off_text": ("דוח זה והתוכניות המצורפות אליו הם הצעה שהופקה על ידי מערכת בינה מלאכותית.\n"
                      "הם טעונים בדיקה ואישור של בעל הרישיון האחראי\n"
                      "לפני הגשה לרשות."),
    "reviewed_by": "נבדק על ידי: ______________________  תאריך: ____________",
    "th_comment": "הערה", "th_department": "מחלקה", "th_status": "סטטוס",
    "th_confidence": "ביטחון", "th_ref": "מזהה", "th_why_open": "מדוע פתוח",
    "th_needed": "מה נדרש", "th_constraint": "אילוץ", "th_priority": "עדיפות",
    "th_rule": "כלל", "th_required": "נדרש", "th_measured": "נמדד",
    "th_check": "בדיקה", "th_details": "פירוט", "th_element": "אלמנט",
    "th_change": "שינוי",
    "department": "מחלקה",
    "municipal_comment": "הערת הרישוי",
    "interpretation": "פרשנות",
    "user_decision": "החלטת המשתמש",
    "correction": "תיקון",
    "affected_drawings": "גיליונות מושפעים",
    "planning_impact": "השפעה תכנונית",
    "validation": "אימות",
    "confidence": "ביטחון",
    "consultation_triggers": "סיבות להתייעצות",
    "none_extracted": "(לא חולצה דרישה)",
    "none_applied": "לא בוצע תיקון.",
    "none_required": "לא נדרש תיקון - המודל כבר עומד בהערה.",
    "no_impact": "לא זוהתה השפעה.",
    "not_sheeted": "(ללא שיוך לגיליון)",
    "not_evaluated": "לא נבדק.",
    "at_limit": "על הגבול",
    "still_compliant": "עדיין תקין",
    "not_compliant": "אינו תקין",
    "confidence_limited": "{value} (מוגבל על ידי {component})",
    "evidence_line": "{status}. נמדד {measured} {op} {required} הנדרש ({tool}, בסיס מדידה: {basis}).",
    "rows": "{count} שורות",
    "updated": "{element} {property} עודכן ({before} ← {after})",
    "status.Resolved": "טופל",
    "status.Partially resolved": "טופל חלקית",
    "status.Addressed - requires confirmation": "טופל - דורש אישור אנושי",
    "status.Not resolved": "לא טופל",
    "status.Requires human review": "דורש בדיקה אנושית",
    "status.Not applicable": "לא רלוונטי",
    "priority.critical": "קריטי", "priority.high": "גבוה",
    "priority.medium": "בינוני", "priority.low": "נמוך",
    "consultation": "התייעצות",
    "the_municipal_comment": "הערת הרישוי",
    "what_was_found": "מה נמצא",
    "affected_elements": "אלמנטים מושפעים:",
    "proposed_correction": "התיקון המוצע",
    "consequences": "השלכות",
    "alternatives": "חלופות",
    "recommendation": "המלצה",
    "option_line": "חלופה {letter}: {strategy}",
    "asking_because": "הסיבה לשאלה:",
    "answer_with": "תשובה אפשרית: approve | reject | alternative:<אות> | modify:<הנחיה>",
    "no_secondary_effect": "- לא זוהתה השפעה משנית",
    "none_identified": "(לא זוהו)",
    "unmet": "- לא מתקיים: {constraint} {rule}",
    "regression_line": "- נסיגה: {constraint} {rule}",
    "answer": "תשובה",
    "r_no_action": "ההערה אינה דורשת פעולה",
    "r_no_requirement": "לא ניתן לחלץ דרישה נמדדת מההערה",
    "r_no_element": "לא נמצא במודל אלמנט התואם ל-{requirement}",
    "r_ambiguous": "{count} אלמנטים תואמים וההערה אינה מציינת מזהה מבחין",
    "r_program": "{metric} הוא שינוי ברמת התוכנית - החלטה תכנונית ולא תיקון מינימלי",
    "r_no_strategy": "אין אסטרטגיית תכנון למדד {metric}",
    "r_unmeasurable": "לא ניתן היה למדוד את הערך הקיים: {error}",
    "r_no_minimal_change": "לא נמצא שינוי מינימלי שמקיים את {requirement}",
    "r_all_unsafe": "כל שינוי אפשרי שנבדק מפר אילוץ או יוצר התנגשות",
    "r_spatial": "התנגשות מרחבית: {detail}",
    "r_already_compliant": "כבר עומד בדרישה; לא נדרש שינוי",
    "r_annotation_missing_text": "ההערה מבקשת שינוי טקסט אך אינה מציינת את הנוסח החדש",
    "r_annotation_no_target": "לא נמצא במודל דבר התואם לשינוי ה{kind} המבוקש",
    "r_annotation_unsafe": "שינוי הסימון מפר אילוץ בסימולציה",
    "r_simulation_failed": "הסימולציה נכשלה: {error}",
    "r_below_floor": "ביטחון {value} נמוך מרף 0.60 (מוגבל על ידי {component})",
    "r_rejected": "המשתמש דחה את התיקון המוצע",
    "r_unanswered": "שאלת ההתייעצות לא נענתה",
    "r_modify": "המשתמש ביקש לשנות את התיקון: {note}",
    "r_execution_failed": "הביצוע נכשל: {error}",
    "r_file_unreadable": "לא ניתן לקרוא את הקובץ ({notes})",
    "r_no_model": "לא סופק מודל מקור הניתן לעריכה (או שאין דרייבר שיודע לקרוא אותו)",
    "r_equal_conflict": "שני אילוצים בעלי עדיפות ומקור זהים סותרים זה את זה: {rules}",
    "r_cycle": "תלות מעגלית בין השינויים",
    "r_regression": "נסיגה: {rule} אינו מתקיים עוד",
    "r_markup_only": "הרצת סימון בלבד: ההערה פורשה אך לא בוצעה מדידה",
    "r_not_measured": "לא ניתן היה למדוד את האילוץ",
    "n_human_decision": "החלטה או הבהרה מגורם אנושי",
    "n_architect_decision": "החלטה מפורשת של האדריכל האחראי",
    "n_which_governs": "החלטת האדריכל איזה אילוץ גובר",
    "n_human_review": "בדיקה אנושית",
    "n_review_interpretation": "בדיקה אנושית של הפרשנות ושל התיקון המוצע",
    "n_answer": "תשובה לשאלת ההתייעצות",
    "n_other_correction": "תיקון אחר, או מענה לרשות",
    "n_investigate_api": "בדיקת התקלה בממשק העריכה",
    "n_readable_copy": "עותק קריא של הקובץ, או ייצוא לטקסט/JSON",
    "n_driver": "מתאם ל-DWG/RVT/IFC, או ייצוא מודל ל-JSON",
    "n_precedence": "החלטה אנושית איזה שינוי גובר",
    "n_rollback": "חזרה לגרסה קודמת או תוכנית תיקון מתוקנת",
    "n_missing_reference": "המסמך החסר, או בדיקה ידנית",
    "n_drafter": "שרטט שיבצע את ההוראה",
    "t_ambiguous": "ההערה אינה מזהה אלמנט יחיד",
    "t_confidence": "ביטחון {value} נמוך מהרף {threshold} (מוגבל על ידי {component})",
    "t_spatial": "התיקון יוצר התנגשות מרחבית: {detail}",
    "t_unmet": "התיקון משאיר אילוץ אחר בלתי מתקיים: {constraints}",
    "t_changes_metric": "התיקון משנה {metric} ({before} ← {after})",
    "t_structural": "{element} הוא אלמנט קונסטרוקטיבי",
    "t_footprint": "התיקון משנה את תכסית הבניין",
    "t_consultant": "{element} שייך ליועץ אחר ({consultant})",
    "t_multiple": "קיימת יותר מחלופה תקפה אחת",
    "t_hard_metric": "השינוי משנה {metric}, שדורש תמיד אישור אנושי",
    "t_low_confidence_risk": ("ביטחון {value} ברמת סיכון {risk}; במצב אוטונומי מבוצעים רק "
                              "שינויים מינימליים והפיכים מתחת לרף"),
    "v_statement_only": "הערת יידוע בלבד; לא נדרשת פעולה",
    "v_not_measurable": "השינוי בוצע, אך הדרישה אינה ניתנת למדידה אוטומטית",
    "v_no_requirement": "לא ניתן לחלץ מההערה דרישה נמדדת",
    "v_cannot_measure": "לא ניתן היה למדוד: {error}",
    "v_still_not_met": "בוצע שינוי אך הדרישה עדיין אינה מתקיימת",
    "v_no_change": "לא בוצע שינוי תקף",
    "v_no_test": "לאילוץ אין ניסוח הניתן לבדיקה אוטומטית",
    "s_set_dimension": "קביעת {parameter} של {element} ל-{value} (תוך קיבוע הצד ה{anchor})",
    "s_move": "הזזת {element} ב-{distance} ל{direction} לקבלת נסיגה {edge} של {value}",
    "s_pull_back": "נסיגת החזית ה{edge} של {element} ב-{distance} ({parameter} {before} ← {after})",
    "s_annotation": "{action} ({count} פריטים)",
    "s_no_change": "לא נדרש שינוי: {requirement} כבר מתקיים ({measured})",
    "s_program_proposal": ("{requirement}; המודל מודד כיום {measured}. סגירת הפער משנה את תוכנית "
                           "הפרויקט, וזו החלטה תכנונית של האדריכל."),
    "s_blocked": ("השינוי המינימלי ({strategy}) יפר את {blockers}. נדרש אישור הרשות להקלה "
                  "באילוץ החוסם, או שינוי תכנוני רחב יותר ממה שההערה מאפשרת."),
    "s_rollback": "שחזור הגרסה הקודמת",
    "dod_manifest": "כל קובץ שסופק מופיע ברשימת הקלט עם סטטוס קריאה.",
    "dod_comments": "לכל הערת רישוי יש אובייקט, סטטוס ורמת ביטחון.",
    "dod_evidence": 'לכל הערה המסומנת "טופל" יש ראיה מדודה.',
    "dod_traceability": "כל שינוי משויך למזהה הערה ולמזהה תוכנית תיקון.",
    "dod_simulated": "כל תוכנית שיושמה עברה סימולציה ובדיקה מקדימה.",
    "dod_ledger": "כל מאגר האילוצים נבדק; אין נסיגה ואין כשל באילוץ קריטי.",
    "dod_questions": "כל שאלת התייעצות נענתה או רשומה כפריט פתוח.",
    "dod_original": "קובץ המקור המקורי זהה בבתים ל-checksum שנרשם בקליטה.",
    "dod_version": "נוצרה גרסה חדשה בלתי ניתנת לשינוי עם מניפסט ויומן ביקורת.",
    "dod_previews": "הופקו תצוגות מקדימות, השוואה ומפת שינויים מסומנת.",
    "dod_open_items": "כל פריט פתוח מציין מה נדרש וממי.",
    "before": "לפני",
    "after": "אחרי ({version})",
    "changes": "שינויים ({version})",
    "plot_boundary": "גבול המגרש",
    "affected": "מושפע",
    "no_changes": "אין שינויים",
    "affected_indirectly": "מושפע בעקיפין",
    "compare_title": "לפני / אחרי - {version}",
    "legend_modified": "אלמנטים חדשים או ששונו",
    "legend_removed": "אלמנטים שהוסרו או הוחלפו",
    "legend_indirect": "אלמנטים המושפעים בעקיפין",
    "legend_resolved": "הערות רישוי שנפתרו בעקבות השינוי",
    "legend_unresolved": "נושאים פתוחים הדורשים בדיקה",
    "metric.width": "רוחב", "metric.length": "אורך", "metric.height": "גובה",
    "metric.area": "שטח", "metric.floor_area": "שטח בנייה", "metric.count": "מספר",
    "metric.setback": "נסיגה", "metric.clear_width": "רוחב נטו",
    "metric.clear_distance": "מרחק",
    "dir.north": "צפון", "dir.south": "דרום", "dir.east": "מזרח", "dir.west": "מערב",
    "edge.north": "צפונית", "edge.south": "דרומית",
    "edge.east": "מזרחית", "edge.west": "מערבית",
    "anchor.south_west": "דרומי-מערבי", "anchor.north_east": "צפוני-מזרחי",
    "anchor.centre": "מרכזי", "anchor.north_west": "צפוני-מערבי",
    "anchor.south_east": "דרומי-מזרחי",
    "requirement_line": "{metric} של {subject} {op} {value}",
    "etype.parking": "מקום חניה", "etype.driveway": "שביל גישה",
    "etype.building": "בניין", "etype.balcony": "מרפסת", "etype.room": "חדר",
    "etype.ramp": "רמפה", "etype.wall": "קיר", "etype.window": "חלון",
    "etype.sidewalk": "מדרכה", "etype.store": "מחסן",
    "etype.project": "הפרויקט",
    "department.Planning": "תכנון", "department.Architecture": "אדריכלות",
    "department.Licensing": "רישוי", "department.Traffic": "תנועה",
    "department.Parking": "חניה", "department.Accessibility": "נגישות",
    "department.Fire Safety": "כבאות", "department.Sanitation": "תברואה",
    "department.Water": "מים", "department.Drainage": "ניקוז",
    "department.Landscaping": "גינון", "department.Environment": "איכות הסביבה",
    "department.Infrastructure": "תשתיות", "department.Engineering": "הנדסה",
    "department.Unknown": "לא ידוע",
    "mode.consultation": "התייעצות", "mode.autonomous": "אוטונומי",
    "exec.applied": "בוצע במודל", "exec.markup_only": "סימון בלבד",
    "result.passed": "עבר", "result.passed_with_open_items": "עבר עם פריטים פתוחים",
    "result.failed": "נכשל",
    "check.duplicate_elements": "אלמנטים כפולים",
    "check.broken_references": "הפניות שבורות",
    "check.spatial_conflicts": "התנגשויות מרחביות",
    "check.schedules": "טבלאות",
    "check.sheet_assignment": "שיוך לגיליונות",
    "check.drawing_checks": "בדיקות תוכנית",
    "check_status.pass": "עבר", "check_status.fail": "נכשל",
    "check_status.warn": "אזהרה", "check_status.not_evaluated": "לא נבדק",
    "unit.m": " מ'", "unit.cm": ' ס"מ', "unit.mm": ' מ"מ', "unit.m2": ' מ"ר',
    "unit.sqm": ' מ"ר', "unit.count": "", "unit.unit": "",
    "conf.extraction": "חילוץ הטקסט", "conf.interpretation": "הפרשנות",
    "conf.identification": "זיהוי האלמנט", "conf.solution": "הפתרון",
    "conf.verification": "האימות",
    "implicit_count": "מספר מקומות החניה לא יקטן מ-{value} שאושרו",
    "implicit_dimension": "{parameter} של {element} לא יקטן מ-{value} שאושרו",
    "r_model_choice": "המודל זיהה את האלמנט: {reasoning}",
    "r_model_declined": "גם המודל לא הצליח להבחין בין המועמדים",
    "attention": "דורש את החלטתך",
    "err_ambiguous_subject": "הנושא תואם {count} אלמנטים",
    "err_not_found": "האלמנט {element} אינו קיים במודל",
    "err_no_plot": "למודל אין גבול מגרש, ולכן לא ניתן למדוד נסיגה",
}

TABLES = {"en": ENGLISH, "he": HEBREW}


class Messages:
    """Localised text with an English fallback."""

    def __init__(self, code: str = "en"):
        self.code = code if code in TABLES else "en"
        self.table = TABLES[self.code]

    @property
    def rtl(self) -> bool:
        return self.code in ("he", "ar")

    @property
    def text_direction(self) -> str:
        return "rtl" if self.rtl else "ltr"

    def knows(self, key: str) -> bool:
        return key in self.table or key in ENGLISH

    def effect_property(self, prop: str) -> str:
        """Render "setback (north)" as a phrase in this language."""
        metric, _, rest = prop.partition(" ")
        edge = rest.strip("() ")
        label = self.metric(metric)
        return f"{label} {self.edge(edge)}" if edge else label

    def t(self, key: str, **params) -> str:
        template = self.table.get(key, ENGLISH.get(key, key))
        if not params:
            return template
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template

    def metric(self, metric: str) -> str:
        return self.t(f"metric.{metric}")

    def direction(self, direction: str) -> str:
        return self.t(f"dir.{direction}")

    def edge(self, edge: str) -> str:
        return self.t(f"edge.{edge}")

    def anchor(self, anchor: str) -> str:
        return self.t(f"anchor.{anchor}")

    def value(self, value: float, unit: str = "m", op: str | None = None) -> str:
        """A measurement, rounded conservatively and suffixed in this language."""
        from .. import units as _units

        if value is None:
            return "-"
        if unit in ("count", "unit"):
            return f"{int(round(value))}"
        shown = _units.round_conservative(value, op) if op else round(value, _units.REPORT_DECIMALS)
        return f"{shown:.{_units.REPORT_DECIMALS}f}{self.t('unit.' + unit)}"

    def driver_error(self, error) -> str:
        """Render a driver failure in this language; unknown ones pass through."""
        import re

        text = str(error)
        match = re.search(r"subject matches (\d+) elements", text)
        if match:
            return self.t("err_ambiguous_subject", count=match.group(1))
        match = re.search(r"element not found: '([^']+)'", text)
        if match:
            return self.t("err_not_found", element=match.group(1))
        if "no site plot" in text:
            return self.t("err_no_plot")
        return text

    def component(self, component: str) -> str:
        return self.t(f"conf.{component}")

    def element_type(self, element_type: str) -> str:
        return self.t(f"etype.{element_type}")

    def department(self, department: str) -> str:
        return self.t(f"department.{department}")

    def mode(self, mode: str) -> str:
        return self.t(f"mode.{mode}")

    def execution(self, execution: str) -> str:
        return self.t(f"exec.{execution}")

    def result(self, result: str) -> str:
        return self.t(f"result.{result}")

    def check(self, check: str) -> str:
        return self.t(f"check.{check}")

    def check_status(self, status: str) -> str:
        return self.t(f"check_status.{status}")

    def status(self, status) -> str:
        value = getattr(status, "value", str(status))
        return self.t(f"status.{value}")

    def priority(self, priority) -> str:
        value = getattr(priority, "value", str(priority))
        return self.t(f"priority.{value}")


DEFAULT = Messages("en")
