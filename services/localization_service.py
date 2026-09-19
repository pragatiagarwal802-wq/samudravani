"""Deterministic English -> Hindi / Gujarati rendering of voyage plans.

No machine translation or LLM is used, so a translation can never invent or
alter a number. Each English sentence the planner/risk service can emit is
matched by a pattern; captured numbers, coordinates and tags are copied
verbatim into a fixed translated template (ASCII digits, Latin units and
safety tags such as HIGH_RISK stay as-is; a gloss is added beside a tag,
never in place of it).

Two guards keep this safe:
  * a sentence with no matching pattern is shown in English and listed in
    `untranslated` (never guessed);
  * every translated sentence is re-checked: its multiset of numbers and safety
    tags must equal the source's, otherwise the English original is used.

The Hindi and Gujarati wording is hand-written and should be reviewed by a native
speaker (ideally a fisheries/maritime one) before operational use.
The original VoyagePlan is never modified.
"""
from __future__ import annotations

import re
from collections import Counter
from typing import Dict, List, Optional, Tuple

from models.schemas import LocalizedPlan, LocalizedRule, VoyagePlan

LANGS = ("en", "hi", "gu")
LANG_NAMES = {"en": "English", "hi": "हिन्दी", "gu": "ગુજરાતી"}

NUM = r"-?\d+(?:\.\d+)?"
LABEL = rf"(?:zone|destination) \([^)]*\)(?: score {NUM})?"

_TAGS = ("SAFE|CAUTION|HIGH_RISK|DO_NOT_VENTURE|INSUFFICIENT_DATA|PROCEED_WITH_CAUTION|PROCEED|"
         "NOT_RECOMMENDED|REFUSED|NOT_AVAILABLE|PARTIAL|ERROR")
_TAG_RE = re.compile(rf"(?<![A-Za-z_])(?:{_TAGS})(?![A-Za-z_])")
_NUM_RE = re.compile(rf"(?<![A-Za-z_\d]){NUM}(?!\d)")
_SENT = re.compile(r"(?<=\.)\s+(?=[A-Z])")

TAG_GLOSS: Dict[str, Dict[str, str]] = {
    "hi": {"SAFE": "सुरक्षित", "CAUTION": "सावधानी", "HIGH_RISK": "उच्च जोखिम",
           "DO_NOT_VENTURE": "समुद्र में न जाएं", "INSUFFICIENT_DATA": "अपर्याप्त डेटा",
           "PROCEED": "आगे बढ़ें", "PROCEED_WITH_CAUTION": "सावधानी से आगे बढ़ें",
           "NOT_RECOMMENDED": "अनुशंसित नहीं", "REFUSED": "योजना नहीं बनाई गई"},
    "gu": {"SAFE": "સુરક્ષિત", "CAUTION": "સાવધાની", "HIGH_RISK": "ઉચ્ચ જોખમ",
           "DO_NOT_VENTURE": "દરિયામાં ન જાઓ", "INSUFFICIENT_DATA": "અપૂરતો ડેટા",
           "PROCEED": "આગળ વધો", "PROCEED_WITH_CAUTION": "સાવધાનીથી આગળ વધો",
           "NOT_RECOMMENDED": "ભલામણ નથી", "REFUSED": "યોજના બનાવાઈ નથી"},
}

# Variable names, and exact phrases used in rule messages (config/risk_config.yaml).
VARS = {
    "hi": {"wave_height": "तरंग ऊँचाई", "wind_speed": "हवा की गति", "visibility": "दृश्यता",
           "current_speed": "धारा की गति"},
    "gu": {"wave_height": "મોજાની ઊંચાઈ", "wind_speed": "પવનની ગતિ", "visibility": "દૃશ્યતા",
           "current_speed": "પ્રવાહની ગતિ"},
}
GLOSS = {
    "hi": {"Significant wave height": "सार्थक तरंग ऊँचाई", "Wind": "हवा", "Visibility": "दृश्यता", "Current": "धारा",
           "moderate sea": "मध्यम समुद्र", "rough sea": "उग्र समुद्र",
           "very rough or worse": "बहुत उग्र या उससे बदतर",
           "Beaufort 6, strong breeze": "ब्यूफोर्ट 6, तेज़ हवा", "Beaufort 8, gale": "ब्यूफोर्ट 8, प्रचंड हवा",
           "Beaufort 10, storm": "ब्यूफोर्ट 10, तूफ़ान", "poor": "खराब", "fog": "कोहरा", "strong": "तेज़"},
    "gu": {"Significant wave height": "નોંધપાત્ર મોજાની ઊંચાઈ", "Wind": "પવન", "Visibility": "દૃશ્યતા",
           "Current": "પ્રવાહ", "moderate sea": "મધ્યમ દરિયો", "rough sea": "તોફાની દરિયો",
           "very rough or worse": "અત્યંત તોફાની અથવા વધુ ખરાબ",
           "Beaufort 6, strong breeze": "બ્યુફોર્ટ 6, પ્રબળ પવન", "Beaufort 8, gale": "બ્યુફોર્ટ 8, વાવાઝોડા જેવો પવન",
           "Beaufort 10, storm": "બ્યુફોર્ટ 10, તોફાન", "poor": "નબળી", "fog": "ધુમ્મસ", "strong": "તીવ્ર"},
}

# (regex, hindi template, gujarati template). Groups: t_* translated recursively,
# l_* "; "-separated list of translated items, v_* variable names, g_* glossary
# phrases (must exist), anything else copied verbatim.
_RAW: List[Tuple[str, str, str]] = [
    # --- labels ---
    (rf"zone \((?P<lat>{NUM}), (?P<lon>{NUM})\) score (?P<s>{NUM})",
     "मछली पकड़ने का क्षेत्र ({lat}, {lon}), स्कोर {s}", "માછીમારી ક્ષેત્ર ({lat}, {lon}), સ્કોર {s}"),
    (rf"destination \((?P<lat>{NUM}), (?P<lon>{NUM})\)", "गंतव्य ({lat}, {lon})", "ગંતવ્ય ({lat}, {lon})"),
    # --- planner summary / explanation ---
    (rf"(?P<tag>[A-Z_]+): (?P<t_l>{LABEL}), (?P<d>{NUM}) nm, ~(?P<f>{NUM}) L one-way\.",
     "{tag}: {t_l}, {d} nm, ~{f} L (एक तरफ़)।", "{tag}: {t_l}, {d} nm, ~{f} L (એક તરફ)."),
    (r"Cannot produce a voyage plan: (?P<t_r>.+)",
     "यात्रा योजना नहीं बनाई जा सकती: {t_r}", "સફર યોજના બનાવી શકાતી નથી: {t_r}"),
    (r"Do not venture out\. (?P<t_r>.+)", "समुद्र में न जाएं। {t_r}", "દરિયામાં ન જાઓ. {t_r}"),
    (r"Voyage not recommended\. (?P<t_r>.+)", "यात्रा की सलाह नहीं दी जाती। {t_r}", "સફરની ભલામણ નથી. {t_r}"),
    (r"Target: (?P<t_l>.+)\.", "लक्ष्य: {t_l}।", "લક્ષ્ય: {t_l}."),
    (r"Why this zone: (?P<l_r>.+)\.", "यह क्षेत्र क्यों: {l_r}।", "આ ક્ષેત્ર કેમ: {l_r}."),
    (rf"SST front: gradient (?P<g>{NUM}) degC/km", "SST फ्रंट: ढाल {g} degC/km", "SST ફ્રન્ટ: ઢાળ {g} degC/km"),
    (rf"Chl-a front: gradient (?P<g>{NUM}) log10/km", "क्लोरोफिल-a फ्रंट: ढाल {g} log10/km",
     "ક્લોરોફિલ-a ફ્રન્ટ: ઢાળ {g} log10/km"),
    (rf"SST (?P<v>{NUM}) degC within preferred band", "SST {v} degC अनुकूल सीमा के भीतर", "SST {v} degC અનુકૂળ મર્યાદામાં"),
    (rf"Chl-a (?P<v>{NUM}) mg/m3 within preferred band", "क्लोरोफिल-a {v} mg/m3 अनुकूल सीमा के भीतर",
     "ક્લોરોફિલ-a {v} mg/m3 અનુકૂળ મર્યાદામાં"),
    (r"front-derived cell", "फ्रंट से प्राप्त ग्रिड सेल", "ફ્રન્ટ પરથી મળેલ ગ્રીડ સેલ"),
    (rf"Route: (?P<d>{NUM}) nm, (?P<h>{NUM}) h, (?P<f>{NUM}) L one-way \((?P<rt>{NUM}) L round trip\)\.",
     "मार्ग: {d} nm, {h} h, {f} L एक तरफ़ ({rt} L आना-जाना)।",
     "માર્ગ: {d} nm, {h} h, {f} L એક તરફ ({rt} L આવવા-જવા)."),
    (rf"Along the route: max wave (?P<w>{NUM}) m, max headwind (?P<h>{NUM}) m/s\.",
     "मार्ग पर: अधिकतम लहर {w} m, अधिकतम सामने की हवा {h} m/s।",
     "માર્ગ પર: મહત્તમ મોજું {w} m, મહત્તમ સામેનો પવન {h} m/s."),
    # --- caveats ---
    (r"Route was NOT checked against land\. Do not navigate by it\.",
     "मार्ग की तट/भूमि से जांच नहीं हुई है। इसके आधार पर नौवहन न करें।",
     "માર્ગની કિનારા/જમીન સામે ચકાસણી થઈ નથી. આના આધારે નૌકાવહન ન કરો."),
    (r"Weather missing for (?P<n>\d+) route legs; they were costed as calm\.",
     "{n} मार्ग खंडों के लिए मौसम डेटा नहीं था; उन्हें शांत मौसम मानकर गणना की गई।",
     "{n} માર્ગ ખંડ માટે હવામાન ડેટા ન હતો; તેમને શાંત હવામાન ગણીને ગણતરી કરી."),
    (r"Weather missing for all route legs; they were costed as calm\.",
     "सभी मार्ग खंडों के लिए मौसम डेटा नहीं था; उन्हें शांत मौसम मानकर गणना की गई।",
     "બધા માર્ગ ખંડ માટે હવામાન ડેટા ન હતો; તેમને શાંત હવામાન ગણીને ગણતરી કરી."),
    (r"Not evaluated \(no data\): (?P<v_x>.+)\.", "मूल्यांकन नहीं हुआ (डेटा नहीं): {v_x}।",
     "મૂલ્યાંકન થયું નથી (ડેટા નથી): {v_x}."),
    (r"(?P<p>[a-z0-9]+) data status (?P<s>[A-Z_]+)\.", "{p} डेटा स्थिति: {s}।", "{p} ડેટા સ્થિતિ: {s}."),
    # --- conflicts / refusal reasons ---
    (r"Fishing/route options were computed but ignored: safety verdict overrides yield\.",
     "मछली/मार्ग विकल्प निकाले गए लेकिन अनदेखा किए गए: सुरक्षा निर्णय उत्पादन से ऊपर है।",
     "માછીમારી/માર્ગ વિકલ્પો ગણ્યા પરંતુ અવગણ્યા: સલામતીનો નિર્ણય ઉત્પાદન કરતાં ઉપર છે."),
    (rf"Dropped (?P<t_l>{LABEL}): (?P<t_r>.+)\.", "{t_l} हटाया गया: {t_r}।", "{t_l} દૂર કર્યું: {t_r}."),
    (rf"Top-ranked (?P<t_a>{LABEL}) was not usable; chose (?P<t_b>{LABEL}) instead\.",
     "सर्वोच्च रैंक वाला {t_a} उपयोग योग्य नहीं था; इसके बजाय {t_b} चुना गया।",
     "સર્વોચ્ચ ક્રમનું {t_a} ઉપયોગી ન હતું; તેના બદલે {t_b} પસંદ કર્યું."),
    (rf"Chose (?P<t_a>{LABEL}) over equally scored (?P<t_b>{LABEL}): lower fuel\.",
     "{t_a} चुना गया, समान स्कोर वाले {t_b} की तुलना में: कम ईंधन।",
     "સમાન સ્કોરવાળા {t_b} કરતાં {t_a} પસંદ કર્યું: ઓછું બળતણ."),
    (r"no passable route on the grid", "ग्रिड पर कोई पार करने योग्य मार्ग नहीं", "ગ્રિડ પર કોઈ પસાર થઈ શકે તેવો માર્ગ નથી"),
    (r"start snaps to a land cell", "प्रारंभ बिंदु भूमि वाले सेल पर आता है", "પ્રારંભ બિંદુ જમીનવાળા સેલ પર આવે છે"),
    (r"goal snaps to a land cell", "गंतव्य बिंदु भूमि वाले सेल पर आता है", "ગંતવ્ય બિંદુ જમીનવાળા સેલ પર આવે છે"),
    (r"route not checked against a land mask", "मार्ग की भूमि-मास्क से जांच नहीं हुई",
     "માર્ગની લેન્ડ-માસ્ક સામે ચકાસણી થઈ નથી"),
    (rf"round trip needs (?P<a>{NUM}) L > budget (?P<b>{NUM}) L",
     "आना-जाना {a} L मांगता है, जो बजट {b} L से अधिक है", "આવવા-જવા માટે {a} L જોઈએ, જે બજેટ {b} L કરતાં વધુ છે"),
    (r"no risk assessment was produced", "कोई जोखिम आकलन नहीं बना", "કોઈ જોખમ મૂલ્યાંકન બન્યું નથી"),
    (r"no destination was given and (?P<t_r>.+)", "कोई गंतव्य नहीं दिया गया और {t_r}",
     "કોઈ ગંતવ્ય આપ્યું નથી અને {t_r}"),
    (r"no front-derived fishing zone met the score threshold",
     "कोई फ्रंट-आधारित मछली क्षेत्र स्कोर सीमा तक नहीं पहुँचा", "કોઈ ફ્રન્ટ-આધારિત માછીમારી ક્ષેત્ર સ્કોર મર્યાદાએ પહોંચ્યું નથી"),
    (r"No SST or Chl-a field supplied; no zones computed\.",
     "SST या क्लोरोफिल-a डेटा नहीं मिला; कोई क्षेत्र नहीं निकाला गया।",
     "SST અથવા ક્લોરોફિલ-a ડેટા મળ્યો નથી; કોઈ ક્ષેત્ર ગણ્યું નથી."),
    (r"no routable target", "कोई मार्ग योग्य लक्ष्य नहीं", "કોઈ માર્ગ યોગ્ય લક્ષ્ય નથી"),
    (r"no land mask configured \(set LAND_POLYGONS_GEOJSON\); routes cannot be certified land-safe\. "
     r"Set allow_unmasked_route only for development\.",
     "कोई भूमि-मास्क कॉन्फ़िगर नहीं है (LAND_POLYGONS_GEOJSON सेट करें); मार्गों को भूमि-सुरक्षित प्रमाणित नहीं किया जा सकता। "
     "allow_unmasked_route केवल विकास के लिए सेट करें।",
     "કોઈ લેન્ડ-માસ્ક ગોઠવેલ નથી (LAND_POLYGONS_GEOJSON સેટ કરો); માર્ગોને જમીન-સુરક્ષિત પ્રમાણિત કરી શકાતા નથી. "
     "allow_unmasked_route ફક્ત વિકાસ માટે સેટ કરો."),
    (r"no candidate target is reachable within the constraints\.(?: (?P<t_r>.*))?",
     "बाधाओं के भीतर कोई लक्ष्य पहुँच योग्य नहीं। {t_r}", "મર્યાદાઓમાં કોઈ લક્ષ્ય પહોંચી શકાય તેવું નથી. {t_r}"),
    # --- risk_service sentences ---
    (r"(?P<g_nm>Significant wave height|Wind|Visibility|Current) (?P<v>" + NUM + r") (?P<u>m/s|km|m) "
     r"(?P<op>>=|<=) (?P<t>" + NUM + r") (?P=u) \((?P<g_d>[^)]*)\)\.",
     "{g_nm} {v} {u} {op} {t} {u} ({g_d})।", "{g_nm} {v} {u} {op} {t} {u} ({g_d})."),
    (r"(?P<g_nm>Significant wave height|Wind|Visibility|Current) (?P<v>" + NUM + r") (?P<u>m/s|km|m) "
     r"(?P<op>>=|<=) (?P<t>" + NUM + r") (?P=u)\.",
     "{g_nm} {v} {u} {op} {t} {u}।", "{g_nm} {v} {u} {op} {t} {u}."),
    (r"SAFE: no rule triggered for (?P<v_x>.+)\.", "SAFE: {v_x} के लिए कोई नियम सक्रिय नहीं हुआ।",
     "SAFE: {v_x} માટે કોઈ નિયમ સક્રિય થયો નથી."),
    (r"INSUFFICIENT_DATA: only (?P<n>\d+) of the required (?P<m>\d+) variables available \(missing: (?P<v_x>.+)\)\.",
     "INSUFFICIENT_DATA: आवश्यक {m} में से केवल {n} चर उपलब्ध हैं (अनुपलब्ध: {v_x})।",
     "INSUFFICIENT_DATA: જરૂરી {m} માંથી ફક્ત {n} ચલ ઉપલબ્ધ છે (અનુપલબ્ધ: {v_x})."),
    (r"(?P<tag>CAUTION|HIGH_RISK|DO_NOT_VENTURE): (?P<t_r>.+)", "{tag}: {t_r}", "{tag}: {t_r}"),
]
_PATTERNS = [(re.compile(rx), {"hi": hi, "gu": gu}) for rx, hi, gu in _RAW]


class LocalizationService:
    # -- text -----------------------------------------------------------------
    def _fill(self, m: "re.Match", tmpl: str, lang: str) -> Optional[str]:
        vals: Dict[str, str] = {}
        for k, v in m.groupdict().items():
            if v is None:
                vals[k] = ""
            elif k.startswith("t_"):
                r = self._apply(v, lang)
                if r is None:
                    return None
                vals[k] = r
            elif k.startswith("l_"):
                parts = [self._apply(i, lang) for i in v.split("; ")]
                if any(p is None for p in parts):
                    return None
                vals[k] = "; ".join(parts)
            elif k.startswith("v_"):
                vals[k] = ", ".join(VARS[lang].get(x.strip(), x.strip()) for x in v.split(","))
            elif k.startswith("g_"):
                g = GLOSS[lang].get(v)
                if g is None:
                    return None
                vals[k] = g
            else:
                vals[k] = v
        return tmpl.format(**vals).strip()

    def _apply(self, text: str, lang: str) -> Optional[str]:
        for rx, tmpl in _PATTERNS:
            m = rx.fullmatch(text)
            if m:
                out = self._fill(m, tmpl[lang], lang)
                if out is not None:
                    return out
        parts = _SENT.split(text)
        if len(parts) > 1:
            outs = [self._apply(p, lang) for p in parts]
            if all(o is not None for o in outs):
                return " ".join(outs)
        return None

    @staticmethod
    def _invariants(text: str) -> Tuple[Counter, Counter]:
        return Counter(_NUM_RE.findall(text)), Counter(_TAG_RE.findall(text))

    def translate(self, text: str, lang: str) -> Tuple[str, bool]:
        """(text, translated). Falls back to the English original if no pattern matches or if
        the numbers/safety tags of the result differ from the source."""
        if lang == "en" or not text:
            return text, True
        if lang not in LANGS:
            raise ValueError(f"unsupported language {lang!r}")
        out = self._apply(text, lang)
        if out is None or self._invariants(out) != self._invariants(text):
            return text, False
        return out, True

    def tag(self, tag: str, lang: str) -> str:
        """'HIGH_RISK' -> 'HIGH_RISK - उच्च जोखिम': the tag is kept, a gloss is appended."""
        gloss = TAG_GLOSS.get(lang, {}).get(tag)
        return f"{tag} - {gloss}" if gloss else tag

    # -- plan -----------------------------------------------------------------
    def localize_plan(self, plan: VoyagePlan, lang: str) -> LocalizedPlan:
        missed: List[str] = []

        def tr(t: str) -> str:
            out, ok = self.translate(t, lang)
            if not ok:
                missed.append(t)
            return out

        risk = plan.risk
        return LocalizedPlan(
            lang=lang,
            status_tag=plan.status.value,
            status_text=self.tag(plan.status.value, lang),
            summary=tr(plan.summary),
            refusal_reason=tr(plan.refusal_reason) if plan.refusal_reason else None,
            risk_tag=risk.verdict.value if risk else None,
            risk_text=self.tag(risk.verdict.value, lang) if risk else None,
            risk_explanation=tr(risk.explanation) if risk else None,
            triggered=[LocalizedRule(rule_id=t.rule_id, variable=t.variable, verdict=t.verdict.value,
                                     message=tr(t.message)) for t in (risk.triggered if risk else [])],
            explanation=[tr(x) for x in plan.explanation],
            caveats=[tr(x) for x in plan.caveats],
            conflicts_resolved=[tr(x) for x in plan.conflicts_resolved],
            untranslated=missed,
        )

    def localize_all(self, plan: VoyagePlan) -> Dict[str, LocalizedPlan]:
        return {lang: self.localize_plan(plan, lang) for lang in LANGS}


# UI chrome for the dashboard (headings and buttons only; never data).
UI_LABELS: Dict[str, Dict[str, str]] = {
    "en": {"title": "SamudraVani - Voyage Planner", "language": "Language", "origin": "Origin",
           "destination": "Destination (optional)", "plan_btn": "Plan voyage", "map": "Voyage map",
           "route": "Suggested route", "pfz": "Potential Fishing Zones", "score": "Suitability score",
           "risk": "Risk assessment", "rules": "Triggered rules", "none_triggered": "No rules triggered",
           "why": "Explanation", "caveats": "Caveats", "conflicts": "Decisions and overrides",
           "data": "Data sources", "pfz_warn": "Shown for information only: the safety verdict advises against this voyage.",
           "no_route": "No route to show.", "no_pfz": "No fishing zones identified.", "untranslated": "Shown in English",
           "distance": "Distance", "fuel": "Fuel (one-way)", "duration": "Duration"},
    "hi": {"title": "समुद्रवाणी - यात्रा योजनाकार", "language": "भाषा", "origin": "प्रारंभ स्थान",
           "destination": "गंतव्य (वैकल्पिक)", "plan_btn": "यात्रा योजना बनाएं", "map": "यात्रा मानचित्र",
           "route": "सुझाया गया मार्ग", "pfz": "संभावित मछली पकड़ने के क्षेत्र", "score": "उपयुक्तता स्कोर",
           "risk": "जोखिम आकलन", "rules": "सक्रिय हुए नियम", "none_triggered": "कोई नियम सक्रिय नहीं हुआ",
           "why": "स्पष्टीकरण", "caveats": "सावधानियाँ", "conflicts": "निर्णय और अधिभावी बदलाव",
           "data": "डेटा स्रोत", "pfz_warn": "केवल जानकारी के लिए: सुरक्षा निर्णय इस यात्रा के विरुद्ध सलाह देता है।",
           "no_route": "दिखाने के लिए कोई मार्ग नहीं।", "no_pfz": "कोई मछली क्षेत्र नहीं मिला।",
           "untranslated": "अंग्रेज़ी में दिखाया गया", "distance": "दूरी", "fuel": "ईंधन (एक तरफ़)", "duration": "अवधि"},
    "gu": {"title": "સમુદ્રવાણી - સફર આયોજક", "language": "ભાષા", "origin": "પ્રારંભ સ્થાન",
           "destination": "ગંતવ્ય (વૈકલ્પિક)", "plan_btn": "સફર યોજના બનાવો", "map": "સફર નકશો",
           "route": "સૂચવેલ માર્ગ", "pfz": "સંભવિત માછીમારી ક્ષેત્રો", "score": "યોગ્યતા સ્કોર",
           "risk": "જોખમ મૂલ્યાંકન", "rules": "સક્રિય થયેલા નિયમો", "none_triggered": "કોઈ નિયમ સક્રિય થયો નથી",
           "why": "સ્પષ્ટીકરણ", "caveats": "સાવચેતીઓ", "conflicts": "નિર્ણયો અને ફેરફારો",
           "data": "ડેટા સ્ત્રોતો", "pfz_warn": "ફક્ત માહિતી માટે: સલામતી નિર્ણય આ સફર સામે સલાહ આપે છે.",
           "no_route": "બતાવવા માટે કોઈ માર્ગ નથી.", "no_pfz": "કોઈ માછીમારી ક્ષેત્ર મળ્યું નથી.",
           "untranslated": "અંગ્રેજીમાં બતાવ્યું", "distance": "અંતર", "fuel": "બળતણ (એક તરફ)", "duration": "સમયગાળો"},
}
